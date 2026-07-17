"""
scenarios.py — Scenario definitions for the RL experiment.

Based on three real supervisor-student dialogues (Scenario A):
  S01 — Mary, PhD student, research methods for digital tools in geography
  S02 — John, Masters student, parent-teacher transition study
  S03 — Liam, PhD student, PISA large-scale quantitative analysis

The AGENT plays the role of AOIFE (academic supervisor / mentor).
The PERSONA plays the role of the student (Mary / John / Liam).

The dialogues are grounded in real PhD/Masters supervisory conversations.
The supervisor's role is to guide the student toward a methodologically
sound decision through Socratic questioning, scaffolding, and confidence-building
— not to give the answer directly.
"""

SCENARIOS = {

    # ── Scenario S01: Mary — PhD, Digital Tools in Geography ─────────────────
    "S01_digital_tools_geography_interviews": {
        "id": "S01",
        "skill_target": "probe-intended-decisions",
        "role": "mentor",
        "topic": "Research methods for teachers' perceptions of digital tools in geography",
        "task_description": (
            "Guide Mary, a second-year PhD student, to justify and feel confident "
            "about choosing semi-structured interviews as her research method. "
            "She already leans toward interviews but doubts herself, thinking "
            "she needs a 'stronger' or more complex design. "
            "The supervisor's goal is to help Mary reason through the options "
            "herself and arrive at a well-justified methodological choice — "
            "not to tell her the answer."
        ),
        "learner_persona": {
            "name": "Mary",
            "level": "second-year full-time PhD student in Education",
            "knowledge_state": (
                "Mary has done a research methods module and has experience with "
                "thematic analysis. She knows qualitative methods broadly but "
                "has not designed a full study before. She is comfortable with "
                "interviews conceptually but unfamiliar with the justification process. "
                "She has limited stats knowledge and is uncomfortable with surveys."
            ),
            "misconception": (
                "Believes a 'stronger' study necessarily uses more complex or "
                "mixed methods. Thinks semi-structured interviews alone might be "
                "'too simple' and not rigorous enough for a PhD. Has not fully "
                "considered that method-question alignment matters more than complexity."
            ),
            "emotional_state": (
                "Anxious about making the wrong choice. Relieved when given permission "
                "to stay qualitative. Responds well to Socratic questioning. "
                "Becomes more confident when her reasoning is validated."
            ),
            "learning_goal": (
                "Mary should be able to: (1) explain why semi-structured interviews "
                "align with her exploratory, interpretivist research question, "
                "(2) acknowledge the limitations of alternatives (surveys, observation, "
                "mixed methods) for her specific question and context, "
                "(3) articulate a confident methodological justification without "
                "feeling she needs to use a more complex design."
            ),
        },
        "task_solved_criteria": (
            "Mary can articulate in her own words why semi-structured interviews "
            "are appropriate for her research question, acknowledges the trade-offs "
            "of at least one alternative method, and expresses confidence in her "
            "methodological choice rather than anxiety about its complexity."
        ),
        # ── 6-stage MethodCheck profile ──────────────────────────────────────
        "stage_profile": {
            "research_question": (
                "How do primary-school teachers perceive using digital tools for "
                "teaching geography?"
            ),
            "tentative_method": "semi-structured interviews with ~10 teachers",
            "comfort_zone": "qualitative",   # used to pick the 'opposite' in Stage 4
            "programme": "second-year full-time PhD in Education",
            "research_aim": "exploratory",
            "epistemology": "interpretivist",
            # Three plausible alternatives for Stage 4. At least one must be the
            # opposite of the comfort zone (here, a quantitative option).
            "stage4_alternatives": [
                {"method": "Online survey of teachers",
                 "family": "quantitative",
                 "note": "Opposite of comfort zone — breadth across many teachers."},
                {"method": "Classroom observation",
                 "family": "qualitative",
                 "note": "Captures practice in situ rather than reported perception."},
                {"method": "Mixed methods (survey + follow-up interviews)",
                 "family": "mixed",
                 "note": "Combines breadth and depth at the cost of added complexity."},
            ],
        },
        "max_turns": 40,
    },

    # ── Scenario S02: John — Masters, Parent-Teacher Transitions ─────────────
    "S02_parent_transition_interviews": {
        "id": "S02",
        "skill_target": "scaffold-and-release",
        "role": "mentor",
        "topic": "Research methods for parents' experiences of school transition",
        "task_description": (
            "Guide John, a first-year Masters student, from vague uncertainty "
            "about research methods to a clear, justified decision about how to "
            "collect data on parents' experiences during their child's transition "
            "to secondary school. John feels he should already know what method "
            "to choose but doesn't. Help him see that the decision flows from his "
            "research question, not from a rule about which methods are best."
        ),
        "learner_persona": {
            "name": "John",
            "level": "first-year Masters student in Education",
            "knowledge_state": (
                "John has completed a research methods module. He knows that "
                "interviews, surveys, and focus groups exist but cannot connect "
                "them to his specific research question. He is a parent himself "
                "and has some personal access to other parents, though he hasn't "
                "thought about this as a research asset. He is uncomfortable with "
                "statistics. He has not thought about ethical approval or school "
                "permissions yet."
            ),
            "misconception": (
                "Feels he should already know the right method from the methods "
                "module — this causes anxiety. Does not yet see that method choice "
                "follows from the research question. Has not connected his personal "
                "parent network to his access problem. Does not realise that a "
                "small sample is appropriate for a Masters qualitative study."
            ),
            "emotional_state": (
                "Uncertain and slightly overwhelmed. Reassured when told that "
                "uncertainty at this stage is normal. Responds positively to "
                "being guided through reasoning step by step. Becomes more "
                "confident when the logic of method selection is made explicit."
            ),
            "learning_goal": (
                "John should be able to: (1) connect his research question "
                "(understanding parents' experiences) to the type of data that "
                "would answer it, (2) identify interviews as a suitable approach "
                "and explain why (depth of understanding, feasibility, his skills), "
                "(3) begin drafting a short data collection description, "
                "(4) feel less overwhelmed about not knowing the 'right' answer immediately."
            ),
        },
        "task_solved_criteria": (
            "John can explain in his own words why interviews (rather than surveys "
            "or focus groups) suit his research question about parents' experiences, "
            "identifies at least one practical consideration (access, feasibility, "
            "timeline), and is ready to draft a short data collection description."
        ),
        # ── 6-stage MethodCheck profile ──────────────────────────────────────
        "stage_profile": {
            "research_question": (
                "What are parents' experiences of their child's transition to "
                "secondary school?"
            ),
            "tentative_method": "unsure — has not yet chosen a method",
            "comfort_zone": "qualitative",
            "programme": "first-year Masters in Education (part-time)",
            "research_aim": "exploratory",
            "epistemology": "interpretivist",
            "stage4_alternatives": [
                {"method": "Parent survey with Likert and open items",
                 "family": "quantitative",
                 "note": "Opposite of comfort zone — reaches many parents quickly."},
                {"method": "One-to-one semi-structured interviews",
                 "family": "qualitative",
                 "note": "Depth on individual transition experiences."},
                {"method": "Focus groups with parents",
                 "family": "qualitative",
                 "note": "Group dynamics surface shared and divergent experiences."},
            ],
        },
        "max_turns": 40,
    },

    # ── Scenario S03: Liam — PhD, PISA Quantitative Analysis ─────────────────
    "S03_pisa_secondary_data_analysis": {
        "id": "S03",
        "skill_target": "diagnose-zpd",
        "role": "mentor",
        "topic": "Quantitative secondary data analysis using the PISA dataset",
        "task_description": (
            "Guide Liam, a PhD student interested in large-scale educational datasets, "
            "to refine his research question so it is feasible within the PISA dataset, "
            "identify the statistical skills he needs to develop, and reflect on "
            "what large-scale datasets can and cannot tell him. Liam is drawn to "
            "PISA because it seems 'powerful' but has not yet thought carefully about "
            "whether the dataset contains the variables he needs or whether his skills "
            "are sufficient."
        ),
        "learner_persona": {
            "name": "Liam",
            "level": "PhD student in Education (year not specified)",
            "knowledge_state": (
                "Liam has some background in basic statistics (regression). "
                "He has briefly explored the PISA dataset but not in depth. "
                "He knows the PISA dataset is large and international. "
                "He is drawn to quantitative methods and positivist evidence. "
                "He understands that surveys measure broad patterns and interviews "
                "provide depth, but has not applied this distinction to his own study."
            ),
            "misconception": (
                "Believes larger datasets are automatically more powerful or rigorous. "
                "Has not checked whether PISA contains the specific variables needed "
                "for his research question. Has not fully considered the complexity "
                "of PISA's weighting structure or that he may need to develop "
                "additional statistical skills. Has not considered whether a smaller, "
                "more focused dataset might serve his question better."
            ),
            "emotional_state": (
                "Enthusiastic about big data but not yet critically reflective. "
                "Responds well to questions that make him think about alignment "
                "between the dataset and his question. Becomes more thoughtful "
                "when shown that dataset choice is not just about size."
            ),
            "learning_goal": (
                "Liam should be able to: (1) explain how his research question "
                "drives the choice of dataset, not the other way round, "
                "(2) identify specific PISA variables relevant to his question, "
                "(3) acknowledge the statistical skills he needs to develop "
                "(weighting structures, complex modelling), "
                "(4) reflect on what large-scale datasets cannot capture "
                "that qualitative methods might."
            ),
        },
        "task_solved_criteria": (
            "Liam can articulate why his research question — not the dataset's size — "
            "should drive the choice of PISA, names at least two PISA variables "
            "relevant to his question, acknowledges one statistical skill he needs "
            "to develop, and is ready to explore the PISA codebook to refine his "
            "research question further."
        ),
        # ── 6-stage MethodCheck profile ──────────────────────────────────────
        "stage_profile": {
            "research_question": (
                "What factors in the PISA dataset relate to students' academic "
                "outcomes across countries?"
            ),
            "tentative_method": "secondary analysis of the PISA large-scale dataset",
            "comfort_zone": "quantitative",
            "programme": "PhD in Education (year not specified)",
            "research_aim": "explanatory",
            "epistemology": "positivist",
            "stage4_alternatives": [
                {"method": "Qualitative interviews with students/teachers",
                 "family": "qualitative",
                 "note": "Opposite of comfort zone — depth on the 'why' behind patterns."},
                {"method": "A smaller, focused primary survey",
                 "family": "quantitative",
                 "note": "Variables designed for the exact question, but smaller scale."},
                {"method": "Mixed methods (PISA analysis + interviews)",
                 "family": "mixed",
                 "note": "Pairs large-scale patterns with explanatory depth."},
            ],
        },
        "max_turns": 40,
    },
}

SURVEY_QUESTIONS = [
    {
        "id": "Q1",
        "question": "How well did the supervisor understand what you were confused or uncertain about?",
        "scale": "1 (not at all) to 5 (completely)",
    },
    {
        "id": "Q2",
        "question": "Did the questions and guidance feel right for your level — not too directive, not too vague?",
        "scale": "1 (very poorly calibrated) to 5 (perfectly calibrated)",
    },
    {
        "id": "Q3",
        "question": "Did you feel safe to express uncertainty or confusion without embarrassment?",
        "scale": "1 (not at all) to 5 (completely)",
    },
    {
        "id": "Q4",
        "question": "How efficient was the conversation — did it take the right number of turns to reach clarity?",
        "scale": "1 (very inefficient) to 5 (very efficient)",
    },
    {
        "id": "Q5",
        "question": "Overall, how satisfied are you with this supervisory interaction?",
        "scale": "1 (very unsatisfied) to 5 (very satisfied)",
    },
    {
        "id": "Q_open",
        "question": "What was the most helpful thing the supervisor did, and what could have been better?",
        "scale": "open text",
    },
]