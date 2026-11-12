import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(1,'/Users/swetangkrishna/.codex/.chatgpt-projects/g-p-6a5a3fea0d408191956a9ebac68aaa2b/method-mentor_new')
import agent,api_client
from human_validation import make_freeform_scenario
ACTION={'skill':'probe-intended-decisions','move':'elicit','id':'probe-intended-decisions::elicit'}
SKILLS={'probe-intended-decisions':{'name':'probe-intended-decisions','description':'Ask the learner about a decision.','body':'Ask one reflective question.'}}
VALID='SKILL: probe-intended-decisions\nTUTOR_MOVE: elicit\nREASONING: Elicit the project focus.\nSTAGE: 2\nSTAGE_COMPLETE: NO\nTASK_SOLVED: NO\nRESPONSE: What aspect of adaptive AI tutors would you like to investigate?'
class RewriteSafety(unittest.TestCase):
 def run_turn(self,responses):
  with patch('pedagogical_runtime.prepare',return_value=(ACTION.copy(),'',[])),patch.object(agent,'_is_repeated_question',return_value=True),patch.object(agent,'call_llm',side_effect=responses) as call:
   result=agent.agent_turn(SKILLS,make_freeform_scenario(),[{'role':'assistant','content':'What is your project?'},{'role':'user','content':'adaptive AI tutor'}],[],3,expected_stage=2,research={'configuration':{'architecture':'single'},'protocol':{}})
   return result,call.call_count
 def test_optional_filtered_rewrite_keeps_valid_initial_candidate(self):
  result,n=self.run_turn([VALID,api_client.AzureBackendError('content_filter')])
  self.assertEqual(n,2);self.assertIn('adaptive AI tutors',result['response']);self.assertEqual(result['quality_flags'],[])
  self.assertEqual(result['model_trace'][0]['issues'],['provider_content_filter'])
 def test_optional_malformed_rewrite_keeps_valid_initial_candidate(self):
  result,n=self.run_turn([VALID,api_client.AzureBackendError('invalid_protocol')])
  self.assertEqual(n,2);self.assertEqual(result['quality_flags'],[])
  self.assertEqual(result['model_trace'][0]['issues'],['format_validation'])
 def test_primary_malformed_response_still_stops_turn(self):
  with self.assertRaises(api_client.AzureBackendError):self.run_turn([api_client.AzureBackendError('invalid_protocol')])
 def test_primary_block_still_stops_turn(self):
  with self.assertRaises(api_client.AzureBackendError):self.run_turn([api_client.AzureBackendError('content_filter')])
 def test_transport_failure_not_suppressed(self):
  with self.assertRaises(api_client.AzureBackendError):self.run_turn([VALID,api_client.AzureBackendError('transport')])
 def test_invalid_initial_candidate_still_requires_repair(self):
  with self.assertRaises(api_client.AzureBackendError):self.run_turn([VALID.replace('TUTOR_MOVE: elicit','TUTOR_MOVE: reflect'),api_client.AzureBackendError('content_filter'),api_client.AzureBackendError('content_filter')])
 def test_provider_label_only_extraction(self):
  d=api_client._filter_diagnostics({'choices':[{'content_filter_results':{'error':{'code':'content_filter','message':"Response content blocked by label 'Jailbreak'."}}}]},'request')
  self.assertEqual(d['filters'],[{'category':'jailbreak','filtered':True}])
 def test_unknown_label_not_logged(self):
  d=api_client._filter_diagnostics({'error':{'code':'content_filter','message':"Response content blocked by label 'PRIVATE'."}},'request')
  self.assertEqual(d['filters'],[])
if __name__=='__main__':unittest.main()
