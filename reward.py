"""Versioned scoring shared by human and synthetic runs.

The operational score is a process measure, not a learning-effect estimate.
Learning outcomes are independently rated pre/post in research evaluation.
"""
from collections import Counter

VERSION='process-v3'
WEIGHTS={'stage_progress':0.55,'survey_score':0.30,'efficiency':0.15}


def calculate_reward(task_solved, survey_data, turns_used, max_turns,
                     learner_task_check=None, stage_summary=None):
    scores=[survey_data.get(f'Q{i}',{}).get('score') for i in range(1,6)]
    valid=all(type(s) is int and 1<=s<=5 for s in scores)
    maximum=(stage_summary or {}).get('max_stage_reached',1)
    progress=max(0.0,min(1.0,(maximum-1)/5))
    efficiency=max(0.0,1-turns_used/max(1,max_turns)) if maximum>=5 else 0.0
    mean=sum(scores)/5 if valid else None
    normal=(mean-1)/4 if valid else None
    total=round(.55*progress+.30*normal+.15*efficiency,4) if valid else None
    return {'version':VERSION,'reward':total,'reward_band':_band(total) if valid else 'INVALID',
      'eligible':valid,'invalid_reason':None if valid else 'Five valid survey responses required',
      'task_solved':bool(task_solved),'turns_used':turns_used,'max_turns':max_turns,'weights':WEIGHTS,
      'stage_progress_score':progress,'max_stage_reached':maximum,
      'components':{'task_solved_score':float(bool(task_solved)),'survey_score_raw_mean':mean,
                    'survey_score_normalised':normal,'efficiency_score':efficiency}}


def skill_sequence_stats(seq):
    return {'sequence':seq,'total_turns':len(seq),'unique_skills':list(dict.fromkeys(seq)),
      'skill_counts':dict(Counter(seq)),'diversity_ratio':round(len(set(seq))/max(len(seq),1),3),
      'rut_detected':any(seq[i]==seq[i+1]==seq[i+2] for i in range(len(seq)-2))}


def _band(r):
    if r>=.85:return 'EXCELLENT'
    if r>=.70:return 'GOOD'
    if r>=.50:return 'FAIR'
    return 'POOR'
