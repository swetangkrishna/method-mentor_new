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
    STAGE5_CONSTRAINTS, stage_name,
)

# Phrases that signal the user wants to stop (checked case-insensitively as
# whole-ish fragments). Kept conservative to avoid false positives.
_EXIT_PATTERNS = [
    r"\bstop here\b",
    r"\bthat'?s enough\b",
    r"\bi(?:'| a)?m done\b",
    r"\bi need to go\b",
    r"\blet'?s stop\b",
    r"\bend (?:the )?(?:conversation|session|chat)\b",
    r"\bi'?ll (?:stop|leave) (?:here|now)\b",
    r"\bgot to go\b",
    r"\bgotta go\b",
    r"\bno more questions\b",
    r"\bthank you,? (?:that'?s all|goodbye|bye)\b",
]


class StageTracker:
    # After this many consecutive turns on the same stage, the tracker emits a
    # hard "advance now" directive (mirrors the agent's skill-ban mechanism).
    STALL_THRESHOLD = 3
    # Stage 5 (reflective comparison) legitimately spans several turns — one per
    # method — so it gets a higher stall threshold before being pushed forward.
    STALL_THRESHOLD_STAGE5 = 5

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
            self._scan_stage4_content(response_text, stage4_alternatives)

        directive_was_active = self.is_stalled()
        target = self.legal_next(declared)

        # ── Stage 4 content gate ─────────────────────────────────────────────
        # Block any advance OUT of Stage 4 until alternatives were actually
        # presented — unless we hit a hard safety cap (avoid an endless stage).
        if self.current_stage == 4 and target > 4:
            cap_reached = self.turns_on_current_stage >= (self.STALL_THRESHOLD_STAGE5 + 2)
            if not self.stage4_alternatives_presented and not cap_reached:
                # Hold in Stage 4: the agent claimed to move on without doing the
                # core MethodCheck action. Keep it here to actually present them.
                target = 4

        # Hard enforcement: directive fired but the agent did not move forward.
        if directive_was_active and target <= self.current_stage:
            # Do not force OUT of Stage 4 until content gate passes (or cap hit).
            blocked_by_gate = (
                self.current_stage == 4
                and not self.stage4_alternatives_presented
                and self.turns_on_current_stage < (self.STALL_THRESHOLD_STAGE5 + 2)
            )
            if not blocked_by_gate:
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
        """Stage 5 gets a longer leash (multi-method reflection)."""
        from stages import FINAL_STAGE as _F  # local import to avoid cycle risk
        if self.current_stage == 5:
            return self.STALL_THRESHOLD_STAGE5
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

    # ── Context block for the agent system prompt ─────────────────────────────

    def build_stage_context(self, comfort_zone: Optional[str] = None,
                            stage4_alternatives: Optional[List[Dict]] = None) -> str:
        """Produce the stage-awareness block injected into the agent prompt."""
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

        # Stage-specific reminders.
        if cur["number"] == 4:
            cz = comfort_zone or "their stated comfort zone"
            if stage4_alternatives:
                method_lines = []
                for alt in stage4_alternatives:
                    m = alt.get("method", "")
                    fam = alt.get("family", "")
                    note = alt.get("note", "")
                    method_lines.append(f"    • {m} ({fam}) — {note}")
                methods_block = "\n".join(method_lines)
                already = ("You have already named some; make sure all three are "
                           "covered." if self.stage4_methods_seen else
                           "You have NOT presented any yet — do it now.")
                lines.append(
                    "REMINDER — PRESENT these THREE specific alternatives (do NOT just "
                    "ask the student about them; describe each one TO the student):\n"
                    f"{methods_block}\n"
                    f"  At least one is outside the student's {cz} comfort zone. Give "
                    f"each a one-line description and a brief similar-context example. "
                    f"{already}"
                )
            else:
                lines.append(
                    f"REMINDER: Present THREE alternative methods. At least one MUST be "
                    f"outside {cz}. Give a brief description, application, and a similar-"
                    f"context example for each. Discuss one method at a time."
                )
        if cur["number"] == 5:
            qs = "; ".join(c["question"] for c in STAGE5_CONSTRAINTS[:3])
            lines.append(
                "REMINDER: Ask reflective feasibility questions ONE METHOD AT A TIME "
                "and ONE QUESTION AT A TIME. Example constraint questions: " + qs
            )
        if cur["number"] == 6:
            lines.append(
                "REMINDER: Invite the student to summarise their own choice and "
                "reasoning. Then encourage them to take this to their supervisor."
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
            "user_requested_exit": self.user_requested_exit,
            "max_stage_reached": max(self.stage_history) if self.stage_history else FIRST_STAGE,
        }