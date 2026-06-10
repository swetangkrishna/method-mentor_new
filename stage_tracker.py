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
    def __init__(self) -> None:
        self.current_stage: int = FIRST_STAGE
        self.stage_history: List[int] = []          # one entry per agent turn
        self.completed_stages: set = set()
        self.corrections: int = 0                    # illegal-transition count
        self.user_requested_exit: bool = False

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

    def advance(self, declared: Optional[int], stage_satisfied: bool) -> int:
        """
        Record one agent turn. `declared` is the STAGE: header the agent emitted.
        `stage_satisfied` indicates the agent marked the current stage complete
        (via STAGE_COMPLETE: YES). Returns the stage now in effect.
        """
        target = self.legal_next(declared)

        # If the agent moved forward, every stage strictly before the new target
        # is considered complete (it either gathered or skipped that info).
        if target > self.current_stage:
            for s in range(self.current_stage, target):
                self.completed_stages.add(s)

        # If the agent stayed on the current stage but marked it satisfied,
        # record completion so the next forward move is unblocked.
        if target == self.current_stage and stage_satisfied:
            self.completed_stages.add(self.current_stage)

        self.current_stage = target
        self.stage_history.append(target)
        return target

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

    def build_stage_context(self, comfort_zone: Optional[str] = None) -> str:
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
        lines.append(f"What to do now: {cur['action']}")
        lines.append(f"Why: {cur['purpose']}")
        lines.append(f"This stage is complete when: {cur['completion_criteria']}")

        # Stage-specific reminders.
        if cur["number"] == 4:
            cz = comfort_zone or "their stated comfort zone"
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
            "user_requested_exit": self.user_requested_exit,
            "max_stage_reached": max(self.stage_history) if self.stage_history else FIRST_STAGE,
        }
