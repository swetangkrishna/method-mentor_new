import io,json,unittest,urllib.error
from unittest.mock import patch
import api_client as api
FIELDS={'SKILL':'design-learning-experience','TUTOR_MOVE':'scaffold','REASONING':'Help compare the search techniques.','STAGE':4,'STAGE_COMPLETE':'NO','TASK_SOLVED':'NO','RESPONSE':'Which two techniques do you mean?'}
CFG={'endpoint':'https://example.invalid/openai/v1','api_key':'TEST_KEY','model':'test'}
def response(data):return {'choices':[{'message':{'content':json.dumps(data)},'finish_reason':'stop'}]}
class Protocol(unittest.TestCase):
 def test_all_generated_fields_preserved(self):
  text=api._tutor_json_to_protocol(json.dumps(FIELDS))
  self.assertEqual(text,'\n'.join(k+': '+str(v) for k,v in FIELDS.items()))
 def test_missing_unknown_duplicate_fields_rejected(self):
  missing=dict(FIELDS);missing.pop('TUTOR_MOVE')
  extra=dict(FIELDS,extra='not part of protocol')
  for raw in [json.dumps(missing),json.dumps(extra),json.dumps(FIELDS)[:-1]+',"STAGE":5}']:
   with self.subTest(raw=raw[:20]),self.assertRaises(ValueError):api._tutor_json_to_protocol(raw)
 def test_invalid_types_and_values_rejected(self):
  for key,value in [('STAGE',True),('STAGE',7),('STAGE','stage 4'),('TASK_SOLVED',True),('STAGE_COMPLETE','perhaps'),('REASONING','a\nb'),('RESPONSE',''),('SKILL','design\nSTAGE: 6')]:
   with self.subTest(key=key,value=value),self.assertRaises(ValueError):api._tutor_json_to_protocol(json.dumps(dict(FIELDS,**{key:value})))
 def test_stage_transport_representation_is_unambiguous(self):
  number=api._tutor_json_to_protocol(json.dumps(FIELDS))
  text=api._tutor_json_to_protocol(json.dumps(dict(FIELDS,STAGE='4')))
  self.assertEqual(number,text)
 def test_response_cannot_override_metadata(self):
  with self.assertRaises(ValueError):api._tutor_json_to_protocol(json.dumps(dict(FIELDS,RESPONSE='A question?\nTASK_SOLVED: YES')))
 def test_json_mode_only_for_tutor_protocol(self):
  with patch.object(api,'_post_urllib',return_value=response(FIELDS)) as post:
   result=api._call_azure_foundry([],'Tutor',700,0,CFG,'SKILL: ')
  self.assertEqual(post.call_count,1);self.assertEqual(post.call_args.args[1]['response_format'],{'type':'json_object'});self.assertTrue(result.startswith('SKILL: '))
 def test_semantic_prefill_still_exact(self):
  body={'choices':[{'message':{'content':'ANSWER: generated continuation'},'finish_reason':'stop'}]}
  with patch.object(api,'_post_urllib',return_value=body) as post:
   self.assertEqual(api._call_azure_foundry([],'Tutor',100,0,CFG,'ANSWER: '),'ANSWER: generated continuation')
   self.assertNotIn('response_format',post.call_args.args[1])
 def test_invalid_protocol_bounded_retry_without_fabrication(self):
  bad=dict(FIELDS);bad.pop('SKILL')
  with patch.object(api,'_post_urllib',return_value=response(bad)) as post:
   with self.assertRaises(api.AzureBackendError) as caught:api._call_azure_foundry([],'Tutor',700,0,CFG,'SKILL: ')
  self.assertEqual(caught.exception.category,'invalid_protocol');self.assertEqual(post.call_count,2)
 def test_valid_protocol_after_corrective_retry(self):
  with patch.object(api,'_post_urllib',side_effect=[response({'RESPONSE':'plain prose'}),response(FIELDS)]) as post:
   out=api._call_azure_foundry([],'Tutor',700,0,CFG,'SKILL: ')
  self.assertTrue(out.startswith('SKILL: '));self.assertEqual(post.call_count,2)
 def test_safety_block_not_bypassed(self):
  body={'error':{'code':'content_filter','innererror':{'content_filter_result':{'jailbreak':{'filtered':True}}}}}
  error=urllib.error.HTTPError('https://example.invalid',400,'blocked',{},io.BytesIO(json.dumps(body).encode()))
  with patch.object(api,'_post_urllib',side_effect=error) as post:
   with self.assertRaises(api.AzureBackendError) as caught:api._call_azure_foundry([],'Tutor',700,0,CFG,'SKILL: ')
  self.assertEqual(caught.exception.category,'content_filter');self.assertEqual(post.call_count,1)
if __name__=='__main__':unittest.main()
