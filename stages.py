"""
stages.py — The 6-stage MethodCheck conversation framework.

Extracted directly from Scenario A (MethodCheck: Reflective comparison of
research methods to support research method decision making).

The 6 stages define the STRUCTURE of the conversation. They are orthogonal to
the pedagogical SKILLS (which define HOW the agent acts at each turn). A single
stage may span several turns and use several different skills.

Key rules from Scenario A:
  - The agent MAY skip stages when the student has already volunteered the
    information that stage would gather.
  - The student is free to discontinue at any stage.
  - Stage 4 (present alternatives) cannot begin until Stages 1-3 have produced
    enough information to synthesise three plausible alternative methods.
  - At least one method presented in Stage 4 must be the OPPOSITE of the
    student's stated comfort zone (Stage 2).
  - Stages move forward or are skipped; they never move backward.
  - The agent never selects a method for the student and never ranks one method
    as superior unless the student's own reflection supports it.
"""

from typing import Dict, List, Optional

# ── Stage definitions ─────────────────────────────────────────────────────────
# Each stage carries: number, name, trigger, action, purpose, and the
# completion_criteria the stage tracker uses to decide the stage is satisfied.

STAGES: Dict[int, Dict] = {
    1: {
        "number": 1,
        "name": "Initial prompt",
        "trigger": "Initial prompt",
        "action": (
            "Ask the user to describe their research question, the methods they "
            "are thinking of using (where available), and their prior experience "
            "of methods."
        ),
        "purpose": (
            "To understand the student's research question and the initial "
            "research method they might be using. This guides the selection of "
            "alternative methods in Stage 4."
        ),
        "completion_criteria": (
            "The student has stated a research question AND has either named a "
            "tentative method or explicitly said they are unsure which method to use."
        ),
        "example_opening": (
            "Tell me a little about your research question and the methods you are "
            "thinking of using. We will reflect on this together and discuss "
            "different research methods that might fit. If you do not know what "
            "method you are thinking of using yet, don't worry — we can discuss "
            "this together."
        ),
    },
    2: {
        "number": 2,
        "name": "Onboarding",
        "trigger": "Onboarding prompt",
        "action": (
            "Ask onboarding questions about the student's programme (full/part "
            "time, PhD or Masters, year of study) and whether they are more "
            "comfortable with qualitative or quantitative methods."
        ),
        "purpose": (
            "To gain knowledge of the student's background to guide the "
            "scaffolded reflection in Stage 5, and to determine the student's "
            "comfort zone so that Stage 4 can include at least one method from "
            "outside it."
        ),
        "completion_criteria": (
            "The student's programme/level/timeline is known AND their "
            "qualitative-vs-quantitative comfort is known."
        ),
    },
    3: {
        "number": 3,
        "name": "Clarification of the research question",
        "trigger": "Clarification of research question prompts",
        "action": (
            "Ask clarification questions about the aim of the research "
            "(explanatory, exploratory, or evaluative), the type of data needed "
            "to answer it, and the kind of evidence the student finds convincing "
            "(positivist / interpretivist / pragmatic). Provide brief contextual "
            "explanation of each option where helpful."
        ),
        "purpose": (
            "To clarify the purpose and scope of the research question so that "
            "appropriate alternative research methods can be identified and "
            "presented in Stage 4."
        ),
        "completion_criteria": (
            "The research aim (explanatory/exploratory/evaluative) is clarified "
            "AND the type of data or epistemological stance is at least partially "
            "established."
        ),
    },
    4: {
        "number": 4,
        "name": "Present alternative research methods",
        "trigger": "Present alternative research methods",
        "action": (
            "Present a high-level summary of THREE plausible alternative research "
            "methods that align with the student's answers in Stages 1-3. For "
            "each: describe the method, its application, and a practical example "
            "of its use in a SIMILAR context (not the student's own). Guide "
            "reflection on each method in turn before moving to the next. At "
            "least one method MUST be the opposite of the student's stated "
            "comfort zone from Stage 2."
        ),
        "purpose": (
            "To broaden the student's awareness of alternative research methods "
            "that could address their research question and provide options for "
            "reflective comparison in Stage 5."
        ),
        "completion_criteria": (
            "Three alternative methods have been presented, with at least one "
            "from outside the student's comfort zone."
        ),
        "gated": True,  # cannot begin until stages 1-3 are complete
    },
    5: {
        "number": 5,
        "name": "Scaffold reflective consideration of each method",
        "trigger": "Scaffolding reflective consideration of research methods",
        "action": (
            "Guide the student, one method at a time, through reflective "
            "questions about feasibility constraints and alignment with the "
            "research question. Constraints include: timeline, participant "
            "access, analysis skills, ethical approval, volume of data, and "
            "research-question alignment (purpose, epistemology, depth vs "
            "breadth, generalisability). Provide a practical example for each "
            "question. Ask about each method in turn — never present all "
            "reflection questions at once."
        ),
        "purpose": (
            "To support the student in reflecting on the practical and "
            "methodological suitability of different methods for their context, "
            "and to build confidence in their own decision-making."
        ),
        "completion_criteria": (
            "The student has reflected on feasibility and/or alignment for at "
            "least one method and shown signs of forming a reasoned view."
        ),
    },
    6: {
        "number": 6,
        "name": "Summary of discussion and future actions",
        "trigger": "Summary of discussion and future actions",
        "action": (
            "Ask the student to summarise which research method appears most "
            "suitable for their research and why, based on the reflections from "
            "Stage 5. Encourage them to discuss this reasoning with their "
            "supervisor."
        ),
        "purpose": (
            "To support the student in synthesising their reflections and to "
            "prepare them for a more informed, scaffolded discussion with their "
            "supervisor."
        ),
        "completion_criteria": (
            "The student has articulated, in their own words, which method they "
            "lean toward and at least one reason why."
        ),
        "is_final": True,
    },
}

# Feasibility-constraint reflection prompts for Stage 5 (from Scenario A).
STAGE5_CONSTRAINTS: List[Dict] = [
    {"key": "timeline",
     "question": "Considering the timeline of your research project, would you "
                 "have sufficient time to do this method?"},
    {"key": "participant_access",
     "question": "Would you be able to access participants within the timeline "
                 "of your research project?"},
    {"key": "analysis_skills",
     "question": "Would you be able to analyse this data with your current "
                 "knowledge, or would you need training on the analysis techniques?"},
    {"key": "ethics",
     "question": "Would you need ethical approval to do this type of research method?"},
    {"key": "data_volume",
     "question": "Would this method produce a volume of data you could realistically "
                 "analyse within your project's timeline?"},
    {"key": "rq_alignment",
     "question": "Does this method align with the purpose of your research question "
                 "and the kind of understanding you are seeking?"},
]

# Global behavioural constraints from Scenario A "Other functional specifications".
GLOBAL_CONSTRAINTS = (
    "BEHAVIOURAL RULES (apply at every stage):\n"
    "- Use reassuring language that builds confidence. Normalise the uncertainty "
    "of choosing a research method.\n"
    "- Use modal language (could, should, may). Frame suggestions as considerations, "
    "not directives.\n"
    "- Never select a research method on the student's behalf.\n"
    "- Never present one method as superior to another UNLESS the student's own "
    "reflection on feasibility constraints supports it.\n"
    "- Do not overemphasise the complexity of methods. Keep language simple.\n"
    "- Encourage autonomy and reflection; validate the student's reflective thinking.\n"
    "- If a question falls outside what you should answer (e.g. asking you to choose "
    "for them), respond that their supervisor may be able to support them with this."
)

FIRST_STAGE = 1
FINAL_STAGE = 6


def get_stage(n: int) -> Optional[Dict]:
    return STAGES.get(n)


def stage_name(n: int) -> str:
    s = STAGES.get(n)
    return s["name"] if s else f"Unknown stage {n}"


def all_stage_numbers() -> List[int]:
    return sorted(STAGES.keys())
