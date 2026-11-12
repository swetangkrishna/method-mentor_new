"""Complete participant lifecycle through the authenticated engine, without live inference."""
import importlib
import re
import os
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from werkzeug.security import generate_password_hash
from space_bridge import SpaceBridge, BridgeError
from research_tools import blind_packet, action_packet, ingest_ratings, learning_rows, RUBRIC, ACTION_RUBRIC
from tutor_actions import select_action


class StudyWebTests(unittest.TestCase):
    def test_six_stage_session_assessments_recovery_and_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            accounts={u:{'password_hash':generate_password_hash('test-password-12345'),'role':'participant'} for u in ('one','two')}
            (root/'accounts.json').write_text(json.dumps(accounts))
            env={'PARTICIPANTS_FILE':str(root/'accounts.json'),'FLASK_SECRET':'x'*40,
                 'DB_PATH':str(root/'legacy.db'),'STUDY_DB_PATH':str(root/'research.db'),
                 'STUDY_ENABLED':'1','LLM_BACKEND':'vllm','COOKIE_SECURE':'1'}
            with patch.dict(os.environ,env,clear=True):
                import database
                real=database.Database
                with patch.object(database,'Database',lambda:real(root/'legacy.db')):
                    sys.modules.pop('human_validation_server',None)
                    web=importlib.import_module('human_validation_server')
                try:
                    bridge=SpaceBridge(web.app)
                    with self.assertRaisesRegex(BridgeError,'initial assessment'):bridge.start('one')
                    bridge.study_info('one')
                    bridge.study_enroll('one',True,'I want to explore teacher experiences using interviews, but need to compare other approaches.',3)
                    def generate(skills,sc,history,previous,turn,stage_context='',expected_stage=1,research=None):
                        a=select_action(skills,expected_stage,history)
                        # Keep behavior driven by the stage context. For stage 4 the template names the next method.
                        body='What evidence would support that reasoning?'
                        if expected_stage==4:
                            match=re.search(r'Present THIS method now: (.*?) \(',stage_context)
                            if match:body=match.group(1)+' offers another perspective. How feasible would this be?'
                        return {'response':body,'skill_name':a['skill'],'tutor_move':a['move'],'action':a,
                          'reasoning':'Test fixture','declared_stage':expected_stage,'stage_complete':expected_stage in (5,6),
                          'task_solved':expected_stage==6,'quality_flags':[]}
                    alts=[{'method':'Survey','family':'quantitative'},{'method':'Observation','family':'qualitative'},{'method':'Focus groups','family':'qualitative'}]
                    with patch.object(web,'agent_turn',side_effect=generate),patch.object(web,'_retrieve_for_turn',return_value=('',[],False)),patch('pedagogical_runtime.plan_alternatives',return_value=alts):
                        sid=bridge.start('one')['session_id']
                        self.assertEqual(bridge.start('one')['session_id'],sid)
                        self.assertEqual(bridge.sessions('one')['sessions'][0]['session_id'],sid)
                        self.assertEqual(bridge.sessions('two')['sessions'],[])
                        snapshot=bridge.resume('one',sid)
                        with patch.object(web,'agent_turn',side_effect=ValueError('synthetic format failure')):
                            with self.assertRaises(BridgeError):bridge.message('one',sid,'A sample reply that should not be committed on failure.')
                        self.assertEqual(bridge.resume('one',sid),snapshot)
                        for message in ['My question concerns teacher experiences and I am considering interviews.',
                          'I am a full-time PhD student in year two, comfortable with qualitative methods because I have used interviews before.',
                          'My aim is exploratory; I need interview transcripts about experiences and interpretivist meanings.']:
                            bridge.message('one',sid,message)
                        for _ in range(18):
                            saved=web.RESEARCH.load(sid,'one')
                            if saved['tracker'].current_stage==6:break
                            bridge.message('one',sid,'I would consider access, timeline and ethical consent. Interviews offer depth while surveys offer breadth; I need to justify these trade-offs.')
                        self.assertEqual(web.RESEARCH.load(sid,'one')['tracker'].stage4_methods_reflected,
                                         {'Survey','Observation','Focus groups'})
                    saved=web.RESEARCH.load(sid,'one')
                    self.assertEqual(saved['tracker'].current_stage,6)
                    self.assertTrue(all(e.get('action') for e in saved['research']['events'] if e['type']=='tutor_turn'))
                    self.assertTrue(web.DB.get_stages(sid))
                    web.SESSIONS.clear()
                    self.assertEqual(bridge.resume('one',sid)['turn_count'],saved['turn_count'])
                    with self.assertRaises(BridgeError):bridge.resume('two',sid)
                    bridge.end('one',sid)
                    bridge.survey('one',sid,{f'Q{i}':{'score':4} for i in range(1,6)})
                    bridge.study_post('one',sid,'Interviews suit an exploratory question, but I would compare surveys and consider access, ethics and bias.',7,[4,2]*5)
                    self.assertEqual(len(blind_packet(web.RESEARCH.store,web.RESEARCH.study)['records']),2)
                    self.assertGreater(len(action_packet(web.RESEARCH.store,web.RESEARCH.study)['records']),0)
                    with patch.object(web,'agent_turn',side_effect=generate),patch.object(web,'_retrieve_for_turn',return_value=('',[],False)):
                        second=bridge.start('one')['session_id']
                    self.assertNotEqual(second,sid)
                    self.assertEqual(len(bridge.sessions('one')['sessions']),2)
                    self.assertEqual(bridge.resume('one',sid)['ended'],True)
                    bridge.study_withdraw('one',True)
                    with self.assertRaises(BridgeError):bridge.resume('one',sid)
                    self.assertIsNone(web.DB.get_session(sid))
                finally:
                    web.RESEARCH.store.close();web.DB.close();sys.modules.pop('human_validation_server',None)

if __name__=='__main__':unittest.main()
