"""
persona.py — Simulated learner persona (second LLM instance).
"""

import json
import re
from typing import Dict, List

from api_client import call_llm, call_llm_precise


def _system(scenario: Dict) -> str:
    p = scenario["learner_persona"]
    return f"""You are playing the role of a learner.

Name: {p['name']} | Level: {p['level']}
What you know: {p['knowledge_state']}
Your misconception (hold until genuinely corrected): {p['misconception']}
Emotional state: {p['emotional_state']}
Your learning goal: {p['learning_goal']}
Topic: {scenario['topic']}

## How to behave
- Respond naturally as this learner — 2-4 sentences typically.
- Update understanding GRADUALLY as explanations land. Do NOT suddenly understand everything.
- If an explanation was unclear or didn't address your confusion, stay confused and say so specifically.
- When you genuinely understand, show it by explaining in your own words.
- Show your emotional state naturally (nervousness, curiosity, frustration).

## Hidden metadata — write these FIRST, they are stripped before showing to the agent:
UNDERSTANDING_LEVEL: <0-10>  (0=lost, 10=fully understand and can apply independently)
LEARNER_READY: YES           (only when level is 9 or 10 AND you can demonstrate it)
"""


def persona_respond(scenario: Dict, history: List[Dict]) -> Dict:
    raw = call_llm(
        messages=history,
        system=_system(scenario),
        max_tokens=350,
        temperature=0.75,
        role="persona",
    )
    level, ready, lines = 0, False, []
    for line in raw.strip().splitlines():
        s = line.strip()
        if s.startswith("UNDERSTANDING_LEVEL:"):
            try:   level = int(re.search(r"\d+", s).group())
            except: pass
        elif s.startswith("LEARNER_READY:"):
            ready = "YES" in s.upper()
        else:
            lines.append(line)
    return {
        "response":            "\n".join(lines).strip(),
        "understanding_level": level,
        "learner_ready":       ready,
        "raw_output":          raw,
    }


def persona_fill_survey(
    scenario: Dict,
    history: List[Dict],
    survey_questions: List[Dict],
    task_solved: bool,
    total_turns: int,
) -> Dict:
    p = scenario["learner_persona"]
    convo = "\n".join(
        f"{m['role'].upper()}: {m['content'][:180]}{'…' if len(m['content'])>180 else ''}"
        for m in history
    )
    qs = "\n".join(f"{q['id']}: {q['question']} [{q['scale']}]" for q in survey_questions)
    system = f"""You are {p['name']}, a learner who just finished a session.
Profile: {p['knowledge_state']}
Goal: {p['learning_goal']}
Session: {total_turns} turns. Task achieved: {'Yes' if task_solved else 'No'}.
Reply ONLY with valid JSON — no other text:
{{
  "Q1": {{"score": <1-5>, "comment": "<one sentence>"}},
  "Q2": {{"score": <1-5>, "comment": "<one sentence>"}},
  "Q3": {{"score": <1-5>, "comment": "<one sentence>"}},
  "Q4": {{"score": <1-5>, "comment": "<one sentence>"}},
  "Q5": {{"score": <1-5>, "comment": "<one sentence>"}},
  "Q_open": {{"score": null, "comment": "<1-2 sentences: most helpful + could be better>"}}
}}
Be honest. Reflect your actual experience."""

    prompt = f"Conversation:\n{convo}\n\nSurvey:\n{qs}"
    raw = call_llm_precise(
        messages=[{"role": "user", "content": prompt}],
        system=system,
        max_tokens=500,
    )
    try:
        data = json.loads(re.sub(r"```json|```", "", raw).strip())
    except Exception:
        data = {q["id"]: {"score": 3, "comment": "parse error"} for q in survey_questions}
        data["Q_open"] = {"score": None, "comment": raw[:200]}
    return {"survey": data, "raw": raw}


def persona_task_check(scenario: Dict, history: List[Dict]) -> Dict:
    p  = scenario["learner_persona"]
    system = f"""You are {p['name']}.
Goal: {p['learning_goal']}
Task solved if: {scenario['task_solved_criteria']}
Reply ONLY in JSON: {{"solved": true/false, "confidence": <0-10>, "evidence": "<one sentence>"}}"""
    msgs = history + [{"role": "user", "content":
        "Based on this conversation, can you now complete the task? Be honest."}]
    raw = call_llm_precise(messages=msgs, system=system, max_tokens=150)
    try:
        return json.loads(re.sub(r"```json|```", "", raw).strip())
    except Exception:
        return {"solved": False, "confidence": 0, "evidence": raw[:150]}
