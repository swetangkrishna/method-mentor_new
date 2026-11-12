import sys,unittest
sys.path.insert(1,'/Users/swetangkrishna/.codex/.chatgpt-projects/g-p-6a5a3fea0d408191956a9ebac68aaa2b/method-mentor_new')
from pedagogical_runtime import quality_flags
class Questions(unittest.TestCase):
 def test_declarative_which_clauses_do_not_join_a_later_question(self):
  text='You can see which papers meet your criteria and which techniques find relevant papers. How will you use that information?'
  self.assertNotIn('multiple_questions',quality_flags(text))
 def test_declarative_how_clauses_before_question_are_valid(self):
  self.assertNotIn('multiple_questions',quality_flags('This shows how the approaches overlap and how they differ. What would you examine next?'))
 def test_two_actual_questions_remain_invalid(self):
  self.assertIn('multiple_questions',quality_flags('Which technique do you mean? How would you apply it?'))
 def test_actual_compound_question_remains_invalid(self):
  self.assertIn('multiple_questions',quality_flags('Which technique do you mean and how would you apply it?'))
if __name__=='__main__':unittest.main()
