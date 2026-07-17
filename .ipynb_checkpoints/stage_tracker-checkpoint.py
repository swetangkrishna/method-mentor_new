"""
stage_tracker.py — State machine for the 6-stage MethodCheck conversation.

Responsibilities:
  - Track the current stage and the history of stages visited.
  - Validate an agent's declared next stage (forward-only; skipping allowed;
    Stage 4 gated behind Stages 1-3).
  - Detect whether the user has signalled they want to discontinue.
  - Produce the stage-context block injected into the agent's system prompt.

The tracker is deliberately permissive: it lets the agent skip ahead (a natural
conversation may gather Stage 2 info during Stage 1), but never lets it move
backward, and never lets it jump to Stage 4 before the prerequisite stages are
done. If the agent declares an illegal stage, the tracker clamps it to the
nearest legal value and records that a correction happened.
"""

import re
from typing import Dict, List, Optional

from stages import (
    STAGES, FIRST_STAGE, FINAL_STAGE, GLOBAL_CONSTRAINTS,
    STAGE5_CONSTRAINTS, stage_name, required_parameters,
)

# Phrases that signal the user genuinely wants to STOP the session. These are
# deliberately strict: each must express clear stop-intent, not merely contain a
# word like "enough" or "done" that appears constantly in normal academic talk
# ("not sure that's enough rigor", "I'm done with the lit review"). The earlier
# bare patterns 'that's enough' and "i'm done" caused false exits and are removed.
_EXIT_PATTERNS = [
    r"\bstop here\b",
    r"\blet'?s stop\b",
    r"\b(?:can|could|should) we stop\b",
    # "that's enough" only counts as an exit when qualified as session-ending.
    r"\bthat'?s enough for (?:today|now|me|this)\b",
    r"\bthat'?s all for (?:today|now)\b",
    r"\bi'?m done (?:here|now|for (?:today|now))\b",
    r"\bi need to (?:go|leave|stop)\b(?!\s+(?:deeper|further|into|on|back|over|through|with|about))",
    r"\bi have to (?:go|leave|stop)\b(?!\s+(?:deeper|further|into|on|back|over|through|with|about))",
    r"\bend (?:the |this )?(?:conversation|session|chat|discussion)\b",
    r"\bi'?ll (?:stop|leave) (?:here|now)\b",
    r"\b(?:got|gotta) to? go\b",
    r"\bgotta go\b",
    r"\bno more questions\b",
    r"\blet'?s (?:wrap up|finish|end) (?:here|now|this)\b",
    r"\bthank you,? (?:that'?s all|goodbye|bye)\b",
    r"\b(?:goodbye|bye for now)\b",
]


class StageTracker:
    # After this many consecutive turns on the same stage, the tracker emits a
    # hard "advance now" directive (mirrors the agent's skill-ban mechanism).
    STALL_THRESHOLD = 2
    # Stage 4 now runs a PRESENT-then-REFLECT cycle per method (issue 006):
    # 3 methods x (1 present turn + ~1-2 reflect turns) ≈ 7-9 turns.
    STALL_THRESHOLD_STAGE4 = 9
    # Stage 5 is now cross-method COMPARISON (not per-method reflection), so it
    # is shorter than before.
    STALL_THRESHOLD_STAGE5 = 3
    # Stages 1-3 collect several required parameters (issues 002-004), one
    # question per turn. The parameter GATE already prevents leaving early, so
    # this only needs to cover ~one turn per question plus a little slack.
    STALL_THRESHOLD_PARAM_STAGES = 4
    # A required question is asked at most this many times. Beyond that we stop
    # demanding it — a detector miss must never trap the student in a loop of
    # the same question rephrased (issue 7).
    MAX_PARAM_ASKS = 2

    def __init__(self) -> None:
        self.current_stage: int = FIRST_STAGE
        self.stage_history: List[int] = []          # one entry per agent turn
        self.completed_stages: set = set()
        self.corrections: int = 0                    # illegal-transition count
        self.user_requested_exit: bool = False
        self.turns_on_current_stage: int = 0         # consecutive-turn counter
        self.forced_advances: int = 0                # how many times we pushed forward
        # Stage 4 content gate: whether the agent actually presented alternatives.
        self.stage4_alternatives_presented: bool = False
        self.stage4_methods_seen: set = set()        # which method names appeared

        # ── Required-parameter tracking (issues 002/003/004) ──────────────────
        # stage_number -> {param_id, ...} the student has actually answered.
        self.filled_parameters: Dict[int, set] = {}
        # param_id -> how many times the agent has been told to ask it. Used to
        # vary the phrasing (and lean on RAG) when a question must be repeated.
        self.parameter_ask_counts: Dict[str, int] = {}

        # ── Stage 4 present-then-reflect cycle (issue 006) ────────────────────
        # "present": introduce the next method. "reflect": ask feasibility
        # questions about the method just introduced, before the next one.
        self.stage4_phase: str = "present"
        self.stage4_current_method: Optional[str] = None
        # Methods the student has actually reflected on (feasibility discussed).
        self.stage4_methods_reflected: set = set()
        # Feasibility angles already used in the reflect phase, so each method's
        # reflection varies rather than always asking about the timeline.
        self._s4_asked_constraints: set = set()

    # ── Transition validation ─────────────────────────────────────────────────

    def legal_next(self, declared: Optional[int]) -> int:
        """
        Given the stage the agent declared for THIS turn, return the stage that
        will actually be recorded. Rules:
          - None / unparseable  -> stay on current stage.
          - Backward move       -> clamp to current stage (illegal; counted).
          - Stage 4 before 1-3 complete -> clamp to first incomplete prereq.
          - Skipping forward     -> allowed; intervening stages marked complete.
          - Beyond FINAL_STAGE  -> clamp to FINAL_STAGE.
        """
        if declared is None:
            return self.current_stage

        d = max(FIRST_STAGE, min(FINAL_STAGE, declared))

        # Backward move is illegal — stay where we are.
        if d < self.current_stage:
            self.corrections += 1
            return self.current_stage

        # Stage 4 is gated: stages 1, 2, 3 must all be complete first.
        if d >= 4 and self.current_stage < 4:
            prereqs = [1, 2, 3]
            missing = [s for s in prereqs if s not in self.completed_stages
                       and s != self.current_stage]
            # If the agent tries to jump to 4+ but hasn't cleared 1-3, allow at
            # most advancing to the first unfinished prerequisite.
            if missing or self.current_stage < 3:
                self.corrections += 1
                # advance by exactly one stage toward the gate
                return min(self.current_stage + 1, 4)

        return d

    def _scan_stage4_content(self, response_text: str,
                             stage4_alternatives: Optional[List[Dict]]) -> None:
        """
        Record which alternative methods appear in the agent's Stage 4 response.
        Marks stage4_alternatives_presented True once the response names at least
        TWO of the scenario's alternative methods (a genuine 'present alternatives'
        turn), counting cumulatively across consecutive Stage 4 turns.
        """
        if not response_text or not stage4_alternatives:
            return
        low = response_text.lower()
        for alt in stage4_alternatives:
            method = alt.get("method", "")
            if not method:
                continue
            # Match on the distinctive head noun(s) of the method name.
            # e.g. "Online survey of teachers" -> match "survey".
            keywords = [w for w in method.lower().replace(",", " ").split()
                        if w not in ("of", "a", "the", "with", "and", "an",
                                     "to", "for", "in", "on")]
            # A method counts as 'presented' if its first salient keyword appears.
            head = keywords[0] if keywords else method.lower()
            if head and head in low:
                self.stage4_methods_seen.add(method)
        if len(self.stage4_methods_seen) >= 2:
            self.stage4_alternatives_presented = True

    def stage4_content_satisfied(self) -> bool:
        """Has the Stage 4 'present alternatives' requirement actually been met?"""
        return self.stage4_alternatives_presented

    def advance(self, declared: Optional[int], stage_satisfied: bool,
                response_text: str = "",
                stage4_alternatives: Optional[List[Dict]] = None) -> int:
        """
        Record one agent turn. `declared` is the STAGE: header the agent emitted.
        `stage_satisfied` indicates the agent marked the current stage complete
        (via STAGE_COMPLETE: YES). `response_text` and `stage4_alternatives` enable
        the Stage 4 content gate. Returns the stage now in effect.

        Enforcement: if a stall directive was in effect for THIS turn and the agent
        failed to move forward, the tracker forces the advance — EXCEPT out of
        Stage 4, where it additionally requires that alternatives were actually
        presented (content gate). A hard safety cap prevents an infinite Stage 4.
        """
        # Scan this turn's content for presented methods if the agent is ACTING
        # in Stage 4 this turn — which is true if we are already in Stage 4, OR
        # the agent is declaring Stage 4 now (its first Stage 4 turn, where
        # current_stage is still 3 until the end of this method).
        acting_in_stage4 = (self.current_stage == 4) or (declared == 4)
        if acting_in_stage4:
            before = set(self.stage4_methods_seen)
            self._scan_stage4_content(response_text, stage4_alternatives)
            # A method the agent introduced THIS turn moves the cycle into its
            # reflect phase: next turn asks feasibility about that method.
            newly = self.stage4_methods_seen - before
            if newly:
                self.stage4_mark_presented(sorted(newly)[0])

        directive_was_active = self.is_stalled()
        target = self.legal_next(declared)

        # ── Stage 4 content gate ─────────────────────────────────────────────
        # Block any advance OUT of Stage 4 until alternatives were actually
        # presented — unless we hit a hard safety cap (avoid an endless stage).
        if self.current_stage == 4 and target > 4:
            cap_reached = self.turns_on_current_stage >= (self.STALL_THRESHOLD_STAGE4 + 2)
            # The cycle is complete only when every alternative has been both
            # presented AND reflected on (issue 006).
            cycle_done = self.stage4_cycle_complete(stage4_alternatives)
            if not (self.stage4_alternatives_presented and cycle_done) and not cap_reached:
                # Hold in Stage 4: either alternatives were not presented, or the
                # student has not yet reflected on each one.
                target = 4

        # Hard enforcement: directive fired but the agent did not move forward.
        # ── Required-parameter gate (issues 002/003/004) ─────────────────────
        # Do not leave a stage until the student has answered every required
        # question for it. A hard cap prevents an infinite stage if the student
        # never gives a recognisable answer.
        if target > self.current_stage:
            param_cap = self.turns_on_current_stage >= (self._stall_threshold() + 2)
            if not self.parameters_satisfied(self.current_stage) and not param_cap:
                target = self.current_stage

        if directive_was_active and target <= self.current_stage:
            # Do not force OUT of Stage 4 until content gate passes (or cap hit).
            blocked_by_gate = (
                self.current_stage == 4
                and not self.stage4_alternatives_presented
                and self.turns_on_current_stage < (self.STALL_THRESHOLD_STAGE4 + 2)
            )
            # Nor force out of a stage whose required questions are unanswered.
            blocked_by_params = (
                not self.parameters_satisfied(self.current_stage)
                and self.turns_on_current_stage < (self._stall_threshold() + 2)
            )
            if not blocked_by_gate and not blocked_by_params:
                forced = self.next_target_stage()
                if forced > self.current_stage:
                    target = forced
                    self.forced_advances += 1
                    self.completed_stages.add(self.current_stage)

        # If the agent moved forward, every stage strictly before the new target
        # is considered complete (it either gathered or skipped that info).
        if target > self.current_stage:
            for s in range(self.current_stage, target):
                self.completed_stages.add(s)

        # If the agent stayed on the current stage but marked it satisfied,
        # record completion so the next forward move is unblocked.
        if target == self.current_stage and stage_satisfied:
            self.completed_stages.add(self.current_stage)

        # Maintain the consecutive-turn counter for the stall directive.
        if target == self.current_stage:
            self.turns_on_current_stage += 1
        else:
            self.turns_on_current_stage = 1   # first turn on the new stage

        self.current_stage = target
        self.stage_history.append(target)
        return target

    def _stall_threshold(self) -> int:
        """
        Stage 4 runs a present-then-reflect cycle per method; Stage 5 compares
        them; Stages 2-3 must collect several required parameters one per turn.
        Each therefore gets a longer leash than the default.
        """
        if self.current_stage == 4:
            return self.STALL_THRESHOLD_STAGE4
        if self.current_stage == 5:
            return self.STALL_THRESHOLD_STAGE5
        if required_parameters(self.current_stage):
            return self.STALL_THRESHOLD_PARAM_STAGES
        return self.STALL_THRESHOLD

    def is_stalled(self) -> bool:
        """
        True when the agent has spent too many consecutive turns on the current
        stage and forward progress is both possible and warranted. Never fires
        on the final stage (there is nowhere to advance to).
        """
        if self.current_stage >= FINAL_STAGE:
            return False
        return self.turns_on_current_stage >= self._stall_threshold()

    def next_target_stage(self) -> int:
        """The stage the agent should advance to when stalled."""
        return min(self.current_stage + 1, FINAL_STAGE)

    def stage6_should_complete(self, student_understanding: int = 0,
                               learner_ready: bool = False) -> bool:
        """
        Natural completion at the final stage. Once the conversation has reached
        Stage 6 (Summary), the episode should end as soon as the student has
        synthesised their choice — we should NOT keep looping to max_turns.

        Completes when at Stage 6 AND any of:
          - the student signalled readiness (learner_ready), or
          - the student's understanding is high (>= 8), indicating they have
            articulated a confident, reasoned choice, or
          - we have spent enough turns on Stage 6 that a summary has clearly been
            exchanged (safety cap so it always terminates).
        """
        if self.current_stage < FINAL_STAGE:
            return False
        if learner_ready:
            return True
        if student_understanding >= 8:
            return True
        if self.turns_on_current_stage >= 3:   # safety cap on Stage 6 looping
            return True
        return False

    def expected_stage(self) -> int:
        """
        The stage the agent is expected to act in THIS turn: the next stage if a
        stall directive is in effect (so the prefill fallback advances rather than
        re-sticking), otherwise the current stage. Stage 4 is special — if the
        content gate has not yet been satisfied we expect it to STAY on Stage 4
        and do the presentation, not advance.
        """
        if self.current_stage < 4 and self.parameters_satisfied(self.current_stage):
            return min(self.current_stage + 1, FINAL_STAGE)
        if self.is_stalled():
            if self.current_stage == 4 and not self.stage4_alternatives_presented:
                return 4
            return self.next_target_stage()
        return self.current_stage

    def advance_after_student_reply(self) -> int:
        """
        Deterministically leave parameter-gathering stages once all required
        student information is present. This prevents the LLM from keeping the
        conversation in Stage 1/2/3 merely because it emitted STAGE_COMPLETE:NO.
        """
        while self.current_stage < 4 and self.parameters_satisfied(self.current_stage):
            self.completed_stages.add(self.current_stage)
            self.current_stage += 1
            self.turns_on_current_stage = 0
            self.stage_history.append(self.current_stage)
        return self.current_stage

    def mark_final_reached(self) -> bool:
        return self.current_stage >= FINAL_STAGE

    # ── User exit detection ───────────────────────────────────────────────────

    def check_user_exit(self, user_text: str) -> bool:
        if not user_text:
            return False
        low = user_text.lower()
        for pat in _EXIT_PATTERNS:
            if re.search(pat, low):
                self.user_requested_exit = True
                return True
        return False

    # ── Required-parameter tracking (issues 002/003/004) ──────────────────────

    def scan_student_parameters(self, stage: int, student_text: str) -> None:
        """
        Mark required parameters for `stage` as filled, based on what the STUDENT
        actually said. Called once per student turn, before advancing.

        Also completes the Stage 4 reflect phase: if the agent asked a feasibility
        question about a method and the student has now answered, the cycle turns
        back to 'present' so the next alternative can be introduced (issue 006).
        """
        if not student_text:
            return

        # Stage 4 present-then-reflect cycle: the student's reply ends the
        # reflect phase for the current method.
        if stage == 4 and self.stage4_phase == "reflect" and self.stage4_current_method:
            if len(student_text.strip()) > 15:   # a substantive reply, not "ok"
                self.stage4_mark_reflected()

        params = required_parameters(stage)
        if not params:
            return
        t = student_text.lower()
        filled = self.filled_parameters.setdefault(stage, set())
        substantive = self._is_substantive(student_text)
        for p in params:
            if p["id"] in filled:
                continue
            # Slots flagged `substantive` are satisfied by ANY real answer —
            # used where keyword matching cannot work (e.g. a research question,
            # which has unlimited valid phrasings).
            if p.get("substantive") and substantive:
                filled.add(p["id"])
                continue
            if any(kw in t for kw in p.get("detect", [])):
                filled.add(p["id"])

    # A reply counts as substantive if it is long enough to carry content and is
    # not merely a question back at the mentor or an expression of confusion.
    _NON_ANSWER_RE = re.compile(
        r"^\s*(?:sorry|pardon|what\?|huh|i don'?t understand|not sure what you mean|"
        r"can you (?:repeat|explain|clarify)|could you (?:repeat|explain|clarify)|"
        r"yes|no|ok(?:ay)?|thanks?|thank you)\b[\s.!?]*$",
        re.IGNORECASE,
    )

    @classmethod
    def _is_substantive(cls, text: str) -> bool:
        t = (text or "").strip()
        if len(t) < 20:
            return False
        if cls._NON_ANSWER_RE.match(t):
            return False
        # A reply that is only a question back to the mentor is not an answer.
        if t.endswith("?") and len(t) < 60:
            return False
        return True

    def missing_parameters(self, stage: int) -> List[Dict]:
        """
        Required parameters for `stage` the student has not yet answered AND that
        we have not already asked too many times.

        The ask cap matters: if a detector fails to recognise a valid answer, an
        uncapped loop would keep re-asking the same question in new words (this
        was issue 7 — "asks the same question again in a different format").
        After MAX_PARAM_ASKS attempts we accept that we've asked, stop demanding
        it, and let the conversation move on.
        """
        filled = self.filled_parameters.get(stage, set())
        out = []
        for p in required_parameters(stage):
            if p["id"] in filled:
                continue
            if self.parameter_ask_counts.get(p["id"], 0) >= self.MAX_PARAM_ASKS:
                continue          # asked enough; do not block the stage
            out.append(p)
        return out

    def parameters_satisfied(self, stage: int) -> bool:
        return not self.missing_parameters(stage)

    def _note_parameter_asked(self, param_id: str) -> int:
        """Record that the agent was directed to ask this; return the ask count."""
        self.parameter_ask_counts[param_id] = self.parameter_ask_counts.get(param_id, 0) + 1
        return self.parameter_ask_counts[param_id]

    # ── Stage 4 present/reflect cycle (issue 006) ─────────────────────────────

    def stage4_mark_presented(self, method: str) -> None:
        """The agent has just introduced `method`; next turn should reflect on it."""
        self.stage4_current_method = method
        self.stage4_phase = "reflect"

    def stage4_mark_reflected(self) -> None:
        """The student has reflected on the current method; move to the next one."""
        if self.stage4_current_method:
            self.stage4_methods_reflected.add(self.stage4_current_method)
        self.stage4_current_method = None
        self.stage4_phase = "present"

    def stage4_cycle_complete(self, stage4_alternatives) -> bool:
        """True when every alternative has been both presented AND reflected on."""
        if not stage4_alternatives:
            return self.stage4_alternatives_presented
        return len(self.stage4_methods_reflected) >= len(stage4_alternatives)

    # Salient method keywords used to compare two method descriptions.
    _METHOD_KEYWORDS = (
        "mixed method", "survey", "questionnaire", "interview", "focus group",
        "observation", "ethnograph", "case study", "experiment",
        "secondary", "document analysis", "content analysis",
        "grounded theory", "action research", "phenomenolog", "narrative",
        "discourse",
    )

    @classmethod
    def _method_keywords(cls, text: str) -> set:
        t = (text or "").lower()
        return {kw for kw in cls._METHOD_KEYWORDS if kw in t}

    @classmethod
    def _methods_match(cls, a: Optional[str], b: Optional[str]) -> bool:
        """
        True when `a` names essentially the SAME method as `b` — used to stop
        Stage 4 offering the student's own method back as an 'alternative'
        (issue 001).

        Compound methods must NOT match a single method they merely contain:
        "Mixed methods (survey + follow-up interviews)" is a genuinely different
        alternative from "semi-structured interviews", even though the word
        'interviews' appears in both. So `a` counts as a duplicate of `b` only
        when EVERY method keyword in `a` also appears in `b` (i.e. `a` introduces
        nothing new).
        """
        if not a or not b:
            return False
        ka, kb = cls._method_keywords(a), cls._method_keywords(b)

        if ka and kb:
            # 'mixed methods' is a distinct alternative in its own right: a
            # compound like "mixed methods (survey + interviews)" is NOT a repeat
            # of a student who proposed plain "interviews".
            if "mixed method" in ka or "mixed method" in kb:
                # They match only if BOTH are mixed-methods designs.
                return ("mixed method" in ka) and ("mixed method" in kb)
            return ka.issubset(kb)

        # Neither side names a recognised method — fall back to a strict
        # substring test (guards against odd free-text method names).
        al, bl = a.lower().strip(), b.lower().strip()
        return al == bl or al in bl or bl in al

    # ── Context block for the agent system prompt ─────────────────────────────

    def build_stage_context(self, comfort_zone: Optional[str] = None,
                            stage4_alternatives: Optional[List[Dict]] = None,
                            student_method: Optional[str] = None) -> str:
        """Produce the stage-awareness block injected into the agent prompt.

        student_method, if given, is the method the student proposed as their own
        (Stage 1/2). Stage 4 alternatives that match it are filtered out and the
        agent is explicitly told not to present the student's own method back to
        them as an alternative.
        """
        cur = STAGES[self.current_stage]
        lines: List[str] = []
        lines.append("## CONVERSATION STAGE FRAMEWORK (MethodCheck — 6 stages)")
        lines.append(
            "The conversation follows a 6-stage structure. You advance through "
            "stages based on CONTENT, not turn count. You may SKIP a stage if the "
            "student has already provided what it would gather. You may NOT go "
            "back to an earlier stage. Keep the conversation natural — do not "
            "announce stage numbers to the student.\n"
        )

        # Compact map of all stages with status markers.
        lines.append("Stage map (✓ done · ▶ current · · upcoming):")
        for n in range(FIRST_STAGE, FINAL_STAGE + 1):
            if n in self.completed_stages and n != self.current_stage:
                marker = "✓"
            elif n == self.current_stage:
                marker = "▶"
            else:
                marker = "·"
            lines.append(f"  {marker} Stage {n}: {STAGES[n]['name']}")
        lines.append("")

        # Detail for the current stage.
        lines.append(f"### YOU ARE IN STAGE {cur['number']}: {cur['name']}")

        # ── Hard stall directive (Fix 2) ──────────────────────────────────────
        if self.is_stalled():
            nxt = self.next_target_stage()
            nxt_name = STAGES[nxt]["name"]
            # Don't tell the agent to leave Stage 4 if it still hasn't presented
            # alternatives — instead, demand it DO the Stage 4 action now.
            if self.current_stage == 4 and not self.stage4_alternatives_presented:
                lines.append(
                    f"## ⚠ DO THE STAGE 4 ACTION NOW\n"
                    f"You have spent {self.turns_on_current_stage} turns in Stage 4 "
                    f"but have NOT yet presented alternative methods. You are still "
                    f"asking questions instead of PRESENTING options. This turn you "
                    f"MUST stop questioning and present the three alternative methods "
                    f"below, each with a one-line description and a similar-context "
                    f"example. This is the core of this stage.\n"
                )
            else:
                lines.append(
                    f"## ⚠ ADVANCE REQUIRED THIS TURN\n"
                    f"You have spent {self.turns_on_current_stage} consecutive turns in "
                    f"Stage {cur['number']} ({cur['name']}). The student has already "
                    f"provided what this stage needs. Staying here is an error. This "
                    f"turn you MUST set STAGE: {nxt} and begin Stage {nxt} "
                    f"({nxt_name}). Set STAGE_COMPLETE for Stage {cur['number']} to YES.\n"
                )

        # PRIMARY INSTRUCTION — the concrete action for this stage, up front.
        lines.append(f"## YOUR TASK THIS TURN\n{cur['action']}\n")
        lines.append(f"Purpose: {cur['purpose']}")
        lines.append(f"This stage is complete when: {cur['completion_criteria']}")

        # ── Required-question directive (issues 002/003/004) ─────────────────
        # The stage cannot complete until the student answers each required
        # question. Feed the agent exactly ONE per turn (compatible with the
        # one-question-per-turn guard).
        missing = self.missing_parameters(cur["number"])
        if missing:
            nxt_p = missing[0]
            asked = self._note_parameter_asked(nxt_p["id"])
            still = ", ".join(p["id"] for p in missing[1:]) or "none"
            block = [
                f"## ⚠ REQUIRED QUESTION — ASK THIS NOW",
                f"Stage {cur['number']} CANNOT complete until the student answers "
                f"this. Ask it as your SINGLE question this turn:",
                f'    "{nxt_p["question"]}"',
                f"  Outstanding after this: {still}.",
            ]
            if asked > 1:
                # Repeat ask — vary the phrasing and lean on retrieved literature.
                block.append(
                    f"  NOTE: you have already asked this {asked - 1} time(s) and the "
                    f"student has not answered it. Do NOT repeat the same wording. "
                    f"Rephrase it differently, and if background literature has been "
                    f"provided above, use it to give ONE brief concrete illustration "
                    f"that helps the student see what an answer might look like."
                )
            lines.append("\n".join(block) + "\n")

        # Stage-specific reminders.
        if cur["number"] == 4:
            cz = comfort_zone or "their stated comfort zone"
            # Never present the student's OWN proposed method back to them as an
            # 'alternative'. Filter it out of the preset list, and instruct the
            # agent directly (covers the free-form case with no preset list).
            filtered_alts = stage4_alternatives
            if stage4_alternatives and student_method:
                filtered_alts = [
                    alt for alt in stage4_alternatives
                    if not self._methods_match(alt.get("method", ""), student_method)
                ]
                # If filtering removed everything (misconfigured scenario), fall
                # back to the original list rather than presenting nothing.
                if not filtered_alts:
                    filtered_alts = stage4_alternatives

            if student_method:
                lines.append(
                    f"IMPORTANT: The student's OWN proposed method is "
                    f"\"{student_method}\". Do NOT present this (or a close variant "
                    f"of it) as one of the three alternatives — the alternatives "
                    f"must be genuinely DIFFERENT methods from what the student "
                    f"already chose. If you have already discussed their own method, "
                    f"the three alternatives are in addition to it."
                )

            # ── Present-then-reflect cycle (issue 006) ───────────────────────
            # Each method is PRESENTED (one turn), then REFLECTED on (feasibility
            # questions about that method), before the next method is introduced.
            if filtered_alts:
                remaining = []
                done = []
                for alt in filtered_alts:
                    m = alt.get("method", "")
                    fam = alt.get("family", "")
                    note = alt.get("note", "")
                    ml = m.lower()
                    seen = any(s.lower() in ml or ml in s.lower()
                               for s in self.stage4_methods_seen)
                    (done if seen else remaining).append((m, fam, note))

                if self.stage4_phase == "reflect" and self.stage4_current_method:
                    # We just introduced a method — now reflect on THAT method
                    # before introducing the next one.
                    cm = self.stage4_current_method
                    unused = [c for c in STAGE5_CONSTRAINTS
                              if c["key"] not in self._s4_asked_constraints]
                    pick = unused[0] if unused else STAGE5_CONSTRAINTS[0]
                    self._s4_asked_constraints.add(pick["key"])
                    lines.append(
                        f"REMINDER — REFLECT PHASE. You have just introduced "
                        f"\"{cm}\". Do NOT introduce another method yet.\n"
                        f"  This turn, ask the student ONE feasibility question about "
                        f"\"{cm}\" specifically, and then stop. Suggested angle "
                        f"({pick['key']}):\n"
                        f"    \"{pick['question']}\"\n"
                        f"  Once the student has reflected on this method, you will "
                        f"introduce the next alternative."
                    )
                    if remaining:
                        lines.append(f"  Still to introduce afterwards: "
                                     f"{', '.join(r[0] for r in remaining)}.")
                elif remaining:
                    nxt_m, nxt_fam, nxt_note = remaining[0]
                    lines.append(
                        f"REMINDER — PRESENT PHASE. Introduce EXACTLY ONE alternative "
                        f"this turn, then stop. Do NOT list the other alternatives.\n"
                        f"  Present THIS method now: {nxt_m} ({nxt_fam}) — {nxt_note}\n"
                        f"  You MUST include ALL THREE of these, briefly:\n"
                        f"    1. DESCRIPTION — what the method is, in one or two sentences.\n"
                        f"    2. COMMON APPLICATION — the kind of research question it "
                        f"typically suits.\n"
                        f"    3. PRACTICAL EXAMPLE — a study in a DIFFERENT research "
                        f"context from the student's own (never their topic).\n"
                        f"  Then ask ONE open question about how it might fit their "
                        f"research, and stop.\n"
                        f"  (At least one of the alternatives must lie outside the "
                        f"student's {cz} comfort zone.)"
                    )
                    if done:
                        names = ", ".join(d[0] for d in done)
                        lines.append(f"  Already covered: {names}. Still to come after "
                                     f"this: "
                                     f"{', '.join(r[0] for r in remaining[1:]) or 'none'}.")
                else:
                    lines.append(
                        "REMINDER: All alternatives have been introduced and reflected "
                        "on. You may advance to Stage 5 to COMPARE them against one "
                        "another and against the student's own original method."
                    )
            else:
                lines.append(
                    "REMINDER: Present alternative methods ONE AT A TIME. For each, give "
                    "(1) a brief description, (2) its common application, and (3) a "
                    "practical example from a DIFFERENT research context. Then ask ONE "
                    "feasibility question about that method before introducing the next. "
                    f"At least one method MUST be outside {cz}."
                )
        if cur["number"] == 5:
            lines.append(
                "REMINDER — Stage 5 is COMPARISON, not repetition. The student has "
                "already reflected on each method's feasibility in Stage 4. Now help "
                "them WEIGH the methods against one another and against their own "
                "original method, using the trade-offs they themselves raised. Ask ONE "
                "comparative question and stop. Do not re-ask the per-method "
                "feasibility questions, and never rank the methods yourself."
            )
        if cur["number"] == 6:
            lines.append(
                "REMINDER: Invite the student to summarise THEIR OWN choice and "
                "reasoning in their own words — do not summarise it for them, and do "
                "not tell them whether their choice is correct. Then encourage them "
                "to take this reasoning to their supervisor. Ask ONE question."
            )

        # Advancement instruction + output contract for the stage headers.
        lines.append("")
        lines.append(
            "When the current stage is complete, advance by setting STAGE to the "
            "next appropriate number (you may skip a stage if already satisfied). "
            "If the student goes quiet, is confused, or needs more support, STAY on "
            "the current stage and use a different pedagogical skill."
        )
        lines.append("")
        lines.append(GLOBAL_CONSTRAINTS)
        return "\n".join(lines)

    # ── Serialisable summary for logging ──────────────────────────────────────

    def summary(self) -> Dict:
        return {
            "final_stage": self.current_stage,
            "stage_history": list(self.stage_history),
            "completed_stages": sorted(self.completed_stages),
            "reached_final": self.mark_final_reached(),
            "stage_corrections": self.corrections,
            "forced_advances": self.forced_advances,
            "stage4_alternatives_presented": self.stage4_alternatives_presented,
            "stage4_methods_seen": sorted(self.stage4_methods_seen),
            "stage4_methods_reflected": sorted(self.stage4_methods_reflected),
            "stage4_phase": self.stage4_phase,
            "filled_parameters": {str(k): sorted(v)
                                  for k, v in self.filled_parameters.items()},
            "missing_parameters": {str(n): [p["id"] for p in self.missing_parameters(n)]
                                   for n in (1, 2, 3)
                                   if self.missing_parameters(n)},
            "parameter_ask_counts": dict(self.parameter_ask_counts),
            "user_requested_exit": self.user_requested_exit,
            "max_stage_reached": max(self.stage_history) if self.stage_history else FIRST_STAGE,
        }