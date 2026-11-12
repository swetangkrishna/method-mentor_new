"""Versioned, bounded pedagogical actions for logging and policy learning.

An action is a skill plus an observable tutor move. Stage constraints remain
outside the learned policy. Selection is logged separately from model enactment.
"""
import hashlib
import json
import math
import random
from pathlib import Path

VERSION = 'skills-moves-v1'
MOVE_VERSION = 'moves-only-v1'
NO_SKILL = 'none'
MOVES = {
    'elicit': 'Ask one open question to elicit the learner\'s question, experience or reasoning.',
    'probe_reason': 'Ask one focused why/how question about a reason the learner has given.',
    'diagnose': 'Use one diagnostic question to locate a misconception or knowledge gap.',
    'scaffold': 'Give a small neutral hint, then ask one focused question; do not supply a verdict.',
    'contrast': 'Invite comparison of two options on exactly one criterion.',
    'test_assumption': 'Ask the learner to examine one assumption or counterexample.',
    'reflect': 'Ask the learner to reflect on one aspect of their reasoning or progress.',
    'acknowledge': 'Acknowledge emotion without endorsing a method, then ask one question.',
    'summarise': 'Invite the learner to summarise their own reasoned choice and next action.',
}
STAGE_ACTIONS = {
 1: [('probe-intended-decisions','elicit'), ('diagnose-zpd','diagnose')],
 2: [('set-learning-objectives','elicit'), ('facilitate-discussion','probe_reason'), ('provide-emotional-support','acknowledge'), ('diagnose-zpd','diagnose'), ('probe-intended-decisions','probe_reason')],
 3: [('probe-intended-decisions','probe_reason'), ('identify-misconceptions','diagnose'), ('scaffold-and-release','scaffold')],
 4: [('design-learning-experience','scaffold'), ('assign-stretch-tasks','test_assumption'), ('scaffold-and-release','scaffold'), ('challenge-assumptions','test_assumption'), ('transform-content','contrast')],
 5: [('provide-formative-feedback','reflect'), ('align-outcomes-activities-assessment','contrast'), ('challenge-assumptions','contrast'), ('encourage-metacognition','reflect'), ('probe-intended-decisions','probe_reason')],
 6: [('encourage-metacognition','summarise'), ('confirm-competence','reflect'), ('reflect-on-pedagogy','summarise')],
}


def action_id(skill, move):
    return skill + '::' + move


def candidates(stage, skills, moves_only=False):
    stage = max(1, min(6, int(stage or 1)))
    if moves_only:
        return list(dict.fromkeys(action_id(NO_SKILL,m) for _,m in STAGE_ACTIONS[stage]))
    return [action_id(s,m) for s,m in STAGE_ACTIONS[stage] if s in skills]


def context_key(stage, history):
    last = next((x.get('content','').lower() for x in reversed(history) if x.get('role')=='user'), '')
    uncertain = any(w in last for w in ('unsure','not sure','anxious','confused','don\'t know'))
    return f'stage={max(1,min(6,int(stage or 1)))};uncertain={int(uncertain)}'


def legal_actions(schema):
    if schema == MOVE_VERSION:
        return {action_id(NO_SKILL,m) for pairs in STAGE_ACTIONS.values() for _,m in pairs}
    if schema == VERSION:
        return {action_id(s,m) for pairs in STAGE_ACTIONS.values() for s,m in pairs}
    raise ValueError('Unknown action space')


def training_schema(rows):
    schemas={r.get('action',{}).get('schema') for r in rows
             if r.get('split')=='train' and not r.get('excluded') and not r.get('withdrawn')}
    if len(schemas)!=1 or not schemas.issubset({VERSION,MOVE_VERSION}):
        raise ValueError('Choose one action space; do not mix skill/move and move-only training rows')
    return schemas.pop()


def validate_policy(data):
    if data.get('schema') not in (VERSION,MOVE_VERSION) or data.get('algorithm') not in ('contextual-bandit-mean-v1','tabular-q-v1'):
        raise ValueError('Unsupported pedagogical policy')
    if not isinstance(data.get('values'),dict): raise ValueError('Policy values missing')
    for row in data['values'].values():
        if not isinstance(row,dict): raise ValueError('Invalid policy row')
        if set(row)-legal_actions(data['schema']):raise ValueError('Policy action does not match its action space')
        for value in row.values():
            if not isinstance(value,dict) or type(value.get('n')) is not int or value['n'] < 1:
                raise ValueError('Invalid policy count')
            mean=value.get('mean')
            if type(mean) not in (int,float) or not math.isfinite(mean) or not 0 <= mean <= 1:
                raise ValueError('Invalid policy value')
    return data


def select_action(skills, stage, history, policy=None, epsilon=0.0, seed=None, moves_only=False):
    schema=MOVE_VERSION if moves_only else VERSION
    if policy is not None and validate_policy(policy)['schema']!=schema:
        raise ValueError('Policy action space does not match condition')
    available=candidates(stage,skills,moves_only=moves_only)
    if not available: raise ValueError('No legal pedagogical action for this stage')
    if not 0 <= epsilon <= 1: raise ValueError('Invalid exploration probability')
    context=context_key(stage,history)
    values=validate_policy(policy)['values'].get(context,{}) if policy else {}
    # The fixed closing policy must respond to unresolved reasoning and avoid
    # repeating an invitation already made. Learned-policy probabilities stay intact.
    closing_reflection = False
    if not policy and int(stage or 1) == 6:
        last = next((x.get('content','').lower() for x in reversed(history) if x.get('role')=='user'), '')
        invited = any(any(w in x.get('content','').lower()
                      for w in ('summaris', 'summariz', 'supervisor')) for x in history)
        unresolved = '?' in last or any(w in last for w in
            ('unsure', 'not sure', 'uncertain', 'cannot', "can't", 'before summar', 'worry', 'concern', 'unresolved', 'still need', 'i need to', 'not ready'))
        closing_reflection = invited or unresolved
        if closing_reflection:
            preferred = action_id(NO_SKILL if moves_only else 'confirm-competence', 'reflect')
            if preferred in available:
                available = [preferred] + [a for a in available if a != preferred]
    # Stable tie-breaking and an explicit random generator make replay possible.
    supported=[a for a in available if a in values]
    best=max(supported or available,key=lambda a: values.get(a,{}).get('mean',0.5))
    probs={a:epsilon/len(available)+(1-epsilon if a==best else 0) for a in available}
    rng=random.Random(seed)
    chosen=rng.choices(available,weights=[probs[a] for a in available])[0]
    skill,move=chosen.split('::')
    return {'id':chosen,'skill':skill,'move':move,'context':context,
            'probability':probs[chosen], 'distribution':probs, 'schema':schema,
            'policy_id':policy.get('id') if policy else ('fixed-moves-v2' if moves_only else 'fixed-stage-v2')}


def load_policy(path):
    return validate_policy(json.loads(Path(path).read_text()))


def fit_policy(rows, minimum=3):
    """Offline contextual-bandit update from scored, validated action observations.

    No model-weight training. Missing/invalid rewards and withheld/test records
    are rejected rather than converted to neutral feedback.
    """
    if type(minimum) is not int or minimum < 1: raise ValueError('minimum must be positive')
    schema=training_schema(rows)
    participant_splits={}
    for row in rows:
        who=row.get('participant_id',row.get('episode_id'))
        participant_splits.setdefault(who,set()).add(row.get('split'))
    if any(len(s)>1 for s in participant_splits.values()):raise ValueError('Participant appears in more than one split')
    sums={}; used=[]
    for r in rows:
        if r.get('split')!='train' or r.get('excluded') or r.get('withdrawn'): continue
        reward=r.get('reward');a=r.get('action',{})
        if type(reward) not in (int,float) or not math.isfinite(reward) or not 0<=reward<=1:continue
        if a.get('schema')!=schema or a.get('id') not in legal_actions(schema):continue
        if not r.get('enactment_verified'):continue
        key=(a['context'],a['id']); sums.setdefault(key,[]).append(reward);used.append(r.get('episode_id',''))
    values={}
    for (context,action),rewards in sums.items():
        if len(rewards)>=minimum: values.setdefault(context,{})[action]={'n':len(rewards),'mean':sum(rewards)/len(rewards)}
    if not values: raise ValueError('Insufficient verified training actions; no policy produced')
    policy={'schema':schema,'algorithm':'contextual-bandit-mean-v1','values':values,
            'training_episodes':sorted(set(used)),'minimum_count':minimum,
            'status':'candidate','limitation':'Associational mean rewards; evaluate on held-out participants before promotion.'}
    policy['id']=hashlib.sha256(json.dumps(policy,sort_keys=True).encode()).hexdigest()
    return policy


def compose(rows, minimum=3):
    """Mine repeated verified skill/move sequences; never synthesize executable code."""
    if training_schema(rows)!=VERSION:raise ValueError('Composite skills require skill/move actions')
    grouped={}
    for r in rows:
        if r.get('split')=='train' and r.get('enactment_verified') and not r.get('excluded') and not r.get('withdrawn'):
            grouped.setdefault(r['episode_id'],[]).append(r)
    sequences={}
    for episode,turns in grouped.items():
        turns.sort(key=lambda r:r['turn'])
        for left,right in zip(turns,turns[1:]):
            if right['turn'] != left['turn']+1:continue
            if any(type(x.get('reward')) not in (float,int) or not 0<=x['reward']<=1 for x in (left,right)):continue
            key=(left['action']['id'],right['action']['id'])
            item=sequences.setdefault(key,{'episodes':set(),'scores':[]})
            item['episodes'].add(episode);item['scores'].append((left['reward']+right['reward'])/2)
    return [{'actions':list(k),'episodes':len(v['episodes']),'mean_reward':sum(v['scores'])/len(v['scores']),
             'status':'candidate','review_required':True}
            for k,v in sorted(sequences.items()) if len(v['episodes'])>=minimum]


def fit_q_policy(rows, epochs=50, alpha=0.2, gamma=0.9):
    """Offline tabular Q-learning over skill/move actions, with bounded returns.

    Learns only from complete, verified training trajectories. Immediate rewards
    are scaled by (1-gamma), so Q remains 0..1 for nonnegative 0..1 rewards.
    No online updates or unsupported actions are introduced into a study.
    """
    if type(epochs) is not int or not 1<=epochs<=1000 or not 0<alpha<=1 or not 0<=gamma<1:
        raise ValueError('Invalid Q-learning hyperparameters')
    # Reuse schema/leakage validation; minimum one supports small synthetic tests.
    schema=fit_policy(rows,minimum=1)['schema']
    episodes={}
    for r in rows:
        if r.get('split')=='train' and not r.get('excluded') and not r.get('withdrawn'):
            episodes.setdefault(r['episode_id'],[]).append(r)
    valid=[]
    for episode,turns in episodes.items():
        turns=sorted(turns,key=lambda r:r['turn'])
        if [r['turn'] for r in turns]!=list(range(1,len(turns)+1)):continue
        if not turns[-1].get('terminal') or any(not r.get('enactment_verified') for r in turns):continue
        if any(r.get('action',{}).get('schema')!=schema or r['action'].get('id') not in legal_actions(schema) for r in turns):continue
        if any(type(r.get('reward')) not in (float,int) or not math.isfinite(r['reward']) or not 0<=r['reward']<=1 for r in turns):continue
        valid.append((episode,turns))
    if not valid:raise ValueError('No complete, verified training trajectories')
    q={};counts={}
    for _,turns in valid:
        for r in turns:
            key=(r['action']['context'],r['action']['id']);q.setdefault(key,0.0);counts[key]=counts.get(key,0)+1
    for _ in range(epochs):
        for _,turns in valid:
            for i,r in enumerate(turns):
                key=(r['action']['context'],r['action']['id'])
                next_context=turns[i+1]['action']['context'] if i+1<len(turns) else None
                future=max([value for (context,action),value in q.items() if context==next_context],default=0.0)
                target=(1-gamma)*r['reward']+gamma*future if next_context else r['reward']
                q[key]+=alpha*(target-q[key])
    values={}
    for (context,action),value in q.items():values.setdefault(context,{})[action]={'mean':value,'n':counts[(context,action)]}
    policy={'schema':schema,'algorithm':'tabular-q-v1','values':values,'status':'candidate',
      'training_episodes':[e for e,_ in valid],'hyperparameters':{'epochs':epochs,'alpha':alpha,'gamma':gamma},
      'reward_semantics':('human-tutor-move-v1' if schema==MOVE_VERSION else 'human-tutor-action-v1')+'; nonterminal rewards scaled by 1-gamma',
      'limitation':'Offline Q-learning on observed trajectories. Hidden learner state and coverage bias remain; prospective evaluation required.'}
    policy['id']=hashlib.sha256(json.dumps(policy,sort_keys=True).encode()).hexdigest()
    return policy
