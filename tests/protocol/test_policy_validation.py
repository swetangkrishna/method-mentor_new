import sys,json,unittest
from unittest.mock import patch
sys.path.insert(1,'/Users/swetangkrishna/.codex/.chatgpt-projects/g-p-6a5a3fea0d408191956a9ebac68aaa2b/method-mentor_new')
import api_client,agent
from human_validation import make_freeform_scenario
ACTION={'skill':'probe-intended-decisions','move':'elicit','id':'probe-intended-decisions::elicit'}
SKILLS={'probe-intended-decisions':{'name':'probe-intended-decisions','description':'Ask the learner about a decision.','body':'Ask one reflective question.'}}
CFG={'backend':'azure_foundry','endpoint':'https://example.invalid/openai/v1','api_key':'TEST_KEY','model':'test'}
def body(move):
 d={'SKILL':'probe-intended-decisions','TUTOR_MOVE':move,'REASONING':'Clarify the intended techniques.','STAGE':'2','STAGE_COMPLETE':'NO','TASK_SOLVED':'NO','RESPONSE':'Which two techniques do you mean?'}
 return {'choices':[{'message':{'content':json.dumps(d)},'finish_reason':'stop'}]}
class Policy(unittest.TestCase):
 def turn(self):return agent.agent_turn(SKILLS,make_freeform_scenario(),[{'role':'user','content':'Both techniques'}],[],2,expected_stage=2,research={'configuration':{'architecture':'single'},'protocol':{}})
 def test_wrong_generated_action_is_rejected_not_relabelled(self):
  with patch('pedagogical_runtime.prepare',return_value=(ACTION.copy(),'',[])),patch.object(agent,'_is_repeated_question',return_value=False),patch.object(api_client,'get_config',return_value=CFG),patch.object(api_client,'_post_urllib',return_value=body('reflect')):
   with self.assertRaisesRegex(ValueError,'action_mismatch'):self.turn()
 def test_correct_generated_action_passes_existing_validation(self):
  with patch('pedagogical_runtime.prepare',return_value=(ACTION.copy(),'',[])),patch.object(agent,'_is_repeated_question',return_value=False),patch.object(api_client,'get_config',return_value=CFG),patch.object(api_client,'_post_urllib',return_value=body('elicit')):
   a=self.turn();self.assertEqual(a['tutor_move'],'elicit');self.assertEqual(a['response'],'Which two techniques do you mean?');self.assertEqual(a['quality_flags'],[])
if __name__=='__main__':unittest.main()
