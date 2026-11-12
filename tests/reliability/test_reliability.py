import unittest,json,copy
from pathlib import Path
from unittest.mock import Mock
from reply_flow import submit_reply
from space_bridge import BridgeError
from failure_records import safe_diagnostics
from api_client import AzureBackendError
from tutor_actions import select_action
from skill_loader import load_all_skills
from stage_tracker import StageTracker

class ReliabilityTests(unittest.TestCase):
 def test_filter_and_transport_failure_preserves_input_history_and_reference(self):
  for status in (400,503):
   b=Mock();b.message.side_effect=BridgeError('Safety filter. Reference: '+'a'*32,status)
   history,text,message=submit_reply(b,'tester','session','my unchanged input')
   self.assertIsNone(history);self.assertEqual(text,'my unchanged input');self.assertIn('a'*32,message);b.resume.assert_not_called()
 def test_success_clears_input_only_after_readback(self):
  b=Mock();b.message.return_value={};b.resume.return_value={'history':[{'role':'assistant','content':'Saved?'}]}
  h,t,s=submit_reply(b,'tester','s','input');self.assertEqual(h,b.resume.return_value['history']);self.assertEqual(t,'');self.assertIn('Ready',s)
 def test_readback_failure_does_not_invite_duplicate_send(self):
  b=Mock();b.message.return_value={};b.resume.side_effect=BridgeError('unavailable')
  h,t,s=submit_reply(b,'tester','s','input');self.assertIsNone(h);self.assertEqual(t,'input');self.assertIn('before sending again',s)
 def test_unauthenticated_no_backend_call(self):
  b=Mock();self.assertIn('sign in',submit_reply(b,None,'s','input')[2]);b.message.assert_not_called()
 def test_diagnostic_allowlist_rejects_raw_text_and_credentials(self):
  e=AzureBackendError('content_filter',400,{'phase':'request','prompt':'SECRET','filters':[{'category':'hate','severity':'medium','filtered':True,'text':'SECRET'},{'category':'SECRET','filtered':True}]})
  d=safe_diagnostics(e);self.assertEqual(d,{'http_status':400,'phase':'request','filters':[{'category':'hate','filtered':True,'severity':'medium'}]});self.assertNotIn('SECRET',json.dumps(d))
 def test_manual_summary_loop_fixture_selects_legal_reflection(self):
  src=Path(__file__).parent/'fixtures/summary-loop.json'
  h=json.loads(src.read_text());skills=load_all_skills();checked=0
  for i,item in enumerate(h):
   if item['role']=='user' and any(w in item['content'].lower() for w in ('before summar','cannot','unsure','not sure')):
    a=select_action(skills,6,h[:i+1]);self.assertEqual(a['move'],'reflect');self.assertEqual(a['probability'],1);self.assertEqual(sum(a['distribution'].values()),1);checked+=1
  self.assertGreaterEqual(checked,3)
 def test_fresh_closing_can_invite_summary_once(self):
  a=select_action(load_all_skills(),6,[{'role':'user','content':'I am ready to explain my choice.'}]);self.assertEqual(a['move'],'summarise')
  a=select_action(load_all_skills(),6,[{'role':'assistant','content':'How would you summarise your rationale?'},{'role':'user','content':'My choice reflects access and the evidence I need.'}]);self.assertEqual(a['move'],'reflect')
 def test_learned_policy_not_overridden(self):
  skills=load_all_skills();h=[{'role':'user','content':'I am unsure?'}];a=select_action(skills,6,h);key=a['context'];policy={'schema':a['schema'],'algorithm':'contextual-bandit-mean-v1','id':'test','values':{key:{'encourage-metacognition::summarise':{'n':10,'mean':.9}}}}
  self.assertEqual(select_action(skills,6,h,policy=policy)['move'],'summarise')
 def test_closing_context_addresses_unresolved_questions(self):
  t=StageTracker();t.current_stage=6;s=t.build_stage_context();self.assertIn('latest unresolved',s);self.assertIn('do not ask them to repeat',s)

class ConnectionRecoveryTests(unittest.TestCase):
 def test_idle_reset_reconnects_before_select_with_verified_tls(self):
  from unittest.mock import patch,MagicMock
  from sqlserver_store import SqlServerConnection
  first,second=MagicMock(),MagicMock()
  with patch('pytds.connect',side_effect=[first,second]) as connect:
   adapter=SqlServerConnection('mssql://u:p@host/db')
   first.cursor.return_value.__enter__.side_effect=ConnectionResetError('idle')
   cursor=second.cursor.return_value.__enter__.return_value;cursor.description=[('x',)];cursor.fetchall.return_value=[('saved',)]
   self.assertEqual(adapter.execute('SELECT payload FROM research_records').fetchone(),('saved',))
   self.assertEqual(connect.call_count,2);self.assertTrue(connect.call_args.kwargs['validate_host']);self.assertFalse(connect.call_args.kwargs['enc_login_only'])
 def test_commit_connection_failure_never_replays_write(self):
  from unittest.mock import patch,MagicMock
  from sqlserver_store import SqlServerConnection
  conn=MagicMock()
  with patch('pytds.connect',return_value=conn) as connect:
   adapter=SqlServerConnection('mssql://u:p@host/db');conn.commit.side_effect=ConnectionResetError('uncertain commit');conn.rollback.side_effect=ConnectionResetError('closed')
   with self.assertRaises(ConnectionResetError):
    with adapter.transaction():adapter.execute('UPDATE research_records SET revision=2')
   self.assertEqual(connect.call_count,1)
   statements=[x.args[0] for x in conn.cursor.return_value.__enter__.return_value.execute.call_args_list]
   self.assertEqual(sum(s.startswith('UPDATE') for s in statements),1)

class FailurePersistenceTests(unittest.TestCase):
 def test_error_reference_diagnostics_and_transactional_history(self):
  import tempfile,os,sys,importlib
  from unittest.mock import patch
  from werkzeug.security import generate_password_hash
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'accounts.json').write_text(json.dumps({'tester':{'password_hash':generate_password_hash('example-only'),'role':'participant'}}))
   env={'PARTICIPANTS_FILE':str(root/'accounts.json'),'FLASK_SECRET':'x'*40,'DB_PATH':str(root/'legacy.db'),'STUDY_DB_PATH':str(root/'research.db'),'STUDY_ENABLED':'1','LLM_BACKEND':'vllm','COOKIE_SECURE':'1'}
   with patch.dict(os.environ,env,clear=True):
    import database
    real=database.Database
    with patch.object(database,'Database',lambda:real(root/'legacy.db')):
     sys.modules.pop('human_validation_server',None);web=importlib.import_module('human_validation_server')
    from space_bridge import SpaceBridge
    bridge=SpaceBridge(web.app)
    try:
     bridge.study_enroll('tester',True,'I want to explore teacher experiences using interviews and compare observation for context.',3)
     a=select_action(web.SKILLS,1,[]) if hasattr(web,'SKILLS') else select_action(load_all_skills(),1,[])
     out={'response':'What is your research question?','skill_name':a['skill'],'tutor_move':a['move'],'action':a,'reasoning':'Fixture','declared_stage':1,'stage_complete':False,'task_solved':False,'quality_flags':[]}
     with patch.object(web,'agent_turn',return_value=out),patch.object(web,'_retrieve_for_turn',return_value=('',[],False)):
      sid=bridge.start('tester')['session_id']
     before=copy.deepcopy(bridge.resume('tester',sid));err=AzureBackendError('content_filter',400,{'phase':'request','filters':[{'category':'hate','filtered':True,'severity':'medium','raw':'SECRET'}]})
     with patch.object(web,'agent_turn',side_effect=err),patch.object(web,'_retrieve_for_turn',return_value=('',[],False)):
      with self.assertRaises(BridgeError) as raised:bridge.message('tester',sid,'A benign fictional project question.')
     records=web.RESEARCH.store.records('error',owner='tester');self.assertEqual(len(records),1);r=records[0]
     self.assertIn(r['id'],str(raised.exception));self.assertEqual(r['data']['session_id'],sid);self.assertEqual(r['data']['diagnostics']['phase'],'request');self.assertNotIn('SECRET',json.dumps(r));self.assertTrue(r['data']['code_hash']);self.assertEqual(bridge.resume('tester',sid),before)
     with web.app.test_request_context('/api/message',method='POST',json={'session_id':sid}):
      web.g.participant='tester'
      with patch.object(web.RESEARCH.store,'put',side_effect=OSError('PRIVATE')),self.assertLogs(web.app.logger,level='ERROR') as logs:
       ref=web.record_failure(err,'azure_content_filter')
      self.assertIn(ref,''.join(logs.output));self.assertNotIn('PRIVATE',''.join(logs.output))
    finally:web.RESEARCH.store.close();web.DB.close()
 def test_real_gradio_reply_callback_preserves_history_on_error(self):
  import os
  from unittest.mock import patch
  import app,gradio as gr
  b=Mock();b.message.side_effect=BridgeError('Blocked. Reference: '+'b'*32)
  with patch.dict(os.environ,{'STUDY_ENABLED':'0'}):demo=app.build_demo(b)
  fn=next(f.fn for f in demo.fns.values() if f.api_name=='reply')
  history,text,status=fn('unchanged','sid',gr.Request(username='tester'))
  self.assertEqual(history,gr.skip());self.assertEqual(text,'unchanged');self.assertIn('b'*32,status)

class ClosingContractTests(unittest.TestCase):
 def test_repeated_summary_is_rejected_for_reflect_action(self):
  from pedagogical_runtime import quality_flags
  self.assertIn('repeated_closing_prompt',quality_flags('How would you summarise your rationale?',{'move':'reflect'},6))
  self.assertNotIn('repeated_closing_prompt',quality_flags('What would you record about unclear adaptation?',{'move':'reflect'},6))
  self.assertNotIn('repeated_closing_prompt',quality_flags('How would you summarise your rationale?',{'move':'summarise'},6))
 def test_explicit_unresolved_next_check_selects_reflection(self):
  a=select_action(load_all_skills(),6,[{'role':'user','content':'I still need to validate the search using backward and forward citations.'}]);self.assertEqual(a['move'],'reflect')
 def test_malformed_declarative_closing_question_rejected(self):
  from pedagogical_runtime import quality_flags
  self.assertIn('declarative_question',quality_flags('You have separated two issues: whether a paper is relevant?',{'move':'reflect'},6))
  self.assertNotIn('declarative_question',quality_flags('What evidence would distinguish those cases?',{'move':'reflect'},6))
