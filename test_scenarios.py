"""
scenarios.py — Scenario definitions and survey questions.
Add new scenarios here to expand the 72-scenario matrix.
"""

SCENARIOS = {
    "S01_recursion_confused_beginner": {
        "id": "S01",
        "skill_target": "scaffold-and-release",
        "role": "tutor",
        "topic": "Python recursion",
        "task_description": (
            "Teach a confused beginner to write a correct recursive function "
            "with a base case and a recursive case in Python."
        ),
        "learner_persona": {
            "name": "Alex",
            "level": "beginner",
            "knowledge_state": (
                "Knows Python for-loops and basic functions. "
                "Has never written a recursive function. "
                "Thinks recursion means calling a function from inside a loop."
            ),
            "misconception": (
                "Believes recursion requires a for-loop. "
                "Does not understand the base-case concept — "
                "writes infinite recursion without realising it."
            ),
            "emotional_state": "mildly anxious, afraid of looking stupid",
            "learning_goal": (
                "Write a recursive factorial(n) function with a proper base case "
                "(n==0 or n==1 returns 1) and recursive call (n * factorial(n-1))."
            ),
        },
        "task_solved_criteria": (
            "Learner has written or described a correct recursive factorial function "
            "with an explicit base case and recursive call, and can explain WHY the "
            "base case is needed."
        ),
        "max_turns": 12,
    },

    "S02_lesson_plan_alignment": {
        "id": "S02",
        "skill_target": "align-outcomes-activities-assessment",
        "role": "educator",
        "topic": "Lesson plan constructive alignment",
        "task_description": (
            "Help an educator identify and fix a misalignment between "
            "learning objective, activity, and assessment in their lesson plan."
        ),
        "learner_persona": {
            "name": "Dr. Priya",
            "level": "practising teacher (5 years experience)",
            "knowledge_state": (
                "Knows how to write lesson plans. Familiar with learning objectives. "
                "Has not heard of Bloom's taxonomy explicitly."
            ),
            "misconception": (
                "Believes 'understand' is a good verb for a learning objective. "
                "Does not see that her multiple-choice assessment contradicts her "
                "stated objective of 'critically evaluate'."
            ),
            "emotional_state": "confident but open, slightly defensive",
            "learning_goal": (
                "Revise her lesson plan so objective, activity, and assessment all "
                "target the same Bloom level."
            ),
        },
        "task_solved_criteria": (
            "Educator has revised objective to use a testable verb, identified the "
            "misalignment, and proposed a revised assessment matching the objective."
        ),
        "max_turns": 10,
    },

    "S03_list_comprehensions": {
        "id": "S03",
        "skill_target": "diagnose-zpd",
        "role": "tutor",
        "topic": "Python list comprehensions",
        "task_description": (
            "Diagnose the learner's ZPD for list comprehensions "
            "and pitch instruction at exactly the right level."
        ),
        "learner_persona": {
            "name": "Mei",
            "level": "intermediate beginner",
            "knowledge_state": (
                "Can write for-loops confidently. Has seen list comprehensions "
                "once but cannot write them. Can write conditional if-statements."
            ),
            "misconception": (
                "Thinks list comprehensions are just a shorter for-loop and does not "
                "understand the expression-first ordering."
            ),
            "emotional_state": "curious and motivated, not anxious",
            "learning_goal": (
                "Write a conditional list comprehension independently: "
                "[x*2 for x in range(10) if x % 2 == 0]"
            ),
        },
        "task_solved_criteria": (
            "Learner has written a correct conditional list comprehension independently "
            "and can explain the position of expression, iterable, and condition."
        ),
        "max_turns": 10,
    },
}

SURVEY_QUESTIONS = [
    {
        "id": "Q1",
        "question": "How well did the tutor/teacher understand what you were confused about?",
        "scale": "1 (not at all) to 5 (completely)",
    },
    {
        "id": "Q2",
        "question": "Did the explanations feel right for your level — not too hard, not too easy?",
        "scale": "1 (very poorly calibrated) to 5 (perfectly calibrated)",
    },
    {
        "id": "Q3",
        "question": "Did you feel supported emotionally — safe to be wrong without embarrassment?",
        "scale": "1 (not at all) to 5 (completely)",
    },
    {
        "id": "Q4",
        "question": "How efficient was the interaction — did it take too many turns, or feel rushed?",
        "scale": "1 (very inefficient) to 5 (very efficient)",
    },
    {
        "id": "Q5",
        "question": "Overall, how satisfied are you with this learning interaction?",
        "scale": "1 (very unsatisfied) to 5 (very satisfied)",
    },
    {
        "id": "Q_open",
        "question": "In 1-2 sentences: what was the most helpful thing the tutor did, and what could be better?",
        "scale": "open text",
    },
]
