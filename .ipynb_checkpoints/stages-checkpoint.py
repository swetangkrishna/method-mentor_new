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
        "required_parameters": [
            # A research question can be phrased in unlimited ways, so keyword
            # matching is the WRONG tool here: an earlier keyword list failed on
            # answers like "It's about student motivation in maths", causing the
            # agent to re-ask the opening question in a different form (issue 7).
            # Instead this slot is filled by ANY substantive reply — which is
            # exactly what the stage asks for.
            {"id": "research_question",
             "question": "Could you tell me about your research question?",
             "substantive": True,          # any real answer counts
             "detect": []},
            {"id": "tentative_method",
             "question": ("What method are you thinking of using — and if you're "
                          "not sure yet, that's completely fine?"),
             # Either they name a method, OR they say they're undecided; the
             # Scenario A completion criteria explicitly allow both.
             "detect": ["survey", "questionnaire", "interview", "focus group",
                        "observation", "ethnograph", "case study", "experiment",
                        "mixed method", "secondary data", "pisa", "dataset",
                        "not sure", "unsure", "not decided", "haven't decided",
                        "have not decided", "don't know", "do not know",
                        "no idea", "undecided", "open to", "thinking of using",
                        "planning to use", "considering using", "might use",
                        "no method", "not yet"]},
        ],
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
            "qualitative-vs-quantitative comfort is known AND they have explained "
            "WHY they feel more confident with that type of method."
        ),
        "required_parameters": [
            {"id": "programme_level",
             "question": ("What programme are you on — Masters or PhD, full-time or "
                          "part-time — and what year are you in?"),
             "detect": ["phd", "masters", "master's", "msc", "ma ", "doctoral",
                        "full time", "full-time", "part time", "part-time",
                        "first year", "second year", "third year", "year "]},
            {"id": "methods_comfort",
             "question": ("Would you be more comfortable using qualitative methods, "
                          "or are you open to exploring quantitative methods as well?"),
             "detect": ["qualitative", "quantitative", "mixed", "comfortable",
                        "prefer", "numbers", "statistics", "stats"]},
            # ISSUE 002 — the question the agent was skipping. Anchors the student
            # in their own experience before alternatives are introduced.
            {"id": "methods_confidence_reason",
             "question": ("Can you describe why you feel more confident using that "
                          "type of method?"),
             # NOTE: these must signal an EXPLANATION, not merely appear in normal
             # speech. Generic fragments ("in my", "since", "as i") are excluded —
             # they matched things like "in my second year" and filled this slot
             # before the student had explained anything.
             "detect": ["because", "the reason", "i feel confident",
                        "experience with", "experience in", "experience of",
                        "used it before", "used them before", "used this before",
                        "have used", "i've used", "familiar with", "trained in",
                        "training in", "i have done", "i've done", "i did",
                        "background in", "i studied", "was taught",
                        "more confident with", "more confident using",
                        "feel confident because"]},
        ],
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
            "AND the type of data needed is established AND the student has "
            "reflected on what kind of evidence they find convincing."
        ),
        "required_parameters": [
            # Bare "explain"/"explore" matched "could you explain that?" — the
            # detectors are anchored to the aim vocabulary instead.
            {"id": "research_aim",
             "question": ("Thinking about your research question, is your aim more "
                          "exploratory, explanatory, or evaluative?"),
             "detect": ["exploratory", "explanatory", "evaluative",
                        "aim is to explore", "aim is to explain",
                        "aim is to evaluate", "trying to explore",
                        "trying to explain", "trying to evaluate",
                        "want to explore", "want to explain", "want to evaluate",
                        "descriptive"]},
            # ISSUE 003 — reflection on the data/information needed.
            {"id": "required_data_type",
             "question": ("Thinking about your research question, what type of "
                          "information or data do you think you would need to "
                          "answer it?"),
             "detect": ["data", "information", "numbers", "numerical", "statistics",
                        "scores", "text", "transcripts", "narratives", "responses",
                        "accounts", "views", "opinions", "measurements",
                        "perceptions", "experiences"]},
            # ISSUE 004 — reflection on epistemological orientation.
            {"id": "evidence_orientation",
             "question": ("Thinking about your research topic, what type of evidence "
                          "would you find most convincing: measurable or observable "
                          "data (a positivist perspective), people's experiences and "
                          "meanings (an interpretivist perspective), or whatever best "
                          "helps answer the research question (a pragmatic "
                          "perspective)?"),
             "detect": ["positivist", "positivism", "interpretivist", "interpretivism",
                        "pragmatic", "pragmatism", "measurable", "observable",
                        "meanings", "lived experience", "convincing", "objective",
                        "subjective"]},
        ],
    },
    4: {
        "number": 4,
        "name": "Present alternative research methods",
        "trigger": "Present alternative research methods",
        "action": (
            "Work through THREE plausible alternative research methods ONE AT A "
            "TIME, in a present-then-reflect cycle. For each method: (a) PRESENT "
            "it with a brief description, its common application, and a practical "
            "example from a DIFFERENT research context (never the student's own); "
            "then (b) REFLECT — ask the student feasibility questions about THAT "
            "method (timeline, participant access, analysis skills, ethics, data "
            "volume, research-question alignment) before introducing the next "
            "method. At least one method MUST be the opposite of the student's "
            "stated comfort zone from Stage 2. NEVER present a method the student "
            "already proposed as their own."
        ),
        "purpose": (
            "To broaden the student's awareness of alternative research methods "
            "and to have them reflect on the feasibility of each one immediately "
            "after it is introduced, while it is fresh, before Stage 5 compares "
            "them against one another."
        ),
        "completion_criteria": (
            "Three alternative methods have been presented, at least one from "
            "outside the student's comfort zone, AND the student has reflected on "
            "the feasibility of each method as it was introduced."
        ),
        "gated": True,  # cannot begin until stages 1-3 are complete
    },
    5: {
        "number": 5,
        "name": "Scaffold reflective comparison of the methods",
        "trigger": "Scaffolding reflective comparison of research methods",
        "action": (
            "The student has now seen each alternative and reflected on its "
            "feasibility in Stage 4. Guide them to COMPARE the methods against one "
            "another and against their own original method — weighing the "
            "trade-offs they themselves raised (timeline, access, skills, ethics, "
            "data volume, alignment with the research question, depth vs breadth, "
            "generalisability). Ask ONE comparative question at a time. Never rank "
            "the methods yourself; help the student weigh them."
        ),
        "purpose": (
            "To support the student in comparing the methodological options for "
            "their context and to build confidence in their own decision-making."
        ),
        "completion_criteria": (
            "The student has compared at least two methods against each other and "
            "shown signs of forming a reasoned, self-justified view."
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


def required_parameters(n: int) -> List[Dict]:
    """
    The information slots a stage MUST collect before it can complete. Each entry:
        {"id": str, "question": str, "detect": [keyword, ...]}
    Stages with no required parameters return an empty list.
    """
    s = STAGES.get(n)
    return list(s.get("required_parameters", [])) if s else []