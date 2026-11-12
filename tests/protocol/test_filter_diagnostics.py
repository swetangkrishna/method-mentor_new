import io,json,unittest,urllib.error
from unittest.mock import patch
import api_client as api
class Diagnostics(unittest.TestCase):
 def test_labels_only(self):
  d=api._filter_diagnostics({'error':{'message':'PRIVATE TEXT','innererror':{'content_filter_result':{'jailbreak':{'detected':True,'filtered':True,'message':'PRIVATE TEXT'},'sexual':{'filtered':False,'severity':'safe'},'private_category':{'filtered':True}}}}},'request')
  self.assertEqual(d,{'phase':'request','filters':[{'category':'jailbreak','filtered':True,'detected':True},{'category':'sexual','filtered':False,'severity':'safe'}]})
  self.assertNotIn('PRIVATE',json.dumps(d))
 def test_request_filter_one_attempt(self):
  body={'error':{'code':'content_filter','message':'PRIVATE TEXT','innererror':{'content_filter_result':{'jailbreak':{'filtered':True,'detected':True}}}}}
  error=urllib.error.HTTPError('https://example.invalid',400,'blocked',{},io.BytesIO(json.dumps(body).encode()))
  with patch.object(api,'_post_urllib',side_effect=error) as post:
   with self.assertRaises(api.AzureBackendError) as caught:api._call_azure_foundry([], 'Tutor',100,0,{'endpoint':'https://example.invalid/openai/v1','api_key':'PRIVATE_KEY','model':'test'})
  self.assertEqual(post.call_count,1);self.assertEqual(caught.exception.diagnostics['phase'],'request');self.assertNotIn('PRIVATE',str(caught.exception))
 def test_completion_filter(self):
  body={'choices':[{'message':{'content':'PRIVATE TEXT'},'finish_reason':'content_filter','content_filter_results':{'violence':{'filtered':True,'severity':'medium'}}}]}
  with patch.object(api,'_post_urllib',return_value=body):
   with self.assertRaises(api.AzureBackendError) as caught:api._call_azure_foundry([], 'Tutor',100,0,{'endpoint':'https://example.invalid/openai/v1','api_key':'PRIVATE_KEY','model':'test'})
  self.assertEqual(caught.exception.diagnostics,{'phase':'completion','filters':[{'category':'violence','filtered':True,'severity':'medium'}]})
if __name__=='__main__':unittest.main()
