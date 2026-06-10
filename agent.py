"""
agent.py — Pedagogical agent (supervisor Aoife) with skill + stage awareness.

Combines:
  - Robust SKILL:/REASONING:/TASK_SOLVED: header parsing (scans all lines).
  - STAGE:/STAGE_COMPLETE: headers for the 6-stage MethodCheck framework.
  - Token sanitisation (strips Qwen chat-template tokens that leak into output).
  - Hard skill-diversity ban after 3 consecutive uses of the same skill.

The agent now produces FIVE header lines, then the response body:
    SKILL: <skill-name>
    REASONING: <one sentence>
    STAGE: <1-6>
    STAGE_COMPLETE: <YES|NO>
    TASK_SOLVED: <YES|NO>
    [response body]
"""

import re
from typing import Dict, List, Tuple, Optional

from api_client import call_llm
from skill_loader import build_skill_index, get_skill_body, list_skill_names
from stages import FINAL_STAGE


# ── Token sanitizer ───────────────────────────────────────────────────────────

_SPECIAL_TOKEN_RE = re.compile(
    r"<\|im_start\|>|<\|im_end\|>|<\|endoftext\|>|<\|assistant\|>|"
    r"<\|user\|>|<\|system\|>|<s>|</s>",
    re.IGNORECASE,
)

def _sanitize(text: str) -> str:
    return _SPECIAL_TOKEN_RE.sub("", text).strip()


# ── System prompt ─────────────────────────────────────────────────────────────

def _system_prompt(
    skills: Dict,
    scenario: Dict,
    recent_skills: List[str],
    stage_context: str,
) -> str:
    p = scenario["learner_persona"]
    lines = [
        f"You are an expert pedagogical agent acting as a research-methods mentor. "
        f"Role: {scenario['role'].upper()}.\n",
        f"## Scenario\nTopic: {scenario['topic']}\nTask: {scenario['task_description']}\n",
        f"## Learner profile\n"
        f"Name: {p['name']} | Level: {p['level']}\n"
        f"Knowledge: {p['knowledge_state']}\n"
        f"Misconception to address: {p['misconception']}\n"
        f"Emotional state: {p['emotional_state']}\n"
        f"Learning goal: {p['learning_goal']}\n",
    ]

    # The stage framework is the structural backbone of the conversation.
    lines.append(stage_context)
    lines.append("")

    lines.append(
        "## CRITICAL OUTPUT FORMAT — follow exactly every turn\n"
        "Your response MUST begin with these FIVE header lines, in this order, "
        "before any other text:\n\n"
        "SKILL: <exact-skill-name-from-list>\n"
        "REASONING: <one sentence: why this skill AND this stage right now>\n"
        "STAGE: <the stage number 1-6 you are acting in this turn>\n"
        "STAGE_COMPLETE: <YES if the current stage's goal is now met, else NO>\n"
        "TASK_SOLVED: <YES only when the whole 6-stage conversation has reached "
        "its natural end, else NO>\n\n"
        "Then write your mentor response to the learner.\n"
        "Do NOT put any text before the SKILL: line. Do NOT announce stage "
        "numbers to the student in the body.\n\n"
        "Example of correct format:\n"
        "SKILL: probe-intended-decisions\n"
        "REASONING: Opening the conversation — Stage 1 needs the student's question and tentative method.\n"
        "STAGE: 1\n"
        "STAGE_COMPLETE: NO\n"
        "TASK_SOLVED: NO\n\n"
        "[Your mentor response to the learner here]\n"
    )

    lines.append(
        "## Objective\n"
        "Guide the learner through the 6-stage reflective comparison so they reach "
        "Stage 6 with a confident, self-justified methodological view. Keep the "
        "dialogue natural and unhurried, but always be progressing the structure. "
        "You are scored on: reaching the final stage + learner survey rating + "
        "efficient, non-repetitive progress.\n"
    )

    # Skill diversity: hard ban after 3 consecutive identical skills.
    if recent_skills:
        last = recent_skills[-1]
        consecutive = 0
        for s in reversed(recent_skills):
            if s == last:
                consecutive += 1
            else:
                break
        if consecutive >= 3:
            lines.append(
                f"## ⚠ SKILL BANNED THIS TURN\n"
                f"You have used '{last}' for {consecutive} turns in a row. "
                f"You MUST choose a DIFFERENT skill this turn. Reusing '{last}' is an error.\n"
            )
        else:
            lines.append(
                "## Recent skills used (avoid repeating the same skill 3 turns in a row):\n"
                + "\n".join(f"  - {s}" for s in recent_skills[-4:]) + "\n"
            )

    lines.append(build_skill_index(skills))
    return "\n".join(lines)


# ── Response parser ───────────────────────────────────────────────────────────

def _parse(raw: str, valid_skills: List[str]) -> Dict:
    """
    Sanitize then scan ALL lines for the five header types. Returns a dict with
    skill_name, reasoning, stage, stage_complete, task_solved, response.
    """
    raw = _sanitize(raw)
    skill: Optional[str] = None
    reasoning: Optional[str] = None
    stage: Optional[int] = None
    stage_complete = False
    task_solved = False
    body_lines: List[str] = []

    for line in raw.strip().splitlines():
        s = line.strip()
        upper = s.upper()
        if upper.startswith("SKILL:"):
            raw_skill = s[len("SKILL:"):].strip().strip("*`\"'")
            if raw_skill in valid_skills:
                skill = raw_skill
            else:
                lower = raw_skill.lower()
                for v in valid_skills:
                    if v.lower() == lower:
                        skill = v; break
                if not skill:
                    for v in valid_skills:
                        if lower in v.lower() or v.lower() in lower:
                            skill = v; break
        elif upper.startswith("REASONING:"):
            reasoning = s[len("REASONING:"):].strip()
        elif upper.startswith("STAGE_COMPLETE:"):
            stage_complete = "YES" in upper
        elif upper.startswith("STAGE:"):
            m = re.search(r"\d+", s)
            if m:
                stage = max(1, min(FINAL_STAGE, int(m.group())))
        elif upper.startswith("TASK_SOLVED:"):
            task_solved = "YES" in upper
        else:
            body_lines.append(line)

    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)

    return {
        "skill": skill,
        "reasoning": reasoning,
        "stage": stage,
        "stage_complete": stage_complete,
        "task_solved": task_solved,
        "response": "\n".join(body_lines).strip(),
    }


# ── Agent turn ────────────────────────────────────────────────────────────────

def agent_turn(
    skills: Dict,
    scenario: Dict,
    conversation_history: List[Dict],
    previous_skills: List[str],
    turn_number: int,
    stage_context: str = "",
) -> Dict:
    """
    Run one agent turn.
    Returns: skill_name, reasoning, declared_stage, stage_complete,
             response, task_solved, raw_output.
    """
    system       = _system_prompt(skills, scenario, previous_skills, stage_context)
    valid_skills = list_skill_names(skills)

    raw = call_llm(
        messages=conversation_history,
        system=system,
        max_tokens=1100,
        temperature=0.6,
        role="agent",
    )

    parsed = _parse(raw, valid_skills)

    skill = parsed["skill"]
    if not skill:
        skill = previous_skills[-1] if previous_skills else valid_skills[0]

    return {
        "skill_name":     skill,
        "reasoning":      parsed["reasoning"] or "",
        "declared_stage": parsed["stage"],          # may be None
        "stage_complete": parsed["stage_complete"],
        "response":       parsed["response"],
        "task_solved":    parsed["task_solved"],
        "raw_output":     raw,
    }
