"""
reward.py — Composite RL reward: task_solved + survey + efficiency.

reward = 0.50 × task_solved_score
       + 0.30 × survey_normalised   (1-5 → 0-1)
       + 0.20 × efficiency_score    (1 - turns/max_turns)
"""

from typing import Dict, List, Optional

WEIGHTS = {"task_solved": 0.50, "survey_score": 0.30, "efficiency": 0.20}


def calculate_reward(
    task_solved: bool,
    survey_data: Dict,
    turns_used: int,
    max_turns: int,
    learner_task_check: Optional[Dict] = None,
) -> Dict:
    # Task component
    task_score = 1.0 if task_solved else 0.0
    if not task_solved and learner_task_check:
        if learner_task_check.get("solved"):
            task_score = 0.8
        elif learner_task_check.get("confidence", 0) >= 7:
            task_score = 0.5

    # Survey component
    nums = [
        survey_data.get(f"Q{i}", {}).get("score")
        for i in range(1, 6)
        if isinstance(survey_data.get(f"Q{i}", {}).get("score"), (int, float))
    ]
    mean_survey = sum(nums) / len(nums) if nums else 3.0
    survey_norm = (mean_survey - 1) / 4

    # Efficiency component
    efficiency = max(0.0, 1.0 - (turns_used / max(max_turns, 1)))

    reward = (
        WEIGHTS["task_solved"] * task_score
        + WEIGHTS["survey_score"] * survey_norm
        + WEIGHTS["efficiency"] * efficiency
    )

    return {
        "reward": round(reward, 4),
        "reward_band": _band(reward),
        "task_solved": task_solved,
        "turns_used": turns_used,
        "max_turns": max_turns,
        "weights": WEIGHTS,
        "components": {
            "task_solved_score":       round(task_score, 4),
            "survey_score_raw_mean":   round(mean_survey, 4),
            "survey_score_normalised": round(survey_norm, 4),
            "efficiency_score":        round(efficiency, 4),
        },
    }


def skill_sequence_stats(seq: List[str]) -> Dict:
    from collections import Counter
    counts = Counter(seq)
    rut = any(seq[i] == seq[i+1] == seq[i+2] for i in range(len(seq)-2)) if len(seq) >= 3 else False
    return {
        "sequence":          seq,
        "total_turns":       len(seq),
        "unique_skills":     list(dict.fromkeys(seq)),
        "skill_counts":      dict(counts),
        "diversity_ratio":   round(len(set(seq)) / max(len(seq), 1), 3),
        "rut_detected":      rut,
    }


def _band(r: float) -> str:
    if r >= 0.85: return "EXCELLENT"
    if r >= 0.70: return "GOOD"
    if r >= 0.50: return "ACCEPTABLE"
    if r >= 0.30: return "POOR"
    return "FAILED"
