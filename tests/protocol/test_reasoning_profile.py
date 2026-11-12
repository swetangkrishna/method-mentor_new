import copy,io,json,os,unittest,urllib.error
from unittest.mock import patch
import api_client as api
from test_json_protocol import FIELDS,CFG,response
class ReasoningProfile(unittest.TestCase):
 def run_calls(self,answers,prefill='SKILL: '):
  captured=[]
  def post(url,payload,headers,timeout):
   captured.append(copy.deepcopy(payload));return answers.pop(0)
  with patch.object(api,'_post_urllib',side_effect=post):
   out=api._call_azure_foundry([],'Tutor',700,0.2,dict(CFG,request_profile='reasoning'),prefill)
  return out,captured
 def test_reasoning_uses_completion_limit_and_supported_parameters(self):
  out,calls=self.run_calls([response(FIELDS)])
  self.assertTrue(out.startswith('SKILL: '));self.assertEqual(calls[0]['max_completion_tokens'],1600)
  self.assertNotIn('max_tokens',calls[0]);self.assertNotIn('temperature',calls[0])
  self.assertEqual(calls[0]['response_format'],{'type':'json_object'})
 def test_classic_profile_keeps_existing_request(self):
  with patch.object(api,'_post_urllib',return_value=response(FIELDS)) as post:
   api._call_azure_foundry([],'Tutor',700,0.2,CFG,'SKILL: ')
  self.assertEqual(post.call_args.args[1]['max_tokens'],700);self.assertEqual(post.call_args.args[1]['temperature'],0.2)
  self.assertNotIn('max_completion_tokens',post.call_args.args[1])
 def test_format_repair_keeps_supported_parameters(self):
  out,calls=self.run_calls([response({'RESPONSE':'question?'}),response(FIELDS)])
  self.assertEqual(len(calls),2)
  for p in calls:self.assertNotIn('temperature',p);self.assertNotIn('max_tokens',p)
 def test_truncation_retry_raises_completion_limit(self):
  truncated={'choices':[{'message':{'content':'unfinished'},'finish_reason':'length'}]}
  out,calls=self.run_calls([truncated,response(FIELDS)])
  self.assertEqual([p['max_completion_tokens'] for p in calls],[1600,3200])
 def test_prefix_retry_keeps_supported_parameters(self):
  out,calls=self.run_calls([{'choices':[{'message':{'content':'wrong'},'finish_reason':'stop'}]},{'choices':[{'message':{'content':'ANSWER: supported'},'finish_reason':'stop'}]}],'ANSWER: ')
  self.assertEqual(out,'ANSWER: supported');self.assertEqual(len(calls),2)
  for p in calls:self.assertNotIn('temperature',p)
 def test_provenance_records_provider_default_temperature(self):
  import study_protocol
  v=study_protocol.provenance({},dict(CFG,backend='azure_foundry',request_profile='reasoning'))
  self.assertIsNone(v['temperature']);self.assertEqual(v['temperature_control'],'provider_default')
  self.assertEqual(v['request_profile'],'reasoning');self.assertEqual(v['minimum_completion_tokens'],1600)
 def test_provenance_retains_classic_temperature(self):
  import study_protocol
  v=study_protocol.provenance({},dict(CFG,backend='azure_foundry'))
  self.assertEqual(v['temperature'],0.2);self.assertEqual(v['request_profile'],'classic')
 def test_token_quota_reset_is_honored_with_bounded_retry(self):
  error=urllib.error.HTTPError('https://example.invalid',429,'rate limit',{'Retry-After':'30'},io.BytesIO(b'{}'))
  with patch.object(api,'_post_urllib',side_effect=[error,response(FIELDS)]) as post,patch.object(api.time,'sleep') as sleep:
   out=api._call_azure_foundry([],'Tutor',700,0.2,dict(CFG,request_profile='reasoning'),'SKILL: ')
  self.assertTrue(out.startswith('SKILL: '));self.assertEqual(post.call_count,2);sleep.assert_called_once_with(30)
 def test_excessive_quota_wait_is_not_retried(self):
  error=urllib.error.HTTPError('https://example.invalid',429,'rate limit',{'Retry-After':'300'},io.BytesIO(b'{}'))
  with patch.object(api,'_post_urllib',side_effect=error) as post,patch.object(api.time,'sleep') as sleep:
   with self.assertRaises(api.AzureBackendError) as caught:api._call_azure_foundry([],'Tutor',700,0.2,dict(CFG,request_profile='reasoning'),'SKILL: ')
  self.assertEqual(caught.exception.category,'http_429');self.assertEqual(post.call_count,1);sleep.assert_not_called()
 def test_server_error_keeps_short_wait_bound(self):
  error=urllib.error.HTTPError('https://example.invalid',503,'unavailable',{'Retry-After':'30'},io.BytesIO(b'{}'))
  with patch.object(api,'_post_urllib',side_effect=error) as post,patch.object(api.time,'sleep') as sleep:
   with self.assertRaises(api.AzureBackendError):api._call_azure_foundry([],'Tutor',700,0.2,dict(CFG,request_profile='reasoning'),'SKILL: ')
  self.assertEqual(post.call_count,1);sleep.assert_not_called()
 def test_configuration_rejects_unknown_profile(self):
  import model_config
  with patch.dict(os.environ,{'LLM_BACKEND':'azure_foundry','AZURE_FOUNDRY_ENDPOINT':'https://example.invalid/openai/v1','AZURE_FOUNDRY_KEY':'TEST','AZURE_FOUNDRY_REQUEST_PROFILE':'unknown'}):
   with self.assertRaises(ValueError):model_config.get_config()
if __name__=='__main__':unittest.main()
