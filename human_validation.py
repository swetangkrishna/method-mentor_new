"""
human_validation_cli.py — Terminal version of the human-validation tool.

The HUMAN plays the student; the agent ("Aoife") plays the teacher. This is the
terminal counterpart to human_validation_server.py — no Flask, no web front end,
no port to reach on the cluster. You type the student's replies at the prompt and
the agent responds in the terminal.

It reuses the SAME runtime as run_experiment.py: the stage tracker drives the
stage context and expected stage (so agent_turn gets the arguments it now
requires), and the RAG layer grounds the agent when available. Database logging
is OPTIONAL — if the DB is read-only (e.g. created under another account), it
warns once and continues in memory so nothing blocks the session.

Usage:
    python human_validation_cli.py                 # pick a scenario interactively
    python human_validation_cli.py --scenario S01  # start a scenario directly
    python human_validation_cli.py --freeform      # new student, no preset scenario
    python human_validation_cli.py --no-db         # skip all DB logging

In-conversation commands:
    /solved   mark that the agent helped you reach a decision (sets task_solved)
    /end      end the conversation and go to the survey
    /quit     abort without survey
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Directory where each human-validation session is saved as JSON (independent of
# the database, so sessions survive even with --no-db or a read-only DB).
RESULTS_DIR = Path(__file__).parent / "human_validation_results"


def _save_session(record: dict) -> Path | None:
    """
    Write the session record to RESULTS_DIR/<session_id>.json. Called after every
    turn (incremental save) and at the end, so an interrupted session still
    leaves a complete-so-far transcript on disk. Never raises — a save failure
    must not crash the live conversation.
    """
    try:
        RESULTS_DIR.mkdir(exist_ok=True)
        path = RESULTS_DIR / f"{record['session_id']}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False))
        tmp.replace(path)          # atomic: never leaves a half-written file
        return path
    except Exception as e:
        # Surface once, but keep going.
        if not getattr(_save_session, "_warned", False):
            print(f"{C.warn}[save] could not write results: {e}{C.reset}")
            _save_session._warned = True
        return None

from skill_loader import load_all_skills
from scenarios import SCENARIOS, SURVEY_QUESTIONS
from agent import agent_turn
from stage_tracker import StageTracker
from stages import stage_name
from model_config import get_config, print_config

try:
    import retrieval as rag
    _HAS_RAG = True
except Exception:
    _HAS_RAG = False

try:
    from reward import calculate_reward
    _HAS_REWARD = True
except Exception:
    _HAS_REWARD = False


# ── Optional database (degrade gracefully if read-only / missing) ─────────────

class _NullDB:
    """Stand-in used when the real DB is unavailable or read-only."""
    def __getattr__(self, _name):
        def _noop(*a, **k):
            return None
        return _noop

def _open_db(use_db: bool):
    if not use_db:
        return _NullDB(), "disabled (--no-db)"
    try:
        from database import Database
        db = Database()
        return db, "connected"
    except Exception as e:
        msg = str(e).lower()
        if "readonly" in msg or "read-only" in msg or "permission" in msg:
            return _NullDB(), "read-only — logging skipped (using another account's DB?)"
        return _NullDB(), f"unavailable ({e}) — logging skipped"


# ── Terminal helpers ──────────────────────────────────────────────────────────

class C:
    """Minimal ANSI colours; disabled automatically if not a TTY."""
    _on = sys.stdout.isatty()
    ink   = "\033[38;5;67m"  if _on else ""
    agent = "\033[38;5;30m"  if _on else ""
    you   = "\033[38;5;94m"  if _on else ""
    dim   = "\033[2m"        if _on else ""
    bold  = "\033[1m"        if _on else ""
    warn  = "\033[38;5;167m" if _on else ""
    ok    = "\033[38;5;28m"  if _on else ""
    reset = "\033[0m"        if _on else ""

def rule(char="─", n=70):
    print(C.dim + char * n + C.reset)

def wrap(text: str, width=88, indent="    ") -> str:
    import textwrap
    out = []
    for para in text.split("\n"):
        if not para.strip():
            out.append("")
            continue
        out.append(textwrap.fill(para, width=width,
                                 initial_indent=indent, subsequent_indent=indent))
    return "\n".join(out)


# ── Scenario selection ────────────────────────────────────────────────────────

def make_freeform_scenario(name: str = "Student"):
    """
    Build a minimal scenario dict for a real walk-in student who does NOT map to
    any preset scenario. The agent reads topic/task/persona fields, so we supply
    neutral placeholders and let the agent ELICIT the real details (research
    question, comfort zone, etc.) from the human during the conversation.

    comfort_zone and stage4_alternatives are intentionally absent: the tracker
    defaults them to None, and the agent will propose alternatives based on what
    the student actually says rather than from a fixed list.
    """
    return {
        "id": "FREEFORM",
        "role": "mentor",
        "topic": "the student's own research project (to be elicited in conversation)",
        "task_description": (
            "A research student has come for help choosing a research method for "
            "their own project. You do not yet know their topic, discipline, "
            "research question, or methodological comfort zone — elicit these "
            "through the six-stage process, then scaffold them toward a reasoned "
            "choice. Do not assume any details that the student has not told you."
        ),
        "max_turns": 40,
        "learner_persona": {
            "name": name,
            "level": "research student (level to be established in conversation)",
            "knowledge_state": "unknown — to be established by asking",
            "misconception": "none assumed — do not presume a misconception",
            "emotional_state": "neutral — gauge from their messages",
            "learning_goal": (
                "choose and justify a research method appropriate to their own "
                "research question"
            ),
        },
        # No stage_profile: comfort_zone and stage4_alternatives default to None,
        # so the agent proposes alternatives grounded in the student's stated work.
        "stage_profile": {},
    }


def choose_scenario(preselect: str | None):
    scen_list = list(SCENARIOS.values())
    if preselect:
        for sc in scen_list:
            if sc["id"].lower() == preselect.lower():
                return sc
        print(f"{C.warn}Scenario '{preselect}' not found.{C.reset}")
    print(f"\n{C.bold}Available scenarios:{C.reset}")
    for i, sc in enumerate(scen_list, 1):
        persona = sc["learner_persona"]["name"]
        print(f"  {C.bold}{i}{C.reset}. [{sc['id']}] {sc['topic']}")
        print(f"     {C.dim} student persona: {persona}{C.reset}")
    while True:
        raw = input(f"\nPick a scenario [1-{len(scen_list)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(scen_list):
            return scen_list[int(raw) - 1]
        # also allow typing the scenario id
        for sc in scen_list:
            if sc["id"].lower() == raw.lower():
                return sc
        print(f"{C.warn}Please enter a number 1-{len(scen_list)} or a scenario id.{C.reset}")


# ── RAG retrieval for a turn (mirrors run_experiment.py) ──────────────────────

def _retrieve_for_turn(sc, expected_stage, last_student_msg, rag_cache):
    """Return (stage_context_suffix, rag_chunks, fired). Empty if RAG inactive."""
    if not (_HAS_RAG and rag.rag_available()):
        return "", [], False
    if not rag.should_retrieve(expected_stage, last_student_msg):
        return "", [], False
    # In freeform mode the scenario topic is a placeholder, so query on the
    # student's words alone; otherwise blend topic + student message.
    if sc.get("id") == "FREEFORM":
        query = last_student_msg.strip()
    else:
        query = f"{sc['topic']} {last_student_msg}".strip()
    if not query:
        return "", [], False
    chunks = rag.retrieve(query, episode_cache=rag_cache)
    block = rag.format_for_prompt(chunks) if chunks else ""
    suffix = ("\n\n" + block) if block else ""
    return suffix, chunks, True

def _print_rag(turn, fired, chunks, expected_stage):
    if not (_HAS_RAG and rag.rag_available()):
        return
    if fired and chunks:
        print(f"{C.dim}  [RAG] turn {turn}: retrieved {len(chunks)} chunk(s) "
              f"(stage {expected_stage}){C.reset}")
        for j, c in enumerate(chunks, 1):
            src = os.path.basename(c.get("source", "")) or "source"
            print(f"{C.dim}        [{j}] dist={c.get('score')}  {src}{C.reset}")
    elif fired:
        print(f"{C.dim}  [RAG] turn {turn}: triggered but nothing passed threshold{C.reset}")
    else:
        print(f"{C.dim}  [RAG] turn {turn}: skipped (not required){C.reset}")


# ── Main interactive session ──────────────────────────────────────────────────

# Method keywords used to detect the student's own proposed method from their
# free-text messages, so Stage 4 does not offer it back as an 'alternative'.
_METHOD_PATTERNS = [
    ("surveys", ["survey", "questionnaire"]),
    ("interviews", ["interview"]),
    ("focus groups", ["focus group"]),
    ("observation", ["observation", "observing", "observe"]),
    ("ethnography", ["ethnograph"]),
    ("case study", ["case study", "case-study"]),
    ("experiment", ["experiment", "randomised control", "rct"]),
    ("mixed methods", ["mixed method", "mixed-method"]),
    ("secondary data analysis", ["secondary data", "secondary analysis",
                                 "existing dataset", "pisa"]),
    ("document analysis", ["document analysis", "documentary analysis"]),
    ("content analysis", ["content analysis"]),
    ("grounded theory", ["grounded theory"]),
    ("action research", ["action research"]),
]

def _detect_method(text: str):
    """Return a canonical method name if the student's message names one, else None."""
    if not text:
        return None
    t = text.lower()
    for canonical, kws in _METHOD_PATTERNS:
        if any(kw in t for kw in kws):
            return canonical
    return None


def run_session(sc, db, db_status, cfg):
    SKILLS = load_all_skills()
    tracker = StageTracker()
    comfort_zone = sc.get("stage_profile", {}).get("comfort_zone")
    stage4_alts  = sc.get("stage_profile", {}).get("stage4_alternatives")
    rag_cache = rag.new_episode_cache() if (_HAS_RAG and rag.rag_available()) else None

    # The method the HUMAN proposes as their own. Seed from the scenario if it has
    # a concrete tentative_method; in freeform it starts empty and is captured from
    # the student's first substantive message so Stage 4 won't offer it back.
    tm = sc.get("stage_profile", {}).get("tentative_method")
    student_method = tm if (tm and "unsure" not in tm.lower()
                            and "not yet" not in tm.lower()) else None
    _method_captured = student_method is not None

    ts         = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = f"HV_{sc['id']}_{ts}_{uuid.uuid4().hex[:6]}"
    db.create_session(
        session_id=session_id, scenario_id=sc["id"], scenario_topic=sc["topic"],
        mode="human_validation_cli", backend=cfg["backend"], model=cfg.get("model_display", cfg["model"]),
        max_turns=sc["max_turns"], persona_name=sc["learner_persona"]["name"])

    history, skill_seq = [], []
    turn_count = 0
    task_solved = False

    # Session record saved to disk after every turn (independent of the DB).
    transcript: list = []
    record = {
        "session_id": session_id,
        "scenario_id": sc["id"],
        "topic": sc["topic"],
        "mode": "human_validation_cli",
        "freeform": sc.get("id") == "FREEFORM",
        "student_name": sc["learner_persona"]["name"],
        "backend": cfg["backend"],
        "model": cfg.get("model_display", cfg["model"]),
        "max_turns": sc["max_turns"],
        "started_utc": datetime.now().isoformat(timespec="seconds"),
        "transcript": transcript,
        "skill_sequence": skill_seq,
        "task_solved": False,
        "completed": False,
    }
    _save_session(record)

    # Header
    print()
    rule("═")
    print(f"{C.bold}MethodCheck — Human Validation (terminal){C.reset}")
    print(f"  Scenario : [{sc['id']}] {sc['topic']}")
    print(f"  You play : the student ({sc['learner_persona']['name']})")
    print(f"  Agent    : Aoife (the teacher)")
    print(f"  DB       : {db_status}")
    if _HAS_RAG and rag.rag_available():
        print(f"  RAG      : active")
    print(f"  {C.dim}Commands: /solved  /end  /quit{C.reset}")
    rule("═")

    # ── Agent opens (turn 1) ──
    turn_count = 1
    stage_context = tracker.build_stage_context(
        comfort_zone=comfort_zone, stage4_alternatives=stage4_alts,
        student_method=student_method)
    expected_stage = tracker.expected_stage()
    suffix, chunks, fired = _retrieve_for_turn(sc, expected_stage, "", rag_cache)
    _print_rag(turn_count, fired, chunks, expected_stage)
    ar = agent_turn(SKILLS, sc, history, [], turn_count,
                    stage_context=stage_context + suffix,
                    expected_stage=expected_stage)
    tracker.advance(ar.get("declared_stage"), ar.get("stage_complete"),
                    response_text=ar.get("response", ""),
                    stage4_alternatives=stage4_alts)
    history.append({"role": "assistant", "content": ar["response"]})
    skill_seq.append(ar["skill_name"])
    t_id = db.log_turn(session_id, turn_count, "agent", ar["response"],
                       agent_declared_solved=ar["task_solved"])
    db.log_skill_use(session_id, t_id, turn_count, ar["skill_name"], ar["reasoning"])

    _render_agent(ar, tracker)

    transcript.append({
        "turn": turn_count, "actor": "agent", "skill": ar["skill_name"],
        "stage": tracker.current_stage, "stage_name": stage_name(tracker.current_stage),
        "reasoning": ar.get("reasoning", ""), "text": ar["response"],
        "rag_fired": fired,
        "repetition_recovered": ar.get("repetition_recovered", False),
        "rag_chunks": [{"source": os.path.basename(c.get("source","")),
                        "score": c.get("score")} for c in chunks],
    })
    record["skill_sequence"] = skill_seq
    _save_session(record)

    # ── Conversation loop ──
    while True:
        if turn_count >= sc["max_turns"]:
            print(f"\n{C.warn}Max turns reached.{C.reset}")
            break

        try:
            msg = input(f"\n{C.you}{C.bold}You (student) ▸ {C.reset}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{C.dim}(input closed){C.reset}")
            break

        if not msg:
            continue
        if msg.lower() in ("/quit", "/q"):
            print(f"{C.dim}Aborted (no survey).{C.reset}")
            record["completed"] = False
            record["ended_reason"] = "user_quit"
            record["ended_utc"] = datetime.now().isoformat(timespec="seconds")
            record["stage_reached"] = tracker.current_stage
            record["turns"] = turn_count
            saved = _save_session(record)
            if saved:
                print(f"{C.dim}  session saved to {saved}{C.reset}")
            return
        if msg.lower() == "/solved":
            task_solved = True
            print(f"{C.ok}  ✓ marked as solved{C.reset}")
            continue
        if msg.lower() in ("/end", "/done"):
            break

        history.append({"role": "user", "content": msg})
        db.log_turn(session_id, turn_count, "human", msg)
        transcript.append({
            "turn": turn_count, "actor": "human_student",
            "stage": tracker.current_stage, "text": msg,
        })
        record["task_solved"] = task_solved
        _save_session(record)
        turn_count += 1

        # User-exit detection (same tracker logic as the automated runs)
        if tracker.check_user_exit(msg):
            print(f"{C.dim}  (you signalled you want to stop){C.reset}")
            break

        # Record which required questions the student has now answered (issues
        # 002/003/004) and close the Stage 4 reflect phase if applicable (006).
        tracker.scan_student_parameters(tracker.current_stage, msg)
        tracker.advance_after_student_reply()

        # Capture the student's OWN proposed method from their early messages
        # (stages 1-3), so Stage 4 won't offer it back as an 'alternative'.
        if not _method_captured and tracker.current_stage <= 3:
            detected = _detect_method(msg)
            if detected:
                student_method = detected
                _method_captured = True

        stage_context = tracker.build_stage_context(
            comfort_zone=comfort_zone, stage4_alternatives=stage4_alts,
            student_method=student_method)
        expected_stage = tracker.expected_stage()
        suffix, chunks, fired = _retrieve_for_turn(sc, expected_stage, msg, rag_cache)
        _print_rag(turn_count, fired, chunks, expected_stage)

        ar = agent_turn(SKILLS, sc, history, skill_seq, turn_count,
                        stage_context=stage_context + suffix,
                        expected_stage=expected_stage)
        tracker.advance(ar.get("declared_stage"), ar.get("stage_complete"),
                        response_text=ar.get("response", ""),
                        stage4_alternatives=stage4_alts)
        history.append({"role": "assistant", "content": ar["response"]})
        skill_seq.append(ar["skill_name"])
        t_id = db.log_turn(session_id, turn_count, "agent", ar["response"],
                           agent_declared_solved=ar["task_solved"])
        db.log_skill_use(session_id, t_id, turn_count, ar["skill_name"], ar["reasoning"])
        if ar["task_solved"]:
            task_solved = True

        _render_agent(ar, tracker)

        transcript.append({
            "turn": turn_count, "actor": "agent", "skill": ar["skill_name"],
            "stage": tracker.current_stage, "stage_name": stage_name(tracker.current_stage),
            "reasoning": ar.get("reasoning", ""), "text": ar["response"],
            "rag_fired": fired,
            "repetition_recovered": ar.get("repetition_recovered", False),
            "rag_chunks": [{"source": os.path.basename(c.get("source","")),
                            "score": c.get("score")} for c in chunks],
        })
        record["skill_sequence"] = skill_seq
        record["task_solved"] = task_solved
        _save_session(record)

    # ── Survey ──
    _run_survey(sc, db, session_id, turn_count, task_solved, tracker,
                record=record)


def _render_agent(ar, tracker):
    stg = tracker.current_stage
    print()
    print(f"{C.agent}{C.bold}Aoife (teacher){C.reset}  "
          f"{C.dim}[stage {stg}: {stage_name(stg)}  ·  skill: {ar['skill_name']}]{C.reset}")
    print(C.agent + wrap(ar["response"]) + C.reset)


def _run_survey(sc, db, session_id, turns_used, task_solved, tracker, record=None):
    print()
    rule("═")
    print(f"{C.bold}Feedback survey{C.reset}  {C.dim}(rate 1-5; press Enter to skip a question){C.reset}")
    rule("═")
    survey = {}
    try:
        for q in SURVEY_QUESTIONS:
            if isinstance(q, dict):
                qid = q.get("id", str(len(survey) + 1))
                qtext = q.get("question") or q.get("text") or str(qid)
                scale = q.get("scale", "1-5")
            else:
                qid, qtext, scale = q, q, "1-5"
            is_open = "open" in str(scale).lower() or "text" in str(scale).lower()
            print(f"  {qtext}")
            if is_open:
                ans = input(f"    {C.dim}[open text, Enter to skip]{C.reset} ▸ ").strip()
                if ans:
                    survey[qid] = {"score": None, "comment": ans}
                continue
            while True:
                raw = input(f"    {C.dim}[{scale}]{C.reset} ▸ ").strip()
                if raw == "":
                    break
                if raw.isdigit() and 1 <= int(raw) <= 5:
                    survey[qid] = {"score": int(raw), "comment": ""}
                    break
                print(f"    {C.warn}enter 1-5 or Enter to skip{C.reset}")
    except (EOFError, KeyboardInterrupt):
        print(f"\n{C.dim}(survey interrupted — saving what we have){C.reset}")

    # Survey persistence must never prevent the JSON transcript from being saved.
    try:
        db.log_survey(session_id, survey, respondent_type="human")
    except Exception as exc:
        print(f"{C.warn}[db] survey logging failed: {exc}; continuing with JSON save{C.reset}")

    reward = None
    if _HAS_REWARD:
        try:
            reward = calculate_reward(task_solved, survey, turns_used, sc["max_turns"])
            db.log_reward(session_id, reward)
        except Exception:
            reward = None
    db.complete_session(session_id, task_solved, turns_used)

    print()
    rule("═")
    print(f"{C.bold}Session summary{C.reset}")
    print(f"  Session  : {session_id}")
    print(f"  Stage    : reached {tracker.current_stage}/6 ({stage_name(tracker.current_stage)})")
    print(f"  Turns    : {turns_used}")
    print(f"  Solved   : {task_solved}")
    if reward:
        band = reward.get("reward_band", "")
        val  = reward.get("reward", reward if isinstance(reward, (int, float)) else "")
        print(f"  Reward   : {val}  {band}")
    rule("═")

    # Finalise and save the JSON record (independent of the DB).
    if record is not None:
        record["completed"] = True
        record["ended_reason"] = "survey_completed"
        record["ended_utc"] = datetime.now().isoformat(timespec="seconds")
        record["stage_reached"] = tracker.current_stage
        record["stage_name"] = stage_name(tracker.current_stage)
        record["turns"] = turns_used
        record["task_solved"] = task_solved
        record["survey"] = survey
        record["reward"] = reward
        saved = _save_session(record)
        if saved:
            print(f"{C.ok}Session saved to {saved}{C.reset}")

    print(f"{C.ok}Thanks — feedback recorded.{C.reset}" if not isinstance(db, _NullDB)
          else f"{C.dim}(feedback shown above; DB logging was off this session){C.reset}")


def main():
    ap = argparse.ArgumentParser(description="Terminal human-validation tool.")
    ap.add_argument("--scenario", help="Scenario id to start directly, e.g. S01")
    ap.add_argument("--freeform", action="store_true",
                    help="No preset scenario — a new student brings their own project")
    ap.add_argument("--name", default="Student",
                    help="Your display name in freeform mode (default: Student)")
    ap.add_argument("--no-db", action="store_true", help="Skip all database logging")
    args = ap.parse_args()

    cfg = get_config()
    print_config()
    db, db_status = _open_db(use_db=not args.no_db)
    if "read-only" in db_status or "unavailable" in db_status:
        print(f"{C.warn}[db] {db_status}{C.reset}")
        print(f"{C.dim}     Tip: re-run with --no-db to silence this, "
              f"or point DB_PATH at a file you own.{C.reset}")

    if args.freeform:
        sc = make_freeform_scenario(name=args.name)
    else:
        sc = choose_scenario(args.scenario)
    run_session(sc, db, db_status, cfg)


if __name__ == "__main__":
    main()