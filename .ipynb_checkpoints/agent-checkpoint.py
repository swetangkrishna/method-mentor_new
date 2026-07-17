"""
agent.py — Pedagogical agent (supervisor Aoife) with skill + stage awareness.

Combines:
  - Robust SKILL:/REASONING:/TASK_SOLVED: header parsing (scans all lines).
  - STAGE:/STAGE_COMPLETE: headers for the 6-stage MethodCheck framework.
  - Token sanitisation (strips Qwen chat-template tokens that leak into output).
  - Hard skill-diversity ban after 3 consecutive uses of the same skill.

The agent now produces SIX structured fields, ending with an explicit RESPONSE: boundary:
    SKILL: <skill-name>
    REASONING: <one sentence>
    STAGE: <1-6>
    STAGE_COMPLETE: <YES|NO>
    TASK_SOLVED: <YES|NO>
    RESPONSE: <student-facing response>
"""

import re
from typing import Dict, List, Tuple, Optional

from api_client import call_llm
from skill_loader import build_skill_index, get_skill_body, list_skill_names
from stages import FINAL_STAGE


# ── Token sanitizer ───────────────────────────────────────────────────────────

# Chat-template special tokens from BOTH model families. The original list was
# Qwen-only (<|im_*|>); Llama-3.1 uses <|eot_id|> / <|start_header_id|> etc., so
# those leaked into the chat verbatim after the model swap.
# Llama-3.1 emits role headers as a THREE-part construct:
#   <|start_header_id|>user<|end_header_id|>
# Removing the tokens individually leaves the bare role word ("user") stranded
# mid-line, where the line-based leak stripper cannot see it. So kill the whole
# construct first, as one unit.
_ROLE_HEADER_RE = re.compile(
    r"<\|start_header_id\|>\s*\w*\s*<\|end_header_id\|>"      # Llama-3.1
    r"|<\|im_start\|>\s*(?:system|user|assistant)\b"          # Qwen2.5
    r"|<\|(?:system|user|assistant)\|>",                      # generic
    re.IGNORECASE)

_SPECIAL_TOKEN_RE = re.compile(
    r"<\|im_start\|>|<\|im_end\|>|<\|endoftext\|>|<\|assistant\|>|"
    r"<\|user\|>|<\|system\|>|<s>|</s>|"
    r"<\|eot_id\|>|<\|bot_id\|>|<\|begin_of_text\|>|<\|end_of_text\|>|"
    r"<\|start_header_id\|>|<\|end_header_id\|>|<\|finetune_right_pad_id\|>|"
    r"<\|python_tag\|>|<\|eom_id\|>",
    re.IGNORECASE,
)

# Lines where the model has started writing the OTHER speaker's turn. Everything
# from such a line onward is fabricated dialogue and is dropped. Prompt ECHOES
# are handled separately by _strip_prompt_echo (they need removing, not cutting,
# because the genuine reply usually follows them).
_LEAK_LINE_RE = re.compile(
    r"^\s*(?:"
    r"(?:user|student|human|mentor|aoife|assistant|teacher|supervisor)\s*:"   # role headers
    r"|\[T\d+\]"                                                              # transcript markers
    r")",
    re.IGNORECASE,
)


def _cut_impersonation(text: str) -> str:
    """
    Cut the response at the first line where the model starts writing the OTHER
    speaker's turn. Everything after such a line is fabricated dialogue, so the
    whole tail is dropped.
    """
    if not text:
        return text
    kept: List[str] = []
    for line in text.splitlines():
        if _LEAK_LINE_RE.match(line):
            break
        kept.append(line)
    out = "\n".join(kept).strip()
    return out if out else text.strip()


# Prompt-scaffolding section headings the model sometimes echoes verbatim.
_PROMPT_HEADING_RE = re.compile(
    r"^\s*#{0,4}\s*(?:"
    r"choose a skill(?: for your turn)?|available skills?|skill (?:index|library|list)"
    r"|selecting a skill.*|now write your turn|your task this turn|stage map"
    r"|recent skills used.*|do not repeat yourself|scaffolding discipline.*"
    r")\s*:?\s*$",
    re.IGNORECASE,
)


def _strip_prompt_echo(text: str, skill_names: List[str]) -> str:
    """
    REMOVE lines where the model has echoed the prompt's skill index or section
    headings, while KEEPING the real message (which typically follows the echo).

    This is deliberately different from _cut_impersonation: with an echo the
    genuine reply comes AFTER the junk, so cutting at the first bad line would
    throw the answer away. Matching is keyed on the ACTUAL skill names, which
    makes it exact rather than a guess — a normal sentence never consists solely
    of a bullet and a skill name.
    """
    if not text or not skill_names:
        return text
    lower_names = {s.lower() for s in skill_names}

    def _is_echo(line: str) -> bool:
        s = line.strip()
        if not s:
            return False
        if _PROMPT_HEADING_RE.match(s):
            return True
        if s in ("]", "[", "```"):          # stray list punctuation from the echo
            return True
        # Strip a leading bullet, then test against the known skill names.
        core = re.sub(r"^[-•*\u2022]\s*", "", s)
        head = core.split(":", 1)[0].strip().lower()
        if head in lower_names:
            # "- probe-intended-decisions" or "- probe-...: Ask the student to..."
            return True
        # A bullet holding nothing but a hyphenated lowercase slug is a skill-list
        # entry even when the name is TRUNCATED or hallucinated ("• elicit-va" —
        # cut off by max_tokens, so it matches no real skill). A genuine mentor
        # line is never a bare slug.
        if s != core and re.fullmatch(r"[a-z]+(?:-[a-z]+)+", head):
            return True
        return False

    kept = [ln for ln in text.splitlines() if not _is_echo(ln)]
    return "\n".join(kept).strip()


def _sanitize(text: str) -> str:
    text = _ROLE_HEADER_RE.sub("", text or "")
    return _cut_impersonation(_SPECIAL_TOKEN_RE.sub("", text)).strip()


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
        "Your response MUST contain these SIX fields, in this order, "
        "before any other text:\n\n"
        "SKILL: <exact-skill-name-from-list>\n"
        "REASONING: <one sentence: why this skill AND this stage right now>\n"
        "STAGE: <the stage number 1-6 you are acting in this turn>\n"
        "STAGE_COMPLETE: <YES if the current stage's goal is now met, else NO>\n"
        "TASK_SOLVED: <YES only when the whole 6-stage conversation has reached "
        "its natural end, else NO>\n"
        "RESPONSE: <the message shown to the learner>\n\n"
        "Only text after RESPONSE: is shown to the learner.\n"
        "Do NOT put any text before the SKILL: line. Do NOT announce stage "
        "numbers to the student in the body.\n\n"
        "Example of correct format:\n"
        "SKILL: probe-intended-decisions\n"
        "REASONING: Opening the conversation — Stage 1 needs the student's question and tentative method.\n"
        "STAGE: 1\n"
        "STAGE_COMPLETE: NO\n"
        "TASK_SOLVED: NO\n"
        "RESPONSE: Could you tell me about your research question?\n"
    )

    lines.append(
        "## Objective\n"
        "Guide the learner through the 6-stage reflective comparison so they reach "
        "Stage 6 with a confident, self-justified methodological view. Keep the "
        "dialogue natural and unhurried, but always be progressing the structure. "
        "You are scored on: reaching the final stage + learner survey rating + "
        "efficient, non-repetitive progress.\n"
    )

    # ── Scaffolding discipline (Concerns 1 & 2) ──────────────────────────────
    lines.append(
        "## ⚠ SCAFFOLDING DISCIPLINE — the most important rules, follow every turn\n"
        "You are a SCAFFOLDER, not an answer-giver. Your job is to help the student "
        "reach their OWN conclusions through questions — never to hand them verdicts.\n"
        "\n"
        "RULE 1 — NEVER evaluate, endorse, or rank the student's method for them.\n"
        "  BANNED phrases (do not say these or anything like them):\n"
        "   - 'you're right', 'you're absolutely right', 'spot-on', 'exactly'\n"
        "   - 'X is a strong choice', 'X is the best fit', 'X is well-suited', 'X is robust'\n"
        "   - 'great job', 'excellent', 'you're on the right track', 'well done'\n"
        "   - 'X is indeed appropriate', 'that's the right method', 'I agree'\n"
        "  Any judgement about whether a method is good/strong/suitable MUST come from\n"
        "  the STUDENT's own reasoning, not from you. If the student states a sound\n"
        "  justification, do not confirm it as correct — instead ask them to test it\n"
        "  ('What might a critic of that choice say?' / 'How would you defend that to\n"
        "  your examiner?'). You may acknowledge effort neutrally ('Thanks for talking\n"
        "  that through') but never validate the CONCLUSION.\n"
        "\n"
        "RULE 2 — NEVER give direct answers, opinions, or recommendations.\n"
        "  Do not tell the student which method to use, which is better, or what they\n"
        "  'should' do. If asked directly to choose for them, say their supervisor can\n"
        "  help with that decision and turn it back into a reflective question.\n"
        "\n"
        "RULE 3 — ONE QUESTION PER TURN. Ask exactly ONE question and then STOP.\n"
        "  Do NOT stack multiple questions. Do NOT present numbered lists of questions.\n"
        "  Do NOT ask a question and then immediately add 'Also, ...' or 'Additionally,'.\n"
        "  Choose the single most useful question for this moment and end your turn.\n"
        "\n"
        "RULE 4 — Use modal, tentative language: 'might', 'could', 'may', 'one\n"
        "  consideration is'. Frame everything as something for the student to weigh,\n"
        "  never as a settled fact about their study.\n"
    )

    lines.append(
        "## DO NOT REPEAT YOURSELF\n"
        "Look at your own previous messages in this conversation. Do NOT re-ask a "
        "question you have already asked, and do NOT re-send the same multi-point "
        "list of questions. If the student gave a partial answer, build on it with "
        "something NEW rather than restating the same prompt. Each of your turns "
        "must move the conversation forward, not restate the previous turn.\n"
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

    # ── Skill index ───────────────────────────────────────────────────────────
    # IMPORTANT: this must NOT be the last thing in the prompt. The assistant
    # turn is prefilled with "SKILL: ", so whatever sits immediately above it is
    # what the model is most likely to continue. With the skill index last,
    # Llama-3.1-8B simply carried on echoing the bullet list into the chat
    # instead of choosing one (issue 8). Ending on the output spec instead makes
    # the required shape the thing it continues.
    lines.append(build_skill_index(skills))

    # ── Closing instruction: the LAST thing the model sees before its turn ────
    lines.append(
        "\n## NOW WRITE YOUR TURN\n"
        "Reply with EXACTLY these five header lines and then your message to the "
        "student. Do NOT repeat or list the skills above — choose ONE and name it "
        "on the SKILL: line. Do NOT output any headings, bullet lists, or notes "
        "from these instructions.\n"
        "\n"
        "SKILL: <one skill name from the list above>\n"
        "REASONING: <one short sentence, for the log — the student never sees it>\n"
        "STAGE: <the stage number you are acting in>\n"
        "STAGE_COMPLETE: <YES or NO>\n"
        "TASK_SOLVED: <YES or NO>\n"
        "<your message to the student — ONE question, nothing else>\n"
    )
    return "\n".join(lines)


# ── Response parser ───────────────────────────────────────────────────────────

def _parse(raw: str, valid_skills: List[str]) -> Dict:
    """Parse the six-field protocol and expose only text after RESPONSE:."""
    raw = _sanitize(raw)
    skill: Optional[str] = None
    reasoning: Optional[str] = None
    stage: Optional[int] = None
    stage_complete = False
    task_solved = False
    response_lines: List[str] = []
    reading_response = False

    for line in raw.strip().splitlines():
        s = line.strip()
        upper = s.upper()
        if upper.startswith("SKILL:"):
            raw_skill = s[len("SKILL:"):].strip().strip("*`\"'")
            if raw_skill in valid_skills:
                skill = raw_skill
            else:
                lower = raw_skill.lower()
                for valid in valid_skills:
                    if valid.lower() == lower:
                        skill = valid
                        break
                if not skill:
                    for valid in valid_skills:
                        if lower in valid.lower() or valid.lower() in lower:
                            skill = valid
                            break
        elif upper.startswith("REASONING:"):
            reasoning = s[len("REASONING:"):].strip()
        elif upper.startswith("STAGE_COMPLETE:"):
            stage_complete = "YES" in upper
        elif upper.startswith("STAGE:"):
            match = re.search(r"\d+", s)
            if match:
                stage = max(1, min(FINAL_STAGE, int(match.group())))
        elif upper.startswith("TASK_SOLVED:"):
            task_solved = "YES" in upper
        elif upper.startswith("RESPONSE:"):
            reading_response = True
            first = s[len("RESPONSE:"):].strip()
            if first:
                response_lines.append(first)
        elif reading_response:
            response_lines.append(line)

    body = _strip_prompt_echo("\n".join(response_lines), valid_skills).strip()
    return {
        "skill": skill,
        "reasoning": reasoning,
        "stage": stage,
        "stage_complete": stage_complete,
        "task_solved": task_solved,
        "response": body,
    }


# ── Post-generation guard (enforces scaffolding discipline deterministically) ─
#
# Prompt rules alone do not reliably stop Qwen-14B from (1) endorsing the
# student's method and (2) asking several questions in one turn. This guard runs
# on every agent response body BEFORE it enters the conversation and repairs it
# in code — no extra LLM call, guaranteed compliance.

# Endorsing clauses to neutralise (Concern 1). Each maps a regex (case-insensitive)
# to a neutral replacement. We soften rather than delete so sentences stay fluent.
_ENDORSEMENT_SUBS = [
    (r"\byou'?re absolutely right\b", "I hear you"),
    (r"\byou'?re right\b",            "I see"),
    (r"\byou'?re correct\b",          "I see"),
    (r"\bthat'?s exactly right\b",    "that's worth examining"),
    (r"\bthat'?s exactly it\b",       "that's worth examining"),
    (r"\bexactly right\b",            "worth examining"),
    (r"\bspot[- ]on\b",               "an interesting point"),
    (r"\bgreat job\b",                "thanks for working through that"),
    (r"\bexcellent (?:job|choice)\b", "thanks for thinking it through"),
    (r"\byou'?re on the right track\b", "let's keep examining this"),
    (r"\bwell done\b",                "thanks for reflecting on that"),
    (r"\bi agree\b",                  "one view is"),
    # "X is indeed a strong/robust ... choice/method/approach/fit" → neutral,
    # consuming the trailing noun so no dangling 'choice for this question' remains.
    (r"\b(?:is|are)\s+indeed\s+(?:a\s+)?(?:strong|robust|appropriate|suitable|rigorous|solid)\s*(?:choice|method|approach|fit|option)?\b",
     "is one possibility to consider"),
    # "X is a strong/robust/well-suited/best/ideal choice/method/fit" → neutral.
    (r"\b(?:is|are|seems?|sounds?)\s+(?:a\s+)?(?:very\s+)?(?:strong|robust|solid|ideal|excellent|perfect|great|the best)\s+(?:choice|method|approach|fit|option)\b",
     "is one option to weigh"),
    (r"\b(?:is|are)\s+well[- ]suited\b", "is one option to consider"),
    (r"\bthat'?s the right (?:method|choice|approach)\b",
     "that's one possible direction"),
]

_ENDORSEMENT_RES = [(re.compile(p, re.IGNORECASE), r) for p, r in _ENDORSEMENT_SUBS]


def _strip_endorsements(text: str) -> str:
    """Neutralise evaluative/endorsing language (Concern 1)."""
    out = text
    for rx, repl in _ENDORSEMENT_RES:
        out = rx.sub(repl, out)
    return out


# Sentence splitter that keeps the trailing punctuation attached.
_SENTENCE_RE = re.compile(r'[^.!?]*[.!?]+|\S[^.!?]*$')

def _limit_to_one_question(text: str) -> str:
    """
    Keep at most ONE question (Concern 2). Strategy: walk sentences in order,
    keep all non-question sentences and the FIRST question sentence, then stop
    once a question has been emitted (dropping any later questions and the
    trailing prose that only existed to support them). If there is no question
    at all, return the text unchanged.
    """
    if text.count("?") <= 1:
        return text

    # Split into sentences while preserving order and punctuation.
    sentences = [s.strip() for s in _SENTENCE_RE.findall(text) if s.strip()]
    if not sentences:
        return text

    kept: List[str] = []
    seen_question = False
    for sent in sentences:
        is_question = sent.rstrip().endswith("?")
        if seen_question and is_question:
            # A later, additional question — drop it.
            continue
        if seen_question and not is_question:
            # Prose after the first question is usually a lead-in to more
            # questions; drop it to avoid dangling fragments.
            continue
        kept.append(sent)
        if is_question:
            seen_question = True

    result = " ".join(kept).strip()
    return result or text


def _apply_scaffolding_guard(text: str) -> str:
    """Apply endorsement stripping then one-question limiting, in that order."""
    if not text:
        return text
    text = _strip_endorsements(text)
    text = _limit_to_one_question(text)
    return text


# ── Repetition detection ─────────────────────────────────────────────────────

def _normalise_question(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    stop = {"could", "would", "can", "you", "please", "tell", "me", "a", "the", "your", "about", "bit"}
    return " ".join(w for w in words if w not in stop)


def _is_repeated_question(candidate: str, history: List[Dict]) -> bool:
    """Detect near-duplicate questions among the last three assistant turns."""
    from difflib import SequenceMatcher
    cand = _normalise_question(candidate)
    if not cand:
        return False
    prior = [m.get("content", "") for m in history if m.get("role") == "assistant"][-3:]
    for old in prior:
        old_n = _normalise_question(old)
        if not old_n:
            continue
        if SequenceMatcher(None, cand, old_n).ratio() >= 0.72:
            return True
        cset, oset = set(cand.split()), set(old_n.split())
        if cset and len(cset & oset) / max(1, min(len(cset), len(oset))) >= 0.80:
            return True
    return False


# ── Agent turn ────────────────────────────────────────────────────────────────

def agent_turn(
    skills: Dict,
    scenario: Dict,
    conversation_history: List[Dict],
    previous_skills: List[str],
    turn_number: int,
    stage_context: str = "",
    expected_stage: Optional[int] = None,
) -> Dict:
    """
    Run one agent turn.
    Returns: skill_name, reasoning, declared_stage, stage_complete,
             response, task_solved, raw_output.

    The call is PREFILLED so the model's first tokens are forced to be the header
    block (fixing the dropped-STAGE-header problem, analogous to the persona's
    UNDERSTANDING_LEVEL prefill). The prefill commits the skill header start; the
    expected stage is stated in the prompt and reinforced here.
    """
    system       = _system_prompt(skills, scenario, previous_skills, stage_context)
    valid_skills = list_skill_names(skills)

    # Prefill the header scaffold. Starting the assistant turn at "SKILL: " makes
    # it structurally impossible for the model to omit the header block or to put
    # prose before it — the single most common cause of dropped STAGE/SKILL lines.
    prefill = "SKILL: "

    raw = call_llm(
        messages=conversation_history,
        system=system,
        max_tokens=700,
        temperature=0.2,
        role="agent",
        prefill=prefill,
    )

    parsed = _parse(raw, valid_skills)

    skill = parsed["skill"]
    if not skill:
        skill = previous_skills[-1] if previous_skills else valid_skills[0]

    # If the model still dropped the STAGE header, fall back to the expected stage
    # the tracker told us to act in, rather than leaving it None (which the tracker
    # would read as "stay put").
    declared_stage = parsed["stage"]
    header_dropped = declared_stage is None
    if declared_stage is None and expected_stage is not None:
        declared_stage = expected_stage

    # ── Empty-body recovery ──────────────────────────────────────────────────
    # If the model spent its whole turn echoing the skill index, stripping the
    # echo leaves NOTHING to say to the student. Rather than emit a blank turn,
    # retry once with the ENTIRE header block pre-filled: with SKILL/STAGE etc.
    # already written for it, the model has no opening to list skills again and
    # can only continue with the message itself.
    recovered = False
    if not parsed["response"].strip():
        full_prefill = (
            f"SKILL: {skill}\n"
            f"REASONING: {(parsed['reasoning'] or 'continuing the stage').strip()}\n"
            f"STAGE: {declared_stage or expected_stage or 1}\n"
            f"STAGE_COMPLETE: {'YES' if parsed['stage_complete'] else 'NO'}\n"
            f"TASK_SOLVED: {'YES' if parsed['task_solved'] else 'NO'}\n"
            "RESPONSE: "
        )
        retry_raw = call_llm(
            messages=conversation_history,
            system=system + (
                "\n\n## ⚠ YOUR LAST ATTEMPT WAS INVALID\n"
                "You listed the skills instead of speaking to the student. The "
                "header block is already written for you. Write ONLY your message "
                "to the student now — one short question, no headings, no bullet "
                "lists, no skill names."
            ),
            max_tokens=300,
            temperature=0.2,
            role="agent",
            prefill=full_prefill,
        )
        retry_parsed = _parse(retry_raw, valid_skills)
        if retry_parsed["response"].strip():
            parsed["response"] = retry_parsed["response"]
            recovered = True

    # Retry once when the model asks a near-duplicate of a recent question.
    repeated_question_recovered = False
    if parsed["response"].strip() and _is_repeated_question(parsed["response"], conversation_history):
        repeat_prefill = (
            f"SKILL: {skill}\n"
            f"REASONING: Move to the next unanswered requirement without repeating an earlier question.\n"
            f"STAGE: {declared_stage or expected_stage or 1}\n"
            "STAGE_COMPLETE: NO\n"
            "TASK_SOLVED: NO\n"
            "RESPONSE: "
        )
        retry_raw = call_llm(
            messages=conversation_history,
            system=system + (
                "\n\n## REPETITION CORRECTION\n"
                "Your proposed question repeats a recent question. Ask about the NEXT "
                "unanswered requirement stated in the stage context. Do not ask again "
                "for information the student has already supplied."
            ),
            max_tokens=240,
            temperature=0.2,
            role="agent",
            prefill=repeat_prefill,
        )
        retry_parsed = _parse(retry_raw, valid_skills)
        if retry_parsed["response"].strip() and not _is_repeated_question(retry_parsed["response"], conversation_history):
            parsed["response"] = retry_parsed["response"]
            repeated_question_recovered = True

    # Post-generation guard: enforce scaffolding discipline deterministically
    # (neutralise endorsements, keep at most one question) since prompt rules
    # alone are unreliable on this model. Keep the raw body for analysis.
    raw_body = parsed["response"]
    guarded_body = _apply_scaffolding_guard(raw_body)
    guard_modified = (guarded_body != raw_body)

    return {
        "skill_name":     skill,
        "reasoning":      parsed["reasoning"] or "",
        "declared_stage": declared_stage,           # resolved (may fall back to expected)
        "stage_header_dropped": header_dropped,     # True if model omitted STAGE: line
        "stage_complete": parsed["stage_complete"],
        "response":       guarded_body,
        "response_pre_guard": raw_body,             # original, for analysis
        "guard_modified": guard_modified,           # True if guard changed the text
        "empty_body_recovered": recovered,          # True if the retry was needed
        "repetition_recovered": repeated_question_recovered,
        "task_solved":    parsed["task_solved"],
        "raw_output":     raw,
    }