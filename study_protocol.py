"""Frozen experiment configuration and research instruments (draft, not validated)."""
import hashlib
import json
import os
from pathlib import Path

CONDITIONS = {
 'descriptions': {'skills':'descriptions','rag':True,'architecture':'single','policy':'fixed'},
 'full_skills': {'skills':'full','rag':True,'architecture':'single','policy':'fixed'},
 'no_skills': {'skills':'none','rag':True,'architecture':'single','policy':'fixed'},
 'no_skills_learned': {'skills':'none','rag':True,'architecture':'single','policy':'learned'},
 'no_rag': {'skills':'full','rag':False,'architecture':'single','policy':'fixed'},
 'multi_agent': {'skills':'full','rag':True,'architecture':'planner_mentor_critic','policy':'fixed'},
 'learned_policy': {'skills':'full','rag':True,'architecture':'single','policy':'learned'},
 'composite_skills': {'skills':'full','rag':True,'architecture':'single','policy':'composite'},
}
ASSESSMENT_PROMPT = ('State your research question and proposed method (or uncertainty). Explain why the method could answer the question, '
 'compare at least one alternative, discuss feasibility and limitations, and state what evidence would change your decision. '
 'Write your own reasoning without asking the mentor for help.')
RUBRIC = {
 'question_method_alignment':'0 absent; 1 asserted; 2 partly explained; 3 coherent; 4 specific and well justified.',
 'alternatives_tradeoffs':'0 absent; 1 names another method; 2 one trade-off; 3 balanced comparison; 4 context-specific comparison with limitations.',
 'feasibility_ethics':'0 absent; 1 generic; 2 one concrete constraint; 3 several relevant constraints; 4 realistic integrated plan.',
 'critical_reasoning':'0 unsupported; 1 confident assertion; 2 some limitation; 3 acknowledges uncertainty and evidence; 4 tests assumptions and explains revision criteria.',
}
# Standard SUS statements; preserve wording, order and 1–5 agreement scale.
SUS_ITEMS = [
 'I think that I would like to use this system frequently.',
 'I found the system unnecessarily complex.',
 'I thought the system was easy to use.',
 'I think that I would need the support of a technical person to be able to use this system.',
 'I found the various functions in this system were well integrated.',
 'I thought there was too much inconsistency in this system.',
 'I would imagine that most people would learn to use this system very quickly.',
 'I found the system very cumbersome to use.',
 'I felt very confident using the system.',
 'I needed to learn a lot of things before I could get going with this system.',
]


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def load_protocol():
    path=os.environ.get('STUDY_PROTOCOL_FILE')
    p=json.loads(Path(path).read_text()) if path else {
      'id':'development','version':'draft-1','mode':'pilot','conditions':['full_skills'],
      'primary_outcome':'methodological_reasoning_gain','approved':False,
      'consent_version':'draft-1','participant_information':'Development pilot using sample research information only.',
      'retention_days':30,'allocation_seed':'development-only','policy':None,'composites':[],
    }
    if p.get('mode') not in ('pilot','formal') or not p.get('id') or not p.get('version'):raise ValueError('Invalid study protocol')
    if not p.get('conditions') or any(c not in CONDITIONS for c in p['conditions']):raise ValueError('Invalid study conditions')
    if type(p.get('retention_days')) is not int or p['retention_days']<1:raise ValueError('Set a positive retention period')
    if type(p.get('initial_assessment',True)) is not bool:raise ValueError('initial_assessment must be boolean')
    if p['mode']=='formal' and not p.get('initial_assessment',True) and p.get('primary_outcome')=='methodological_reasoning_gain':
        raise ValueError('Reasoning gain requires an initial assessment; revise the outcome or restore the baseline')
    if p['mode']=='formal':
        for field in ('approval_reference','researcher_contact','participant_information','consent_version','allocation_seed','primary_outcome'):
            if not p.get(field):raise ValueError('Formal protocol incomplete: '+field)
        if p.get('approved') is not True:raise ValueError('Formal protocol requires researcher approval')
        if not os.environ.get('STUDY_DATABASE_URL'):raise ValueError('Formal mode requires external durable study storage')
        if p.get('recovery_verified') is not True:raise ValueError('Formal mode requires a recorded recovery rehearsal')
    from tutor_actions import validate_policy, VERSION, MOVE_VERSION
    for condition,field,schema in [('learned_policy','policy',VERSION),('no_skills_learned','move_policy',MOVE_VERSION)]:
        if condition in p['conditions']:
            candidate=validate_policy(p.get(field) or {})
            if candidate['schema']!=schema:raise ValueError('Policy action space does not match '+condition)
            if candidate.get('status')!='approved':raise ValueError('Learned policy needs explicit approval')
    if 'composite_skills' in p['conditions']:
        if not p.get('composites') or any(c.get('status')!='approved' for c in p['composites']):raise ValueError('Composite sequences need explicit approval')
    epsilon=p.get('exploration',0.0)
    if type(epsilon) not in (float,int) or not 0 <= epsilon <= 1:raise ValueError('Exploration must be between zero and one')
    if p.get('allow_policy_learning') and not p.get('policy_learning_notice'):
        raise ValueError('Explain policy-learning reuse in the participant information')
    for recipe in p.get('composites',[]):
        from tutor_actions import STAGE_ACTIONS, action_id
        legal={action_id(s,m) for pairs in STAGE_ACTIONS.values() for s,m in pairs}
        if not isinstance(recipe.get('actions'),list) or not 2<=len(recipe['actions'])<=4 or any(a not in legal for a in recipe['actions']):
            raise ValueError('Composite must contain 2–4 known actions')
    p['hash']=digest({k:v for k,v in p.items() if k!='hash'})
    return p


def provenance(skills, config):
    root=Path(__file__).parent
    code={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.py') if not p.name.startswith('cluster_')}
    return {'code_hash':digest(code),'files':code,
      'skills_hash':digest({k:{'description':v['description'],'body':v['body']} for k,v in skills.items()}),
      'backend':config['backend'],'model':config['model'],
      'request_profile':config.get('request_profile','classic'),
      'temperature':None if config.get('request_profile')=='reasoning' else 0.2,
      'temperature_control':'provider_default' if config.get('request_profile')=='reasoning' else 'application',
      'minimum_completion_tokens':1600 if config.get('request_profile')=='reasoning' else None,
      'rag_settings':{k:os.environ.get(k) for k in ('RAG_EMBED_MODEL','RAG_TOP_K','RAG_MAX_DISTANCE')},
      'rag_manifest_hash':hashlib.sha256((root/'rag_assets.json').read_bytes()).hexdigest() if (root/'rag_assets.json').exists() else None}


def sus_score(scores):
    if len(scores)!=10 or any(type(s) is not int or not 1<=s<=5 for s in scores):raise ValueError('Answer all ten usability questions from 1 to 5')
    return 2.5*sum(s-1 if i%2==0 else 5-s for i,s in enumerate(scores))


def reasoning_score(scores):
    if set(scores)!=set(RUBRIC) or any(type(v) is not int or not 0<=v<=4 for v in scores.values()):raise ValueError('Rate each rubric dimension 0–4')
    return sum(scores.values())/16
