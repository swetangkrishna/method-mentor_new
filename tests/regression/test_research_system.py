import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_store import ResearchStore, StoreConflict
from research_runtime import StudyRuntime, StudyError
from study_protocol import load_protocol, sus_score, reasoning_score, RUBRIC, digest
from tutor_actions import select_action, fit_policy, compose, candidates
from research_tools import blind_packet, ingest_ratings, analyse, learning_rows, ACTION_RUBRIC, action_packet, evaluate_policy
from stage_tracker import StageTracker
from skill_loader import load_all_skills
from reward import calculate_reward
import agent


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'study.db'
        self.store=ResearchStore(self.path,url='');self.addCleanup(self.store.close)
        with patch.dict(os.environ,{},clear=True): self.protocol=load_protocol()
        self.skills=load_all_skills()
        self.runtime=StudyRuntime(self.skills,{'backend':'vllm','model':'test'},self.store,self.protocol)

    def enroll(self,user='p1'):
        return self.runtime.enroll(user,True,'I want to understand teacher experiences, using interviews with a justified sampling approach.',3)

    def session(self,user='p1'):
        self.enroll(user)
        return {'session_id':'HV_FREEFORM_'+user,'owner':user,'tracker':StageTracker(),'rag_cache':{},
          'research':self.runtime.start(user,'FREEFORM'),'history':[{'role':'assistant','content':'What is your question?'}],
          'ended':False,'turn_count':1}

    def test_transaction_revision_failure_and_restore(self):
        sess=self.session();self.runtime.save(sess,{'type':'tutor_turn','action':select_action(self.skills,1,[])})
        old=copy.deepcopy(sess)
        self.runtime.save(sess,{'type':'end'})
        with self.assertRaises(StoreConflict):self.runtime.save(old,{'type':'lost_update'})
        self.assertEqual(old['research']['revision'],1)
        self.assertEqual(len(old['research']['events']),1)
        archive=self.store.export()
        dest=ResearchStore(Path(self.tmp.name)/'restored.db',url='')
        try:
            dest.restore_empty(archive)
            runtime=StudyRuntime(self.skills,{'backend':'vllm','model':'test'},dest,self.protocol)
            loaded=runtime.load(sess['session_id'],'p1')
            self.assertEqual(loaded['research']['revision'],2)
            self.assertIsInstance(loaded['tracker'].completed_stages,set)
            self.assertIsNone(runtime.load(sess['session_id'],'other'))
            with self.assertRaises(ValueError):dest.restore_empty(archive)
        finally:dest.close()

    @unittest.skipUnless(importlib.util.find_spec('psycopg'), 'Install optional PostgreSQL dependency')
    def test_external_database_verifies_tls_and_redacts_connection_errors(self):
        import psycopg
        url='postgresql://researcher:PRIVATE_TEST_PASSWORD@db.example.org/postgres'
        with patch('psycopg.connect') as connect:
            store=ResearchStore(url=url)
            self.assertEqual(connect.call_args.kwargs['sslmode'],'verify-full')
            self.assertTrue(connect.call_args.kwargs['sslrootcert'])
            self.assertTrue(store.remote)
            store.close()
        with patch('psycopg.connect',side_effect=psycopg.OperationalError(url)):
            with self.assertRaises(RuntimeError) as raised:ResearchStore(url=url)
            self.assertNotIn('PRIVATE_TEST_PASSWORD',str(raised.exception))
            self.assertNotIn(url,str(raised.exception))

    def test_consent_freeze_withdrawal(self):
        with self.assertRaises(StudyError):self.runtime.start('p1','FREEFORM')
        with self.assertRaises(StudyError):self.runtime.enroll('p1',False,'long enough '+'x'*60,2)
        sess=self.session();self.runtime.save(sess,{'type':'start'})
        with self.assertRaises(StudyError):self.runtime.start('p1','FREEFORM')
        changed=copy.deepcopy(self.protocol);changed['conditions']=['no_rag']
        with self.assertRaises(StudyError):StudyRuntime(self.skills,{'backend':'vllm','model':'test'},self.store,changed)
        self.runtime.withdraw('p1')
        self.assertEqual(self.store.records('session',self.runtime.study,'p1'),[])
        with self.assertRaises(StudyError):self.enroll()

    def test_blinded_ratings_usability_analysis(self):
        sess=self.session();sess['ended']=True;self.runtime.save(sess,{'type':'end'})
        result=self.runtime.finish_assessment('p1',sess['session_id'],'I would compare interviews with a survey and consider access, ethics and depth of evidence.',7,[5,1]*5)
        self.assertIn('saved',result['status'])
        packet=blind_packet(self.store,self.runtime.study)
        self.assertEqual(len(packet['records']),2)
        for r in packet['records']:self.assertEqual(set(r),{'id','text'})
        ratings=[{'id':r['id'],'scores':{k:3 for k in RUBRIC},'comment':'Evidence reviewed'} for r in packet['records']]
        self.assertEqual(ingest_ratings(self.store,self.runtime.study,'raterA',ratings),2)
        with self.assertRaises(ValueError):ingest_ratings(self.store,self.runtime.study,'raterA',ratings)
        report=analyse(self.store,self.runtime.study)
        self.assertEqual(report['participants'][0]['gain'],0)
        self.assertEqual(report['participants'][0]['sus'],100)
        self.assertEqual(report['groups']['full_skills']['completed_n'],0) # pilot excluded
        self.assertEqual(sus_score([1,5]*5),0)
        with self.assertRaises(ValueError):sus_score([True]*10)

    def test_policy_learning_support_and_composition(self):
        action=select_action(self.skills,1,[],epsilon=1,seed=1)
        rows=[{'episode_id':f'train{i}','participant_id':f'p{i}','turn':1,'action':action,
          'split':'train','reward':.8,'enactment_verified':True} for i in range(3)]
        policy=fit_policy(rows)
        self.assertAlmostEqual(policy['values'][action['context']][action['id']]['mean'],.8)
        held=dict(rows[0],episode_id='held',split='test')
        assessment=evaluate_policy(policy,[held])
        self.assertEqual(assessment['supported_rows'],1)
        with self.assertRaises(ValueError):evaluate_policy(policy,[dict(held,episode_id='train0')])
        with self.assertRaises(ValueError):fit_policy([dict(r,enactment_verified=False) for r in rows])
        paired=rows+[dict(r,turn=2) for r in rows]
        self.assertEqual(len(compose(paired)),1)
        self.assertTrue(compose(paired)[0]['review_required'])

    def test_full_procedure_action_enforcement_and_quality_repair(self):
        research={'configuration':{'skills':'full','rag':True,'architecture':'single','policy':'fixed'},'protocol':self.protocol}
        selected=select_action(self.skills,1,[])
        raw=f"SKILL: {selected['skill']}\nTUTOR_MOVE: {selected['move']}\nREASONING: clarify\nSTAGE: 1\nSTAGE_COMPLETE: NO\nTASK_SOLVED: NO\nRESPONSE: "
        with patch('agent.call_llm',side_effect=[raw+'Interviews could be a good fit. What is your question and how will you recruit?',raw+'What is your research question?']) as call:
            result=agent.agent_turn(self.skills,{'role':'mentor','topic':'Test','task_description':'Test',
              'learner_persona':{'name':'P','level':'PhD','knowledge_state':'unknown','misconception':'unknown','emotional_state':'unknown','learning_goal':'reason'}},[],[],1,expected_stage=1,research=research)
            self.assertIn(self.skills[selected['skill']]['body'],call.call_args_list[0].kwargs['system'])
            self.assertNotIn('SIX fields',call.call_args_list[0].kwargs['system'])
            self.assertIn('SEVEN fields',call.call_args_list[0].kwargs['system'])
            self.assertEqual(call.call_args_list[0].kwargs['prefill'],'SKILL: ')
            self.assertIn('TUTOR_MOVE: '+selected['move'],call.call_args_list[0].kwargs['system'])
            self.assertEqual(result['action']['id'],selected['id'])
            self.assertEqual(result['response'],'What is your research question?')
            self.assertEqual(call.call_count,2)
        prompt=agent._system_prompt(self.skills,{'role':'mentor','topic':'Test','task_description':'Test',
          'learner_persona':{'name':'P','level':'PhD','knowledge_state':'unknown','misconception':'unknown','emotional_state':'unknown','learning_goal':'reason'}},
          [selected['skill']]*3,'',selected)
        self.assertNotIn('SKILL BANNED',prompt)

    def test_consent_only_preserves_missing_baseline_and_gates_chat(self):
        p=copy.deepcopy(self.protocol);p.update(version='no-baseline',initial_assessment=False)
        runtime=StudyRuntime(self.skills,{'backend':'vllm','model':'test'},self.store,p)
        with self.assertRaises(StudyError):runtime.start('p1','FREEFORM')
        with self.assertRaises(StudyError):runtime.enroll('p1',False,None,None)
        runtime.enroll('p1',True,'must not be retained',9)
        enrollment=self.store.get('enrollment',runtime.study+':p1','p1')['data']
        self.assertIsNone(enrollment['pre']);self.assertIsNone(enrollment['pre_confidence'])
        self.assertEqual(enrollment['pre_status'],'not_collected_by_protocol')
        self.assertEqual(blind_packet(self.store,runtime.study)['records'],[])
        sess=dict(session_id='no-baseline',owner='p1',tracker=StageTracker(),rag_cache={},
                  research=runtime.start('p1','FREEFORM'),history=[],ended=True,turn_count=0)
        runtime.save(sess,{'type':'end'})
        runtime.finish_assessment('p1','no-baseline','I would compare interviews with a survey and evaluate feasibility and evidence quality.',7,[4,2]*5)
        report=analyse(self.store,runtime.study)['participants'][0]
        self.assertIsNone(report['gain']);self.assertIsNone(report['confidence_change'])
        self.assertEqual(len(blind_packet(self.store,runtime.study)['records']),1)
        file=Path(self.tmp.name)/'no-baseline.json';p.update(mode='formal');file.write_text(json.dumps(p))
        with patch.dict(os.environ,{'STUDY_PROTOCOL_FILE':str(file)}):
            with self.assertRaisesRegex(ValueError,'Reasoning gain requires'):load_protocol()

    def test_historical_recovery_is_owned_read_only_and_withdrawal_aware(self):
        sess=self.session();self.runtime.save(sess,{'type':'start'})
        newer=copy.deepcopy(self.protocol);newer['version']='next-version'
        runtime=StudyRuntime(self.skills,{'backend':'vllm','model':'test'},self.store,newer)
        self.assertTrue(runtime.sessions('p1')[0]['read_only'])
        self.assertEqual(runtime.sessions('other'),[])
        self.assertTrue(runtime.historical_session(sess['session_id'],'p1')['ended'])
        self.assertIsNone(runtime.historical_session(sess['session_id'],'other'))
        self.assertIsNone(runtime.load(sess['session_id'],'p1'))
        self.runtime.withdraw('p1')
        self.assertEqual(runtime.sessions('p1'),[])
        self.assertIsNone(runtime.historical_session(sess['session_id'],'p1'))

    def test_repeated_pilot_scoring_has_distinct_actions_and_post_records(self):
        first=self.session();first['ended']=True
        event={'type':'tutor_turn','expected_stage':1,'action':select_action(self.skills,1,[])}
        self.runtime.save(first,event)
        second=copy.deepcopy(first);second['session_id']='ZZ_second';second['research']=self.runtime.start('p1','FREEFORM')
        self.runtime.save(second,event)
        packet=action_packet(self.store,self.runtime.study)
        self.assertEqual(len({r['id'] for r in packet['records']}),2)
        for sess in (first,second):
            self.runtime.finish_assessment('p1',sess['session_id'],'I would compare interviews and surveys against feasibility and evidence requirements.',5,[4,2]*5)
        self.assertEqual(len(self.store.records('post',self.runtime.study,'p1')),2)
        self.runtime.protocol['mode']='formal'
        with self.assertRaises(StudyError):self.runtime.start('p1','FREEFORM')

    def test_formal_gate_and_missing_scores(self):
        p=copy.deepcopy(self.protocol);p['mode']='formal'
        file=Path(self.tmp.name)/'protocol.json';file.write_text(json.dumps(p))
        with patch.dict(os.environ,{'STUDY_PROTOCOL_FILE':str(file)},clear=True):
            with self.assertRaises(ValueError):load_protocol()
        invalid=calculate_reward(False,{},1,40,stage_summary={'max_stage_reached':1})
        self.assertIsNone(invalid['reward']);self.assertFalse(invalid['eligible'])
        survey={f'Q{i}':{'score':4} for i in range(1,6)}
        score=calculate_reward(True,survey,15,40,stage_summary={'max_stage_reached':6})
        self.assertEqual(score['version'],'process-v3');self.assertAlmostEqual(score['reward'],.8688,places=4)

if __name__=='__main__':unittest.main()
