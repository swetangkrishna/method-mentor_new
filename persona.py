"""
persona.py — Simulated learner persona, now stage-aware for MethodCheck.

Combines all prior fixes:
  - Assistant prefill forces UNDERSTANDING_LEVEL: to appear.
  - Token sanitisation strips chat-template leaks.
  - Empty-body fallback uses a minimal no-format call.
And adds stage awareness: the persona behaves differently depending on which
of the 6 conversation stages the mentor is currently in, so the simulated
student supplies the right kind of information at the right point (research
question in Stage 1, background in Stage 2, reflection in Stage 5, etc.).
"""

import json
import re
from typing import Dict, List, Optional

from api_client import call_llm, call_llm_precise

_PERSONA_PREFILL = "UNDERSTANDING_LEVEL: "

_SPECIAL_TOKEN_RE = re.compile(
    r"<\|im_start\|>|<\|im_end\|>|<\|endoftext\|>|<\|assistant\|>|"
    r"<\|user\|>|<\|system\|>|<s>|</s>",
    re.IGNORECASE,
)

def _sanitize(text: str) -> str:
    return _SPECIAL_TOKEN_RE.sub("", text).strip()


# Per-stage guidance for how the student should behave this turn.
_STAGE_BEHAVIOUR = {
    1: "The mentor is asking about your research question and tentative method. "
       "Share your research question and the method you are leaning toward (or say "
       "you are unsure). Keep it brief and natural.",
    2: "The mentor is asking about your programme and background. Tell them your "
       "programme, year, and whether you feel more comfortable with qualitative or "
       "quantitative methods.",
    3: "The mentor is helping clarify your research question. Answer their questions "
       "about whether your aim is exploratory/explanatory/evaluative, what data you "
       "would need, and what kind of evidence convinces you. It is fine to be a bit "
       "unsure and think aloud.",
    4: "The mentor is presenting alternative methods you had not focused on. React "
       "naturally — curiosity, mild surprise, or hesitation. You may not have "
       "considered some of these. Do not instantly accept or reject them.",
    5: "The mentor is helping you reflect on how well each method fits, one at a "
       "time (timeline, access, skills, ethics, alignment). Think through each "
       "honestly in relation to YOUR situation. This is where your understanding "
       "should grow as things click into place.",
    6: "The mentor is asking you to summarise which method now seems most suitable "
       "and why. Give your own synthesis in your own words, with at least one "
       "reason. Show your increased confidence.",
}


def _system(scenario: Dict, current_stage: int, prev_level: Optional[int]) -> str:
    p = scenario["learner_persona"]
    sp = scenario.get("stage_profile", {})
    prev_hint = (
        f"Your understanding was {prev_level}/10 last turn. "
        f"Only increase it if something genuinely clicked this turn.\n"
    ) if prev_level is not None else ""

    stage_behaviour = _STAGE_BEHAVIOUR.get(current_stage, "")

    profile_facts = ""
    if sp:
        profile_facts = (
            "\nFACTS ABOUT YOUR RESEARCH (use these consistently when relevant):\n"
            f"- Research question: {sp.get('research_question', 'unspecified')}\n"
            f"- Method you are leaning toward: {sp.get('tentative_method', 'unsure')}\n"
            f"- You are more comfortable with: {sp.get('comfort_zone', 'unspecified')} methods\n"
            f"- Your programme: {sp.get('programme', p['level'])}\n"
        )

    return f"""You are {p['name']}, a student in a reflective conversation with a research-methods mentor. Respond ONLY as this student.

YOUR PROFILE
Name      : {p['name']}
Level     : {p['level']}
Knowledge : {p['knowledge_state']}
Misconception: {p['misconception']}
Emotional state: {p['emotional_state']}
Learning goal: {p['learning_goal']}
Topic: {scenario['topic']}
{profile_facts}{prev_hint}
WHAT IS HAPPENING RIGHT NOW (conversation stage {current_stage}):
{stage_behaviour}

OUTPUT FORMAT (mandatory every turn — the first line is already started for you)
UNDERSTANDING_LEVEL: <integer 0-10>
LEARNER_READY: NO
<2-4 sentences as {p['name']} — natural student voice>

Write LEARNER_READY: YES only when your understanding is 9-10 AND you have given your own reasoned summary of your chosen method (this only happens near the end).

RULES
- React to what the mentor just said. Stay in character as a real student.
- Provide the information the current stage is asking for.
- If something clicked, show it by explaining it back in plain words.
- If you are still unsure, say so honestly — do NOT pretend to understand.
- 2-4 sentences only. No lists. No headers. No bullet points.
- NEVER ask the mentor teaching questions. NEVER write like a mentor or expert.
- Understanding grows slowly: start 2-4, only reach 8+ when things genuinely fit together.
- YOU MUST ALWAYS WRITE 2-4 SENTENCES AFTER THE HEADERS — never leave the body blank.

EXAMPLE CORRECT RESPONSE
UNDERSTANDING_LEVEL: 3
LEARNER_READY: NO
My question is about how teachers perceive digital tools in geography, and I was thinking semi-structured interviews. I haven't really thought about other methods though, so I'm a bit unsure if that's the right call."""


def _parse_raw(raw: str, prev_level: Optional[int]) -> Dict:
    raw = _sanitize(raw)
    level_found = False
    level = 0
    ready = False
    body_lines: List[str] = []

    for line in raw.strip().splitlines():
        s = line.strip()
        upper = s.upper()
        if upper.startswith("UNDERSTANDING_LEVEL:"):
            m = re.search(r"\d+", s)
            if m:
                level = max(0, min(10, int(m.group())))
                level_found = True
        elif upper.startswith("LEARNER_READY:"):
            ready = "YES" in upper
        else:
            body_lines.append(line)

    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)

    if not level_found:
        level = max(1, (prev_level or 1) - 1)
        print(f"  [persona] ⚠ UNDERSTANDING_LEVEL missing — carried forward {level}/10")

    return {
        "response":            "\n".join(body_lines).strip(),
        "understanding_level": level,
        "learner_ready":       ready,
        "raw_output":          raw,
        "level_found":         level_found,
    }


def persona_respond(
    scenario: Dict,
    history: List[Dict],
    current_stage: int = 1,
    prev_level: Optional[int] = None,
) -> Dict:
    p = scenario["learner_persona"]

    raw = call_llm(
        messages=history,
        system=_system(scenario, current_stage, prev_level),
        max_tokens=350,
        temperature=0.7,
        role="persona",
        prefill=_PERSONA_PREFILL,
    )
    result = _parse_raw(raw, prev_level)

    # Empty-body fallback: minimal no-format call.
    if not result["response"]:
        print(f"  [persona] ⚠ Empty body (understanding={result['understanding_level']}/10) "
              f"— using minimal fallback call")
        fallback_system = (
            f"You are {p['name']}, a {p['level']}.\n"
            f"React to what your mentor just said in 2-3 sentences.\n"
            f"Use a natural student voice. No headers, no bullet points, "
            f"no questions back to the mentor. Just your honest reaction."
        )
        fallback_raw = call_llm(
            messages=history,
            system=fallback_system,
            max_tokens=120,
            temperature=0.85,
            role="persona",
            prefill="I ",
        )
        fallback_body = _sanitize(fallback_raw).strip()
        fallback_body = "\n".join(
            ln for ln in fallback_body.splitlines()
            if not ln.strip().upper().startswith(("UNDERSTANDING_LEVEL:", "LEARNER_READY:"))
        ).strip()
        if fallback_body:
            result["response"] = fallback_body
        else:
            print(f"  [persona] ⚠ Fallback also empty — leaving blank")

    return result


def persona_fill_survey(
    scenario: Dict,
    history: List[Dict],
    survey_questions: List[Dict],
    task_solved: bool,
    total_turns: int,
) -> Dict:
    p = scenario["learner_persona"]
    convo = "\n".join(
        f"{m['role'].upper()}: {m['content'][:200]}{'…' if len(m['content']) > 200 else ''}"
        for m in history
    )
    qs = "\n".join(
        f"{q['id']}: {q['question']} [{q['scale']}]" for q in survey_questions
    )
    system = f"""You are {p['name']}, a learner who just finished a research-methods mentoring session.
Your profile: {p['knowledge_state']}
Your learning goal was: {p['learning_goal']}
Session: {total_turns} turns. Reached a confident conclusion: {'Yes' if task_solved else 'No'}.

Reply ONLY with valid JSON — no markdown, no other text, no code fences:
{{
  "Q1": {{"score": <1-5>, "comment": "<one sentence>"}},
  "Q2": {{"score": <1-5>, "comment": "<one sentence>"}},
  "Q3": {{"score": <1-5>, "comment": "<one sentence>"}},
  "Q4": {{"score": <1-5>, "comment": "<one sentence>"}},
  "Q5": {{"score": <1-5>, "comment": "<one sentence>"}},
  "Q_open": {{"score": null, "comment": "<1-2 sentences: most helpful + could be better>"}}
}}
Be honest. If the session was inefficient or confusing, reflect that in the scores."""

    raw = call_llm_precise(
        messages=[{"role": "user", "content": f"Conversation:\n{convo}\n\nSurvey:\n{qs}"}],
        system=system,
        max_tokens=500,
    )
    try:
        clean = re.sub(r"```json|```", "", raw).strip()
        data  = json.loads(clean)
    except Exception:
        data = {q["id"]: {"score": 3, "comment": "parse error"} for q in survey_questions}
        data["Q_open"] = {"score": None, "comment": raw[:200]}

    return {"survey": data, "raw": raw}


def persona_task_check(scenario: Dict, history: List[Dict]) -> Dict:
    p = scenario["learner_persona"]
    system = f"""You are {p['name']}.
Your learning goal: {p['learning_goal']}
The task is solved when: {scenario['task_solved_criteria']}
Reply ONLY in JSON (no other text):
{{"solved": true/false, "confidence": <0-10>, "evidence": "<one sentence what you can/cannot do>"}}"""

    msgs = history + [{
        "role": "user",
        "content": "Based on this conversation, can you now complete the task? Be honest."
    }]
    raw = call_llm_precise(messages=msgs, system=system, max_tokens=150)
    try:
        return json.loads(re.sub(r"```json|```", "", raw).strip())
    except Exception:
        return {"solved": False, "confidence": 0, "evidence": raw[:150]}
