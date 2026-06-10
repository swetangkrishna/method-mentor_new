"""
run_experiment.py — Automated RL experiment runner (LLM persona).

Saves every session, turn, skill use, survey, and reward to SQLite + JSON.

Usage:
    python run_experiment.py --scenario S01 [--runs 5] [--quiet]
    python run_experiment.py --scenario all --runs 3
"""

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from model_config import print_config, get_config
from api_client import check_ollama_running, check_hf_model, _get_hf_token
from skill_loader import load_all_skills
from scenarios import SCENARIOS, SURVEY_QUESTIONS
from agent import agent_turn
from persona import persona_respond, persona_fill_survey, persona_task_check
from reward import calculate_reward, skill_sequence_stats
from database import Database
from stage_tracker import StageTracker
from stages import FINAL_STAGE, stage_name

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# Map short IDs to full scenario keys — MUST match keys in scenarios.py exactly
SCENARIO_ID_MAP = {
    "S01": "S01_digital_tools_geography_interviews",
    "S02": "S02_parent_transition_interviews",
    "S03": "S03_pisa_secondary_data_analysis",
}


def _augment_reward_with_stage(reward: dict, stage_summary: dict) -> dict:
    """
    Add a stage-progression signal to the reward dict WITHOUT modifying reward.py.

    The base reward (task + survey + efficiency) is preserved as base_reward. A
    stage_progress_score in [0,1] is computed from how far through the 6 stages
    the conversation reached, and blended in at 20% weight. Reaching the final
    stage scores 1.0; reaching Stage 1 only scores ~0.0.
    """
    if not isinstance(reward, dict):
        return reward
    max_stage = stage_summary.get("max_stage_reached", 1)
    reached_final = stage_summary.get("reached_final", False)
    # Linear progress across stages 1..FINAL_STAGE.
    progress = (max_stage - 1) / float(FINAL_STAGE - 1) if FINAL_STAGE > 1 else 1.0
    progress = max(0.0, min(1.0, progress))
    if reached_final:
        progress = 1.0

    base = reward.get("reward", 0.0)
    blended = round(0.8 * base + 0.2 * progress, 4)

    reward["base_reward"] = base
    reward["stage_progress_score"] = round(progress, 4)
    reward["max_stage_reached"] = max_stage
    reward["reached_final_stage"] = reached_final
    reward["reward"] = blended

    # Recompute band on the blended reward.
    if   blended >= 0.85: band = "EXCELLENT"
    elif blended >= 0.70: band = "GOOD"
    elif blended >= 0.50: band = "FAIR"
    else:                 band = "POOR"
    reward["reward_band"] = band
    return reward


def run_episode(scenario: dict, skills: dict, db: Database,
                verbose: bool = True) -> dict:
    sc     = scenario
    pid    = sc["id"]
    run_id = (f"{pid}_auto_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
              f"_{uuid.uuid4().hex[:6]}")

    cfg = get_config()
    db.create_session(
        session_id    = run_id,
        scenario_id   = pid,
        scenario_topic= sc["topic"],
        mode          = "automated",
        backend       = cfg["backend"],
        model         = cfg["model"],
        max_turns     = sc["max_turns"],
        persona_name  = sc["learner_persona"]["name"],
    )

    if verbose:
        print(f"\n{'='*60}\nEpisode: {run_id}")
        print(f"Scenario: {pid} — {sc['topic']}")
        print(f"Student: {sc['learner_persona']['name']} "
              f"({sc['learner_persona']['level']})")
        print(f"{'='*60}")

    history:     list = []
    skill_seq:   list = []
    understanding: list = []
    task_solved       = False
    final_turn        = 0
    prev_level: 'int | None' = None

    tracker = StageTracker()
    comfort_zone = sc.get("stage_profile", {}).get("comfort_zone")

    for turn in range(1, sc["max_turns"] + 1):
        final_turn = turn

        # Build the stage-awareness block for the agent's system prompt.
        stage_context = tracker.build_stage_context(comfort_zone=comfort_zone)
        stage_before  = tracker.current_stage

        # ── Agent (mentor Aoife) ──────────────────────────────────────────────
        ar = agent_turn(skills, sc, history, skill_seq, turn,
                        stage_context=stage_context)
        skill_seq.append(ar["skill_name"])
        history.append({"role": "assistant", "content": ar["response"]})

        # Advance the stage state machine using the agent's declared stage.
        stage_now = tracker.advance(ar["declared_stage"], ar["stage_complete"])

        t_id = db.log_turn(run_id, turn, "agent", ar["response"],
                           agent_declared_solved=ar["task_solved"])
        db.log_skill_use(run_id, t_id, turn, ar["skill_name"], ar["reasoning"])
        # Stage logging is best-effort — the DB schema may predate stage support.
        try:
            db.log_stage(run_id, t_id, turn, stage_now,
                         declared=ar["declared_stage"],
                         stage_complete=ar["stage_complete"])
        except Exception:
            pass

        if verbose:
            print(f"\n[T{turn}] MENTOR (Aoife)  skill={ar['skill_name']}  "
                  f"stage={stage_now} ({stage_name(stage_now)})")
            print(f"  {ar['response']}")

        # Completion: agent explicitly ended, OR we have reached the final stage
        # and the agent marked the stage complete.
        if ar["task_solved"]:
            task_solved = True; break
        if stage_now >= FINAL_STAGE and ar["stage_complete"]:
            task_solved = True; break

        # ── Persona (student) ─────────────────────────────────────────────────
        pr = persona_respond(sc, history, current_stage=stage_now,
                             prev_level=prev_level)
        prev_level = pr["understanding_level"]
        understanding.append(pr["understanding_level"])
        history.append({"role": "user", "content": pr["response"]})

        db.log_turn(run_id, turn, "persona", pr["response"],
                    understanding_level=pr["understanding_level"],
                    learner_ready=pr["learner_ready"])

        if verbose:
            print(f"[T{turn}] STUDENT ({sc['learner_persona']['name']})  "
                  f"understanding={pr['understanding_level']}/10")
            print(f"  {pr['response']}" if pr["response"] else "  [no response]")

        # The student is free to discontinue at any stage.
        if tracker.check_user_exit(pr["response"]):
            if verbose:
                print(f"  [stage] student signalled they want to stop — ending episode")
            break

        if pr["learner_ready"]:
            task_solved = True; break

    stage_summary = tracker.summary()

    # ── Task check ────────────────────────────────────────────────────────────
    task_check = persona_task_check(sc, history)
    if not task_solved and task_check.get("solved"):
        task_solved = True

    # ── Survey ────────────────────────────────────────────────────────────────
    survey_result = persona_fill_survey(
        sc, history, SURVEY_QUESTIONS, task_solved, final_turn)
    db.log_survey(run_id, survey_result["survey"], respondent_type="persona")

    # ── Reward ────────────────────────────────────────────────────────────────
    reward = calculate_reward(task_solved, survey_result["survey"],
                              final_turn, sc["max_turns"], task_check)
    # Augment reward with a stage-progression component WITHOUT modifying reward.py.
    reward = _augment_reward_with_stage(reward, stage_summary)
    db.log_reward(run_id, reward)
    db.complete_session(run_id, task_solved, final_turn)

    if verbose:
        print(f"\n{'─'*40}")
        print(f"RESULT : solved={task_solved}  turns={final_turn}/{sc['max_turns']}")
        print(f"STAGES : reached {stage_summary['max_stage_reached']}/{FINAL_STAGE}  "
              f"path={'→'.join(str(s) for s in stage_summary['stage_history'])}")
        if stage_summary["user_requested_exit"]:
            print(f"         (student discontinued early)")
        print(f"REWARD : {reward['reward']} ({reward['reward_band']})")
        print(f"SKILLS : {' → '.join(skill_seq)}")

    # Save JSON
    result = {
        "run_id": run_id, "scenario_id": pid, "topic": sc["topic"],
        "student": sc["learner_persona"]["name"],
        "mode": "automated", "task_solved": task_solved,
        "total_turns": final_turn, "max_turns": sc["max_turns"],
        "skill_sequence": skill_seq,
        "skill_stats": skill_sequence_stats(skill_seq),
        "understanding_progression": understanding,
        "stage_progression": stage_summary,
        "reward": reward, "survey": survey_result["survey"],
        "task_check": task_check,
        "model": cfg["model"], "backend": cfg["backend"],
    }
    (RESULTS_DIR / f"{run_id}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False))

    return result


def _health_check():
    print_config(); print()
    cfg = get_config()
    b   = cfg["backend"]

    if b == "huggingface":
        try:
            tok = _get_hf_token(cfg)
            st  = check_hf_model(cfg["model"], tok)
            if not st["available"]:
                print(f"[ERROR] {st['error']}"); sys.exit(1)
            msg = "loaded" if st["loaded"] else "cold start — first call will be slow (~20-60s)"
            print(f"[ok] HF model '{cfg['model']}': {msg}\n")
        except RuntimeError as e:
            print(f"[ERROR] {e}"); sys.exit(1)

    elif b == "ollama":
        st = check_ollama_running()
        if not st["running"]:
            print("[ERROR] Ollama not running.\n  Fix: ollama serve"); sys.exit(1)
        m = cfg["model"]
        if not any(m in x for x in st["models"]):
            print(f"[WARN] '{m}' not pulled. Run: ollama pull {m}")
        else:
            print(f"[ok] Ollama — '{m}' ready\n")

    elif b == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("[ERROR] ANTHROPIC_API_KEY not set."); sys.exit(1)
        print("[ok] Anthropic key found\n")


def main():
    parser = argparse.ArgumentParser(
        description="Run pedagogical RL experiment (LLM student persona)")
    parser.add_argument("--scenario", default="S01",
                        help="S01 | S02 | S03 | all")
    parser.add_argument("--runs",  type=int, default=1)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    _health_check()
    skills = load_all_skills()
    db     = Database()

    if args.scenario == "all":
        keys = list(SCENARIO_ID_MAP.values())
    else:
        key = SCENARIO_ID_MAP.get(args.scenario.upper())
        if not key:
            print(f"[ERROR] Unknown scenario '{args.scenario}'. "
                  f"Valid: {list(SCENARIO_ID_MAP.keys())} | all")
            sys.exit(1)
        keys = [key]

    all_results = []
    for key in keys:
        sc = SCENARIOS[key]
        for i in range(1, args.runs + 1):
            r = run_episode(sc, skills, db, verbose=not args.quiet)
            all_results.append(r)
            if args.runs > 1 and i < args.runs:
                time.sleep(2)

    db.close()

    if len(all_results) > 1:
        print(f"\n{'='*60}\nSUMMARY ({len(all_results)} runs)")
        for r in all_results:
            sp = r.get("stage_progression", {})
            stg = sp.get("max_stage_reached", "?")
            print(f"  {r['run_id']}  student={r['student']}  "
                  f"solved={r['task_solved']}  turns={r['total_turns']}  "
                  f"stage={stg}/{FINAL_STAGE}  "
                  f"reward={r['reward']['reward']}  ({r['reward']['reward_band']})")
        rewards = [r["reward"]["reward"] for r in all_results]
        stages_reached = [r.get("stage_progression", {}).get("max_stage_reached", 1)
                          for r in all_results]
        print(f"  Mean reward: {sum(rewards)/len(rewards):.3f}")
        print(f"  Mean stage reached: {sum(stages_reached)/len(stages_reached):.2f}/{FINAL_STAGE}")


if __name__ == "__main__":
    main()
