import copy
import unittest
from unittest.mock import patch
from tutor_actions import fit_q_policy, validate_policy, select_action, candidates
from pedagogical_runtime import prepare, critic_review, plan_alternatives, quality_flags
from skill_loader import load_all_skills
import json


class PolicyTests(unittest.TestCase):
    def setUp(self):self.skills=load_all_skills()

    def test_required_stage_questions_satisfy_quality_contract(self):
        from stages import STAGES
        for stage in STAGES.values():
            for parameter in stage.get('required_parameters',[]):
                self.assertEqual(quality_flags(parameter['question']),[],parameter['id'])

    def test_compound_question_guard_preserves_first_request(self):
        from agent import _apply_scaffolding_guard
        raw='Thanks for explaining. What degree are you studying, and what year are you in?'
        self.assertEqual(_apply_scaffolding_guard(raw,split_compound=True),
                         'Thanks for explaining. What degree are you studying?')
        self.assertEqual(_apply_scaffolding_guard('What is your research question?',split_compound=True),
                         'What is your research question?')

    def test_two_bounded_repairs_preserve_declared_action(self):
        from agent import agent_turn
        scenario={'role':'mentor','topic':'Test','task_description':'Test','learner_persona':dict(name='P',level='PhD',knowledge_state='unknown',misconception='unknown',emotional_state='unknown',learning_goal='reason')}
        action=select_action(self.skills,1,[])
        good=f"SKILL: {action['skill']}\nTUTOR_MOVE: {action['move']}\nREASONING: clarify\nSTAGE: 1\nSTAGE_COMPLETE: NO\nTASK_SOLVED: NO\nRESPONSE: What is your research question?"
        bad=good.replace('TUTOR_MOVE: '+action['move'],'TUTOR_MOVE: invalid')
        with patch('agent.call_llm',side_effect=[bad,bad,good]) as model:
            result=agent_turn(self.skills,scenario,[],[],1,expected_stage=1,research={'configuration':{'skills':'full','architecture':'single','policy':'fixed'},'protocol':{}})
        self.assertEqual(model.call_count,3)
        self.assertEqual(result['tutor_move'],action['move'])
        self.assertIn('action_mismatch',model.call_args_list[1].kwargs['system'])

    def test_compound_guard_handles_introductory_phrase(self):
        from agent import _apply_scaffolding_guard
        for raw,expected in [
            ('Given your research, how will you recruit teachers, and what constraints might apply?', 'Given your research, how will you recruit teachers?'),
            ('Thinking about your project, could you describe your experience and how you plan to build on it?', 'Thinking about your project, could you describe your experience?'),
        ]:
            corrected=_apply_scaffolding_guard(raw,split_compound=True)
            self.assertEqual(corrected,expected)
            self.assertEqual(quality_flags(corrected),[])
        self.assertEqual(_apply_scaffolding_guard('How would you compare interviews and surveys?',split_compound=True), 'How would you compare interviews and surveys?')

    def test_q_update_and_leakage_rejection(self):
        action=select_action(self.skills,1,[],epsilon=1,seed=1)
        rows=[dict(episode_id='e'+str(i),participant_id='p'+str(i),turn=t,split='train',
                   action=action,reward=1.0,terminal=t==2,enactment_verified=True) for i in range(3) for t in (1,2)]
        policy=fit_q_policy(rows,epochs=50)
        validate_policy(policy)
        self.assertEqual(policy['algorithm'],'tabular-q-v1')
        self.assertGreater(policy['values'][action['context']][action['id']]['mean'],.9)
        bad=copy.deepcopy(rows);bad[-1]['split']='test'
        with self.assertRaises(ValueError):fit_q_policy(bad)
        with self.assertRaises(ValueError):fit_q_policy([dict(r,terminal=False) for r in rows])

    def test_multiagent_calls_and_rejected_invalid_plans(self):
        choice=candidates(3,self.skills)[0]
        with patch('pedagogical_runtime.call_llm',return_value=json.dumps({'action':choice,'focus':'Research aim'})) as model:
            action,body,trace=prepare(self.skills,3,[],{'skills':'full','architecture':'planner_mentor_critic','policy':'fixed'})
            self.assertEqual(action['id'],choice)
            self.assertIsNone(action['probability'])
            self.assertIn(self.skills[action['skill']]['body'],body)
            self.assertEqual(trace[0]['role'],'planner');model.assert_called_once()
        with patch('pedagogical_runtime.call_llm',return_value='{"action":"unknown::choose"}'):
            with self.assertRaises(ValueError):prepare(self.skills,3,[],{'skills':'full','architecture':'planner_mentor_critic'})
        with patch('pedagogical_runtime.call_llm',return_value='{"acceptable":false,"issues":["method endorsement"]}'):
            self.assertFalse(critic_review('This is the best method.',[],4)['acceptable'])

    def test_procedure_templates_are_reference_not_chat_format(self):
        from agent import _system_prompt
        from human_validation import make_freeform_scenario
        action, body, _ = prepare(self.skills, 2, [],
            {'skills': 'full', 'architecture': 'single', 'policy': 'fixed'})
        self.assertIn(self.skills[action['skill']]['body'], body)
        self.assertIn('not the response format for this chat', body)
        self.assertIn('one learner-facing question', body)
        prompt = _system_prompt(self.skills, make_freeform_scenario(), [], 'Current stage: 2', action)
        self.assertNotIn('Opening the conversation — Stage 1', prompt)
        self.assertIn('TUTOR_MOVE: ' + action['move'], prompt)

    def test_description_ablation_and_reviewed_composition(self):
        config={'skills':'descriptions','architecture':'single','policy':'fixed'}
        action,body,_=prepare(self.skills,1,[],config)
        self.assertNotIn(self.skills[action['skill']]['body'],body)
        recipe={'actions':candidates(1,self.skills),'status':'approved'}
        action,_,_=prepare(self.skills,1,[],dict(config,policy='composite'),composites=[recipe],turn=2)
        self.assertEqual(action['id'],recipe['actions'][1])
        self.assertTrue(action['policy_id'].startswith('composite:'))

if __name__=='__main__':unittest.main()
