"""
agent.py — Pedagogical agent. Selects a skill each turn and responds.
"""

import re
from typing import Dict, List, Tuple, Optional

from api_client import call_llm
from skill_loader import build_skill_index, get_skill_body, list_skill_names


def _system_prompt(skills: Dict, scenario: Dict, recent_skills: List[str]) -> str:
    p = scenario["learner_persona"]
    lines = [
        f"You are an expert pedagogical agent. Role: {scenario['role'].upper()}.\n",
        f"## Scenario\nTopic: {scenario['topic']}\nTask: {scenario['task_description']}\n",
        f"## Learner Profile\n"
        f"Name: {p['name']} | Level: {p['level']}\n"
        f"Knowledge: {p['knowledge_state']}\n"
        f"Misconception: {p['misconception']}\n"
        f"Emotional state: {p['emotional_state']}\n"
        f"Goal: {p['learning_goal']}\n",
        "## Objective\n"
        "Help this learner reach their goal using the MINIMUM turns necessary.\n"
        "Every response must be pedagogically purposeful.\n"
        "You are scored on: task solved + fewest turns + learner survey rating.\n",
    ]
    if recent_skills:
        lines.append(
            "## Recent skills used (avoid repeating unnecessarily):\n" +
            "\n".join(f"  - {s}" for s in recent_skills[-3:]) + "\n"
        )
    lines.append(build_skill_index(skills))
    return "\n".join(lines)


def _parse(raw: str) -> Tuple[Optional[str], Optional[str], str, bool]:
    """Parse SKILL / REASONING / TASK_SOLVED header lines out of raw response."""
    skill, reasoning, task_solved = None, None, False
    body_lines = []
    for line in raw.strip().splitlines():
        s = line.strip()
        if s.startswith("SKILL:"):
            skill = s.split("SKILL:", 1)[1].strip()
        elif s.startswith("REASONING:"):
            reasoning = s.split("REASONING:", 1)[1].strip()
        elif s.startswith("TASK_SOLVED:"):
            task_solved = "YES" in s.upper()
        else:
            body_lines.append(line)
    return skill, reasoning, "\n".join(body_lines).strip(), task_solved


def agent_turn(
    skills: Dict,
    scenario: Dict,
    conversation_history: List[Dict],
    previous_skills: List[str],
    turn_number: int,
) -> Dict:
    """
    Run one agent turn.
    Returns: skill_name, reasoning, response, task_solved, raw_output
    """
    system  = _system_prompt(skills, scenario, previous_skills)
    raw     = call_llm(
        messages=conversation_history,
        system=system,
        max_tokens=800,
        temperature=0.6,
        role="agent",
    )
    skill, reasoning, response, task_solved = _parse(raw)

    # fuzzy-match skill name if needed
    if skill:
        names = list_skill_names(skills)
        if skill not in skills:
            for n in names:
                if skill.lower() in n.lower() or n.lower() in skill.lower():
                    skill = n
                    break

    return {
        "skill_name":   skill or "unknown",
        "reasoning":    reasoning or "",
        "response":     response,
        "task_solved":  task_solved,
        "raw_output":   raw,
    }
