"""Researcher CLI: backup/recovery, blinded scoring, action rewards and policy candidates.

Uses STUDY_DATABASE_URL (PostgreSQL) or STUDY_DB_PATH (local rehearsal).
Outputs are private local files and are never included in public deployment.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import secrets

from research_store import ResearchStore, now
from study_protocol import RUBRIC, reasoning_score, digest
from tutor_actions import fit_policy, fit_q_policy, compose, select_action, VERSION, MOVE_VERSION, validate_policy

ACTION_RUBRIC={
 'skill_enactment':'0 absent/contradicted; 1 weak; 2 partial; 3 clear; 4 strong application of the selected procedure.',
 'move_enactment':'0 different move; 1 ambiguous; 2 partial; 3 clear; 4 focused, well-executed move.',
 'autonomy':'0 chooses for student; 1 strong endorsement; 2 some direction; 3 preserves choice; 4 actively supports independent reasoning.',
 'context_fit':'0 irrelevant; 1 weak fit; 2 partial; 3 appropriate stage/need; 4 precise adaptation to the learner.',
}


def action_rubric(action):
    if action.get('schema')==MOVE_VERSION:
        return {k:v for k,v in ACTION_RUBRIC.items() if k!='skill_enactment'}
    return ACTION_RUBRIC


def private_write(path,data):
    p=Path(path)
    # Study records must not accidentally become source-controlled artifacts.
    root=Path(__file__).resolve().parent
    resolved=p.resolve()
    if root in resolved.parents and root/'deployment-private' not in resolved.parents:
        raise ValueError('Write research records under deployment-private or outside the source checkout')
    p.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(data,f,indent=2,ensure_ascii=False,allow_nan=False);f.flush();os.fsync(f.fileno())


def blind_id(store,study,owner,phase):
    key=study+':'+owner+':'+phase
    existing=store.get('blind_id',key,owner)
    if existing:return existing['data']['value']
    value=secrets.token_hex(12)
    store.put('blind_id',key,owner,study,{'value':value})
    return value


def blind_packet(store,study):
    records=[]
    for e in store.records('enrollment',study):
        for phase in ('pre','post'):
            source=e if phase=='pre' else store.get('post',study+':'+e['owner'],e['owner'])
            if source and (phase!='pre' or source['data'].get('pre')):
                records.append({'id':blind_id(store,study,e['owner'],phase),'text':source['data'].get('pre') if phase=='pre' else source['data']['text']})
    # No phase, condition, participant ID or model score in the rater packet.
    return {'schema':'blinded-reasoning-v1','rubric':RUBRIC,'records':sorted(records,key=lambda r:r['id']),
            'instructions':'Rate each dimension 0–4 independently. Return {id,scores,comment}; do not infer condition or pre/post phase. Researcher credentials and crosswalk stay separate.'}


def action_rating_id(store,study,session,turn):
    # Retain existing first-episode rating identities; new episodes get distinct IDs.
    episodes=sorted(store.records('session',study,session['owner']),key=lambda r:r['id'])
    phase='action:'+str(turn) if episodes and episodes[0]['id']==session['id'] else 'action:'+session['id']+':'+str(turn)
    return blind_id(store,study,session['owner'],phase)


def action_packet(store,study):
    records=[]
    for s in store.records('session',study):
        turn=0
        for event in s['data']['research']['events']:
            if event['type']!='tutor_turn':continue
            turn+=1
            if not event.get('action'):continue
            history=s['data']['history'][:2*turn-1]
            records.append({'id':action_rating_id(store,study,s,turn),
              'selected_action':event['action']['id'],'expected_stage':event['expected_stage'],
              'rubric':action_rubric(event['action']),'action_schema':event['action']['schema'],
              'context':history[-3:],'quality_flags':event.get('quality_flags',[])})
    return {'schema':'tutor-action-rating-v2','rubric':ACTION_RUBRIC,'records':records,
      'instructions':'Use the rubric on EACH record. Rate enacted behavior 0–4. Move-only records omit skill enactment, not a zero score. Include verified true only when the selected move (and skill, where supplied) is enacted. A generated label alone is not sufficient.'}


def rating_crosswalk(store,study):
    lookup={}
    for e in store.records('enrollment',study):
        for phase in ('pre','post'):
            if phase=='pre' and not e['data'].get('pre'):continue
            if phase=='post' and not store.get('post',study+':'+e['owner']):continue
            lookup[blind_id(store,study,e['owner'],phase)]=(e['owner'],phase,None,None)
    for s in store.records('session',study):
        count=0
        for event in s['data']['research']['events']:
            if event['type']=='tutor_turn':
                count+=1;lookup[action_rating_id(store,study,s,count)]=(s['owner'],'action',count,s['id'])
    return lookup


def ingest_ratings(store,study,rater,ratings):
    if not isinstance(rater,str) or not rater.strip() or len(rater)>100:raise ValueError('Rater identity required')
    lookup=rating_crosswalk(store,study)
    action_rubrics={r['id']:r['rubric'] for r in action_packet(store,study)['records']}
    pending=[]
    for item in ratings:
        if item.get('id') not in lookup:raise ValueError('Unknown rating ID')
        owner,phase,turn,session_id=lookup[item['id']]
        expected=action_rubrics[item['id']] if phase=='action' else RUBRIC
        scores=item.get('scores',{})
        if set(scores)!=set(expected) or any(type(v) is not int or not 0<=v<=4 for v in scores.values()):raise ValueError('Invalid rubric scores')
        if phase=='action' and type(item.get('verified')) is not bool:raise ValueError('Action verification required')
        id=study+':'+item['id']+':'+rater
        if store.get('rating',id):raise ValueError('Rater already submitted this item; original ratings are immutable')
        pending.append((id,owner,dict(item,rater=rater,phase=phase,turn=turn,session_id=session_id,at=now(),source='human')))
    # The batch is validated before any insert. Individual immutable rows are recoverable/idempotent by ID.
    for id,owner,data in pending:store.put('rating',id,owner,study,data)
    return len(pending)


def participant_split(owner,seed):
    value=int(hashlib.sha256((seed+':'+owner).encode()).hexdigest(),16)%10
    return 'train' if value<7 else 'test'


def learning_rows(store,study,seed='split-v1'):
    rows=[]
    for s in store.records('session',study):
        data=s['data'];research=data['research'];enrollment=store.get('enrollment',study+':'+s['owner'])
        # Analysis reuse is a protocol decision, never silently assumed from participation.
        if not research['protocol'].get('allow_policy_learning',False):continue
        if not data.get('survey_result') or not enrollment:continue
        count=0
        for e in research['events']:
            if e['type']!='tutor_turn':continue
            count+=1
            rating_id=action_rating_id(store,study,s,count)
            ratings=[r['data'] for r in store.records('rating',study,s['owner']) if r['data']['phase']=='action' and r['data']['id']==rating_id]
            action=e.get('action')
            if not action or not ratings:continue
            verified=all(r.get('verified') for r in ratings)
            rubric=action_rubric(action)
            if any(set(r['scores'])!=set(rubric) for r in ratings):raise ValueError('Stored action scores do not match action rubric')
            reward=statistics.mean(sum(r['scores'].values())/(4*len(rubric)) for r in ratings)
            rows.append({'episode_id':s['id'],'participant_id':s['owner'],'turn':count,'action':action,
              'reward':reward,'reward_version':'human-tutor-move-v1' if action.get('schema')==MOVE_VERSION else 'human-tutor-action-v1','enactment_verified':verified,
              'split':participant_split(s['owner'],seed),'terminal':count==len([v for v in research['events'] if v['type']=='tutor_turn']),
              'synthetic':research['synthetic'],
              'excluded':research['synthetic'],'study':study})
    return rows


def evaluate_policy(policy,rows):
    validate_policy(policy)
    if any(r.get('action',{}).get('schema')!=policy['schema'] for r in rows if not r.get('excluded')):
        raise ValueError('Evaluation action space does not match policy; filter rows explicitly')
    training=set(policy.get('training_episodes',[]))
    held=[r for r in rows if r.get('split')=='test' and not r.get('excluded') and r.get('enactment_verified')]
    if any(r['episode_id'] in training for r in held):raise ValueError('Train/test episode leakage')
    weighted=[];matches=0;eligible=0
    for r in held:
        p=r['action'].get('probability')
        if type(p) not in (int,float) or not 0<p<=1:continue
        context=r['action']['context'];observed=r['action']['id'];values=policy['values'].get(context,{})
        legal=list((r['action'].get('distribution') or {}).keys())
        if not legal:continue
        supported=[a for a in legal if a in values]
        desired=max(supported or legal,key=lambda a:values.get(a,{}).get('mean',.5))
        target=1.0 if desired==observed else 0.0
        # Complete support is required for this target action, not just observed support.
        if (r['action']['distribution'].get(desired) or 0)<=0:continue
        eligible+=1;matches+=int(target>0);weighted.append(target*r['reward']/p)
    return {'schema':'off-policy-ips-v1','held_out_rows':len(held),'supported_rows':eligible,'matched_rows':matches,
      'ips_estimate':statistics.mean(weighted) if weighted else None,
      'observed_mean':statistics.mean(r['reward'] for r in held) if held else None,
      'promotion_ready':False,
      'warning':'IPS can have high variance. Repeated turns are clustered within participants; no causal or significance claim. Review support and run a prospective comparison before promotion.'}


def analyse(store,study):
    rows=[];ratings=store.records('rating',study)
    for e in store.records('enrollment',study):
        owner=e['owner'];post=store.get('post',study+':'+owner)
        if not post:continue
        values={}
        for phase in ('pre','post'):
            rr=[r['data'] for r in ratings if r['owner']==owner and r['data']['phase']==phase]
            values[phase]=statistics.mean(reasoning_score(r['scores']) for r in rr) if rr else None
        rows.append({'participant':blind_id(store,study,owner,'analysis'),'condition':e['data']['condition'],
          'synthetic':e['data']['synthetic'],'pre':values['pre'],'post':values['post'],
          'gain':values['post']-values['pre'] if None not in values.values() else None,
          'confidence_change':post['data']['confidence']-e['data']['pre_confidence'] if e['data'].get('pre_confidence') is not None else None,
          'sus':post['data']['sus_score']})
    groups={}
    for condition in sorted({r['condition'] for r in rows}):
        actual=[r for r in rows if r['condition']==condition and not r['synthetic']]
        gains=[r['gain'] for r in actual if r['gain'] is not None]
        groups[condition]={'completed_n':len(actual),'rated_pairs_n':len(gains),
          'mean_gain':statistics.mean(gains) if gains else None,
          'mean_sus':statistics.mean(r['sus'] for r in actual) if actual else None}
    agreement=[]
    for id in sorted({r['data']['id'] for r in ratings if r['data']['phase']!='action'}):
        rr=[r['data'] for r in ratings if r['data']['id']==id]
        if len(rr)>=2:
            totals=[reasoning_score(r['scores']) for r in rr]
            agreement.append(max(totals)-min(totals))
    return {'study':study,'groups':groups,'participants':rows,'double_rated_items':len(agreement),
       'mean_rater_range':statistics.mean(agreement) if agreement else None,
       'warning':'Descriptive analysis only. Missing and synthetic observations excluded from group means; no proof of effectiveness or statistical significance.'}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command',choices=['backup','restore','blind','actions','ratings','analyse','dataset','train','qtrain','compose','evaluate'])
    ap.add_argument('--study');ap.add_argument('--input');ap.add_argument('--output');ap.add_argument('--policy');ap.add_argument('--rater');ap.add_argument('--minimum',type=int,default=3)
    ap.add_argument('--action-space',choices=['skills','moves'],help='Filter training/evaluation input to one action space')
    args=ap.parse_args()
    if args.command in ('train','qtrain','compose','evaluate'):
        rows=json.loads(Path(args.input).read_text())
        if args.action_space:
            schema=MOVE_VERSION if args.action_space=='moves' else VERSION
            rows=[r for r in rows if r.get('action',{}).get('schema')==schema]
        if args.command=='train':result=fit_policy(rows,args.minimum)
        elif args.command=='qtrain':result=fit_q_policy(rows)
        elif args.command=='compose':result=compose(rows,args.minimum)
        else:result=evaluate_policy(json.loads(Path(args.policy).read_text()),rows)
    else:
        store=ResearchStore()
        try:
            if args.command=='backup':result=store.export()
            elif args.command=='restore':store.restore_empty(json.loads(Path(args.input).read_text()));result={'restored':True}
            else:
                if not args.study:raise ValueError('--study is required')
                if args.command=='blind':result=blind_packet(store,args.study)
                elif args.command=='actions':result=action_packet(store,args.study)
                elif args.command=='ratings':result={'imported':ingest_ratings(store,args.study,args.rater,json.loads(Path(args.input).read_text()))}
                elif args.command=='analyse':result=analyse(store,args.study)
                else:result=learning_rows(store,args.study)
        finally:store.close()
    if args.output:private_write(args.output,result);print('Private output saved.')
    else:
        if args.command not in ('ratings','restore'):raise ValueError('--output is required to avoid printing participant data')
        print(json.dumps(result))

if __name__=='__main__':main()
