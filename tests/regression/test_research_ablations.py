"""Ablations must omit skill instructions and cannot reuse incompatible policies."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent import agent_turn
from skill_loader import load_all_skills
from study_protocol import CONDITIONS, load_protocol
from tutor_actions import select_action, candidates, fit_policy, fit_q_policy, MOVE_VERSION, VERSION
from research_tools import action_packet, ingest_ratings, learning_rows, evaluate_policy
from research_runtime import StudyRuntime
from research_store import ResearchStore
from stage_tracker import StageTracker

SCENARIO={'role':'mentor','topic':'Test','task_description':'Compare methods',
 'learner_persona':dict(name='P',level='PhD',knowledge_state='unknown',misconception='unknown',emotional_state='unknown',learning_goal='reason')}


def training_rows(action):
    return [dict(episode_id='e'+str(i),participant_id='p'+str(i),turn=1,split='train',action=action,
                 reward=.75,terminal=True,enactment_verified=True) for i in range(3)]

class AblationTests(unittest.TestCase):
    def setUp(self): self.skills=load_all_skills()

    def test_no_skills_prompt_and_logged_action_across_stages(self):
        for stage in range(1,7):
            action=select_action({},stage,[],moves_only=True)
            raw=f"SKILL: none\nTUTOR_MOVE: {action['move']}\nREASONING: clarify\nSTAGE: {stage}\nSTAGE_COMPLETE: NO\nTASK_SOLVED: NO\nRESPONSE: What would you consider next?"
            with patch('agent.call_llm',return_value=raw) as model:
                result=agent_turn(self.skills,SCENARIO,[],[],1,expected_stage=stage,
                    research={'configuration':CONDITIONS['no_skills'],'protocol':{}})
                prompt=model.call_args.kwargs['system']
                for name,skill in self.skills.items():
                    self.assertNotIn(name,prompt)
                    self.assertNotIn(skill['body'],prompt)
                self.assertNotIn('choose ONE and name it',prompt)
                self.assertEqual(result['skill_name'],'none')
                self.assertEqual(result['action']['schema'],MOVE_VERSION)
                self.assertEqual(result['action']['id'],action['id'])
                model.assert_called_once()
            moves={a.split('::')[1] for a in candidates(stage,self.skills)}
            self.assertEqual({a.split('::')[1] for a in candidates(stage,{},moves_only=True)},moves)

    def test_move_policy_learning_and_schema_boundaries(self):
        action=select_action({},1,[],moves_only=True)
        rows=training_rows(action)
        for policy in [fit_policy(rows),fit_q_policy(rows)]:
            self.assertEqual(policy['schema'],MOVE_VERSION)
            self.assertEqual(select_action({},1,[],policy=policy,moves_only=True)['id'],action['id'])
            with self.assertRaises(ValueError): select_action(self.skills,1,[],policy=policy)
            held=dict(rows[0],episode_id='held',participant_id='held',split='test')
            self.assertEqual(evaluate_policy(policy,[held])['supported_rows'],1)
        skill_action=select_action(self.skills,1,[])
        with self.assertRaises(ValueError):fit_policy(rows+training_rows(skill_action))
        with self.assertRaises(ValueError):fit_q_policy(rows+training_rows(skill_action))
        with self.assertRaises(ValueError):evaluate_policy(fit_policy(rows),training_rows(skill_action))

    def test_four_arm_protocol_requires_two_matching_approved_policies(self):
        with patch.dict(os.environ,{},clear=True): protocol=load_protocol()
        protocol['conditions']=['learned_policy','no_skills_learned','full_skills','no_skills']
        protocol['policy']=dict(fit_policy(training_rows(select_action(self.skills,1,[]))),status='approved')
        protocol['move_policy']=dict(fit_policy(training_rows(select_action({},1,[],moves_only=True))),status='approved')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'protocol.json'
            def load(p):
                path.write_text(json.dumps(p))
                with patch.dict(os.environ,{'STUDY_PROTOCOL_FILE':str(path)},clear=True):return load_protocol()
            self.assertEqual(len(load(protocol)['conditions']),4)
            invalid=copy.deepcopy(protocol);invalid['move_policy']=invalid['policy']
            with self.assertRaises(ValueError):load(invalid)
            invalid=copy.deepcopy(protocol);invalid['move_policy']['status']='candidate'
            with self.assertRaises(ValueError):load(invalid)
            invalid=copy.deepcopy(protocol);del invalid['move_policy']
            with self.assertRaises(ValueError):load(invalid)

    def test_rl_only_uses_move_policy_and_preserves_move_contract(self):
        action=select_action({},1,[],moves_only=True)
        policy=fit_policy(training_rows(action))
        context=action['context'];policy['values'][context]={'none::diagnose':{'n':3,'mean':1}}
        raw='SKILL: none\nTUTOR_MOVE: diagnose\nREASONING: locate gap\nSTAGE: 1\nSTAGE_COMPLETE: NO\nTASK_SOLVED: NO\nRESPONSE: What is unclear about your question?'
        with patch('agent.call_llm',return_value=raw):
            result=agent_turn(self.skills,SCENARIO,[],[],1,expected_stage=1,research={
                'configuration':CONDITIONS['no_skills_learned'],'protocol':{'move_policy':policy}})
        self.assertEqual(result['action']['id'],'none::diagnose')
        self.assertEqual(result['action']['policy_id'],policy['id'])
        with patch('agent.call_llm',return_value=raw.replace('TUTOR_MOVE: diagnose','TUTOR_MOVE: elicit')):
            with self.assertRaises(ValueError):agent_turn(self.skills,SCENARIO,[],[],1,expected_stage=1,research={
                'configuration':CONDITIONS['no_skills_learned'],'protocol':{'move_policy':policy}})

    def test_move_only_ratings_do_not_penalise_absent_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=ResearchStore(Path(tmp)/'records.db',url='');self.addCleanup(store.close)
            with patch.dict(os.environ,{},clear=True):p=load_protocol()
            p.update(conditions=['no_skills'],allow_policy_learning=True,policy_learning_notice='Synthetic test')
            runtime=StudyRuntime(self.skills,{'backend':'vllm','model':'test'},store,p)
            runtime.enroll('test',True,'I want to compare methods for understanding teacher experiences and justify the tradeoffs.',3)
            session=dict(session_id='test',owner='test',tracker=StageTracker(),rag_cache={},research=runtime.start('test','FREEFORM'),
                history=[{'role':'assistant','content':'What is your question?'}],ended=True,turn_count=1,survey_result={'ok':True})
            action=select_action({},1,[],moves_only=True)
            runtime.save(session,{'type':'tutor_turn','action':action,'expected_stage':1})
            packet=action_packet(store,runtime.study);item=packet['records'][0]
            self.assertNotIn('skill_enactment',item['rubric'])
            rating={'id':item['id'],'scores':{k:4 for k in item['rubric']},'verified':True}
            bad=copy.deepcopy(rating);bad['scores']['skill_enactment']=0
            with self.assertRaises(ValueError):ingest_ratings(store,runtime.study,'rater', [bad])
            ingest_ratings(store,runtime.study,'rater',[rating])
            rows=learning_rows(store,runtime.study)
            self.assertEqual(rows[0]['reward'],1)
            self.assertEqual(rows[0]['reward_version'],'human-tutor-move-v1')
            self.assertTrue(rows[0]['excluded'])

if __name__=='__main__':unittest.main()
