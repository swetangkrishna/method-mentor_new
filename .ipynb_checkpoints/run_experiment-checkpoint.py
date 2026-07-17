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
from api_client import (check_ollama_running, check_hf_model, _get_hf_token,
                        check_vllm_running)
from skill_loader import load_all_skills
from scenarios import SCENARIOS, SURVEY_QUESTIONS
from agent import agent_turn
from persona import persona_respond, persona_fill_survey, persona_task_check
from reward import calculate_reward, skill_sequence_stats
from database import Database
from stage_tracker import StageTracker
from stages import FINAL_STAGE, stage_name
import retrieval as rag

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
    Recompute the reward so that PROGRESS THROUGH THE 6 STAGES is the dominant
    signal, and a conversation that ends prematurely (before the reflective
    Stage 5) cannot score well no matter how the base components look.

    Rationale (Fix B): the old blend (0.8*base + 0.2*progress) let a 1-turn
    episode score ~0.79 because the base reward rewarded efficiency (finished
    fast!) and survey. That is backwards for a staged tutoring task — finishing
    in 1 turn at Stage 1 is a failure, not an efficient success.

    New scheme:
        final = 0.55 * stage_progress
              + 0.30 * survey_norm
              + 0.15 * efficiency_if_earned
    where:
      - stage_progress is 0..1 across stages 1..6 (reaching Stage 6 = 1.0).
      - efficiency_if_earned is the base efficiency score, but ZEROED if the
        conversation ended before Stage 5 (so a fast premature exit gets no
        efficiency credit).
      - survey_norm is taken from the base reward's normalised survey component.
    """
    if not isinstance(reward, dict):
        return reward

    max_stage     = stage_summary.get("max_stage_reached", 1)
    reached_final = stage_summary.get("reached_final", False)

    # Stage progress across 1..FINAL_STAGE.
    progress = (max_stage - 1) / float(FINAL_STAGE - 1) if FINAL_STAGE > 1 else 1.0
    progress = max(0.0, min(1.0, progress))
    if reached_final:
        progress = 1.0

    # Pull normalised survey + efficiency out of the base reward components.
    comps        = reward.get("components", {}) if isinstance(reward, dict) else {}
    survey_norm  = comps.get("survey_score_normalised")
    if survey_norm is None:
        # Fallback: derive from raw mean if present, else neutral 0.5.
        raw_mean = comps.get("survey_score_raw_mean", 3.0)
        survey_norm = max(0.0, min(1.0, (raw_mean - 1) / 4.0))
    efficiency = comps.get("efficiency_score", 0.0)

    # Efficiency is only earned if the conversation actually reached reflection.
    REFLECTION_STAGE = 5
    efficiency_earned = efficiency if max_stage >= REFLECTION_STAGE else 0.0

    final = (0.55 * progress
             + 0.30 * survey_norm
             + 0.15 * efficiency_earned)
    final = round(final, 4)

    # Preserve the old value for analysis, then overwrite.
    reward["base_reward"]            = reward.get("reward", 0.0)
    reward["stage_progress_score"]   = round(progress, 4)
    reward["max_stage_reached"]      = max_stage
    reward["reached_final_stage"]    = reached_final
    reward["survey_norm_used"]       = round(survey_norm, 4)
    reward["efficiency_earned"]      = round(efficiency_earned, 4)
    reward["reward_weights_v2"]      = {"stage_progress": 0.55, "survey": 0.30,
                                        "efficiency_if_earned": 0.15}
    reward["reward"]                 = final

    if   final >= 0.85: band = "EXCELLENT"
    elif final >= 0.70: band = "GOOD"
    elif final >= 0.50: band = "FAIR"
    else:               band = "POOR"
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
    stage_trace: list = []         # detailed chronological per-turn stage records

    tracker = StageTracker()
    comfort_zone = sc.get("stage_profile", {}).get("comfort_zone")
    stage4_alts  = sc.get("stage_profile", {}).get("stage4_alternatives")
    student_method = sc.get("stage_profile", {}).get("tentative_method")

    # RAG: per-episode query cache (so identical queries are not re-retrieved) and
    # a running log of every retrieval made during the episode.
    rag_cache = rag.new_episode_cache()
    rag_turn_log: list = []      # one entry per turn that triggered retrieval

    for turn in range(1, sc["max_turns"] + 1):
        final_turn = turn

        # Build the stage-awareness block for the agent's system prompt.
        stage_context = tracker.build_stage_context(
            comfort_zone=comfort_zone, stage4_alternatives=stage4_alts,
            student_method=student_method)
        stage_before  = tracker.current_stage
        expected_stage = tracker.expected_stage()

        # ── RAG retrieval (Option A: informs scaffolding only) ────────────────
        # Retrieve only when the turn warrants it (always in method-heavy stages,
        # otherwise only if the student's last message has a substantive methods
        # term). Identical queries are cached within the episode.
        rag_chunks: list = []
        last_student_msg = ""
        for m in reversed(history):
            if m["role"] == "user":
                last_student_msg = m["content"]; break
        rag_fired = rag.should_retrieve(expected_stage, last_student_msg)
        if rag_fired:
            # Query blends the scenario topic with the student's latest message so
            # retrieval is grounded in both the domain and the immediate context.
            query = f"{sc['topic']} {last_student_msg}".strip()
            rag_chunks = rag.retrieve(query, episode_cache=rag_cache)
            block = rag.format_for_prompt(rag_chunks)
            if block:
                stage_context = stage_context + "\n\n" + block
            rag_turn_log.append({
                "turn": turn,
                "query": query[:200],
                "n_chunks": len(rag_chunks),
                "chunks": [
                    {"source": os.path.basename(c.get("source", "")),
                     "score": c.get("score"),
                     "text": c.get("text", "")[:300]}
                    for c in rag_chunks
                ],
            })

        # Live console view of what RAG loaded this turn (if anything).
        if verbose and rag.rag_available():
            if rag_fired and rag_chunks:
                print(f"\n  [RAG] turn {turn}: retrieved {len(rag_chunks)} chunk(s) "
                      f"(stage {expected_stage})")
                for j, c in enumerate(rag_chunks, 1):
                    src = os.path.basename(c.get("source", "")) or "source"
                    snippet = c.get("text", "").strip().replace("\n", " ")[:200]
                    print(f"        [{j}] dist={c.get('score')}  {src}")
                    print(f"            \"{snippet}...\"")
            elif rag_fired and not rag_chunks:
                print(f"  [RAG] turn {turn}: triggered but no chunk passed the "
                      f"distance threshold — none injected")
            else:
                print(f"  [RAG] turn {turn}: skipped (not required this turn)")

        # ── Agent (mentor Aoife) ──────────────────────────────────────────────
        ar = agent_turn(skills, sc, history, skill_seq, turn,
                        stage_context=stage_context,
                        expected_stage=expected_stage)
        skill_seq.append(ar["skill_name"])
        history.append({"role": "assistant", "content": ar["response"]})

        # Advance the stage state machine using the agent's declared stage,
        # passing the response text so the Stage 4 content gate can verify that
        # alternatives were actually presented.
        forced_before = tracker.forced_advances
        stage_now = tracker.advance(
            ar["declared_stage"], ar["stage_complete"],
            response_text=ar["response"], stage4_alternatives=stage4_alts)
        was_forced = tracker.forced_advances > forced_before

        t_id = db.log_turn(run_id, turn, "agent", ar["response"],
                           agent_declared_solved=ar["task_solved"])
        db.log_skill_use(run_id, t_id, turn, ar["skill_name"], ar["reasoning"])

        # ── Detailed, chronological stage record for this turn ────────────────
        stage_record = {
            "turn":                  turn,
            "actor":                 "agent",
            "skill":                 ar["skill_name"],
            "reasoning":             ar["reasoning"],
            "stage_before":          stage_before,
            "expected_stage":        expected_stage,
            "declared_stage":        ar["declared_stage"],
            "stage_after":           stage_now,
            "stage_name":            stage_name(stage_now),
            "stage_complete_flag":   ar["stage_complete"],
            "stage_header_dropped":  ar.get("stage_header_dropped", False),
            "advanced":              stage_now > stage_before,
            "forced":                was_forced,
            "turns_on_stage":        tracker.turns_on_current_stage,
            "stage4_methods_seen":   sorted(tracker.stage4_methods_seen),
            "stage4_presented":      tracker.stage4_alternatives_presented,
            "task_solved_flag":      ar["task_solved"],
            "agent_response":        ar["response"],
            "rag_fired":             rag_fired,
            "rag_chunks":            [
                {"source": os.path.basename(c.get("source", "")),
                 "score": c.get("score"),
                 "text": c.get("text", "")[:300]}
                for c in rag_chunks
            ],
        }
        stage_trace.append(stage_record)

        # Persist to DB (best-effort — schema may predate the richer signature).
        try:
            db.log_stage(run_id, t_id, turn, stage_now,
                         declared=ar["declared_stage"],
                         expected=expected_stage,
                         stage_before=stage_before,
                         stage_complete=ar["stage_complete"],
                         advanced=(stage_now > stage_before),
                         forced=was_forced,
                         header_dropped=ar.get("stage_header_dropped", False),
                         skill=ar["skill_name"],
                         reasoning=ar["reasoning"],
                         stage4_presented=tracker.stage4_alternatives_presented)
        except TypeError:
            # Older log_stage signature — fall back to the minimal call.
            try:
                db.log_stage(run_id, t_id, turn, stage_now,
                             declared=ar["declared_stage"],
                             stage_complete=ar["stage_complete"])
            except Exception:
                pass
        except Exception:
            pass

        if verbose:
            flag = ""
            if was_forced: flag += "  [FORCED]"
            if ar.get("stage_header_dropped"): flag += "  [header dropped]"
            print(f"\n[T{turn}] MENTOR (Aoife)  skill={ar['skill_name']}  "
                  f"stage={stage_now} ({stage_name(stage_now)}){flag}")
            print(f"  {ar['response']}")

        # ── Completion checks ─────────────────────────────────────────────────
        # Fix A: a TASK_SOLVED:YES declaration only ends the episode if the
        # conversation has actually progressed through the reflective stages.
        # Qwen sometimes declares done on turn 1; we ignore that. Real completion
        # requires the agent to be at Stage 5 (reflection) or 6 (summary).
        MIN_STAGE_FOR_SOLVED = 5
        if ar["task_solved"]:
            if stage_now >= MIN_STAGE_FOR_SOLVED:
                task_solved = True
                if verbose:
                    print(f"  [stage] agent declared task solved at stage {stage_now} — accepted")
                break
            else:
                # Premature — ignore and keep going. Record that it happened.
                if stage_trace and stage_trace[-1]["turn"] == turn:
                    stage_trace[-1]["premature_solved_ignored"] = True
                if verbose:
                    print(f"  [stage] agent declared TASK_SOLVED at stage {stage_now} "
                          f"(< {MIN_STAGE_FOR_SOLVED}) — IGNORED, continuing")

        # Natural completion: reached the final stage and the agent marked it done.
        if stage_now >= FINAL_STAGE and ar["stage_complete"]:
            task_solved = True
            if verbose:
                print(f"  [stage] reached final stage {FINAL_STAGE} and marked complete — episode done")
            break

        # ── Persona (student) ─────────────────────────────────────────────────
        pr = persona_respond(sc, history, current_stage=stage_now,
                             prev_level=prev_level)
        prev_level = pr["understanding_level"]
        understanding.append(pr["understanding_level"])
        history.append({"role": "user", "content": pr["response"]})

        # Record which required questions the student has now answered (issues
        # 002/003/004) and close the Stage 4 reflect phase if applicable (006).
        tracker.scan_student_parameters(stage_now, pr["response"])

        db.log_turn(run_id, turn, "persona", pr["response"],
                    understanding_level=pr["understanding_level"],
                    learner_ready=pr["learner_ready"])

        if verbose:
            print(f"[T{turn}] STUDENT ({sc['learner_persona']['name']})  "
                  f"understanding={pr['understanding_level']}/10")
            print(f"  {pr['response']}" if pr["response"] else "  [no response]")

        # The student is free to discontinue at any stage.
        # Attach the persona's response + understanding to this turn's stage record
        # so the chronological report shows both halves of the exchange together.
        if stage_trace and stage_trace[-1]["turn"] == turn:
            stage_trace[-1]["student_understanding"] = pr["understanding_level"]
            stage_trace[-1]["student_response"] = pr["response"]
            stage_trace[-1]["learner_ready"] = pr["learner_ready"]

        if tracker.check_user_exit(pr["response"]):
            if stage_trace and stage_trace[-1]["turn"] == turn:
                stage_trace[-1]["student_exit"] = True
            if verbose:
                print(f"  [stage] student signalled they want to stop — ending episode")
            break

        if pr["learner_ready"]:
            task_solved = True; break

        # Natural completion at the final stage: once we are in Stage 6 (Summary)
        # and the student has synthesised a confident choice, end the episode
        # rather than looping to max_turns. (Fix C / natural-completion request.)
        if tracker.stage6_should_complete(
                student_understanding=pr["understanding_level"],
                learner_ready=pr["learner_ready"]):
            task_solved = True
            if stage_trace and stage_trace[-1]["turn"] == turn:
                stage_trace[-1]["stage6_natural_completion"] = True
            if verbose:
                print(f"  [stage] Stage {FINAL_STAGE} reached and student summarised "
                      f"(understanding={pr['understanding_level']}) — episode complete")
            break

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
        "stage_trace": stage_trace,
        "rag": {
            "available": rag.rag_available(),
            "status": rag.status(),
            "turns_with_retrieval": len(rag_turn_log),
            "total_chunks_returned": sum(t["n_chunks"] for t in rag_turn_log),
            "retrievals": rag_turn_log,
        },
        "reward": reward, "survey": survey_result["survey"],
        "task_check": task_check,
        "model": cfg["model"], "backend": cfg["backend"],
    }
    (RESULTS_DIR / f"{run_id}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False))

    return result


def _health_check():
    print_config(); print()
    # RAG status (non-fatal — experiment runs with or without it).
    rs = rag.status()
    if rs["available"]:
        print(f"[ok] RAG active — index present, model {rs['embed_model']}, top_k {rs['top_k']}\n")
    else:
        why = ("libraries not installed" if not rs["libs_ok"]
               else "index not built (run build_index.py)")
        print(f"[info] RAG inactive ({why}); experiment will run WITHOUT retrieval.\n")
    cfg = get_config()
    b   = cfg["backend"]

    if b == "vllm":
        # The vLLM server may still be loading the model when the experiment
        # starts. Poll /v1/models for up to ~5 minutes before giving up.
        host = cfg["vllm_host"]
        waited = 0
        interval = 10
        max_wait = 300
        while True:
            st = check_vllm_running()
            if st["running"]:
                served = ", ".join(st["models"]) or "(model list empty)"
                print(f"[ok] vLLM server ready at {host} — serving: {served}\n")
                break
            if waited >= max_wait:
                print(f"[ERROR] vLLM server not reachable at {host} after {max_wait}s.")
                print(f"        Detail: {st['error']}")
                print(f"        Check the Slurm .err/.out log — the server may still be "
                      f"loading or may have failed to start.")
                sys.exit(1)
            print(f"[wait] vLLM not ready yet ({waited}s elapsed) — model still loading...")
            time.sleep(interval)
            waited += interval

    elif b == "huggingface":
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