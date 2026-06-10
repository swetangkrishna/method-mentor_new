---
name: align-outcomes-activities-assessment
description: >
  Use this skill when an educational agent is designing, reviewing, or
  critiquing a lesson plan, unit plan, or any instructional sequence.
  Triggers: learner submits a lesson plan for review, agent is generating a
  lesson plan, agent detects that what is being taught, how it is being
  taught, and how it is being assessed are not consistent with each other.
  Ensures that the learning objective, the instructional activity, and the
  assessment all target the same cognitive level and content.
  Role: Educator / Teacher.
  Source: Biggs & Tang (2011) — Constructive Alignment;
          Bloom (1956, revised Anderson & Krathwohl 2001) — Taxonomy.
---

# Align Outcomes, Activities, and Assessment

## Why this skill exists

Biggs & Tang (2011) identified constructive alignment as the central design
principle of effective instruction: the learning outcomes, the teaching
activities, and the assessment tasks must all be aligned — targeting the same
verb (cognitive operation) and the same content. When they are misaligned —
when a teacher asks students to "evaluate" in the outcome but only "recall" in
the assessment, or teaches through lecture but assesses through application —
learning is undermined regardless of how well each component is individually
designed.

For an educational agent, this skill is the quality-assurance check on any
lesson plan it reviews or produces. It catches the most common structural
flaw in instructional design: components that each make sense locally but
do not cohere as a system.

**Research grounding:**
Biggs, J., & Tang, C. (2011). *Teaching for Quality Learning at University*
(4th ed.). Open University Press / McGraw-Hill.
Bloom, B. S. (Ed.). (1956). *Taxonomy of educational objectives*. Longmans.
Anderson, L. W., & Krathwohl, D. R. (Eds.). (2001). *A taxonomy for learning,
teaching, and assessing*. Longman.

---

## When to use this skill

- Reviewing or generating a lesson plan, unit plan, or course design.
- Any time a learning objective, activity, and assessment appear together
  in the same design.
- When a learner reports that students are performing poorly despite "good
  teaching" — misalignment is a frequent hidden cause.
- When a learner asks "Is this a good lesson plan?" — alignment is the
  first check.

## When NOT to use this skill

- Single-question tutoring interactions with no instructional design component.
- The objective and assessment have already been verified as aligned — move
  to other quality dimensions.

---

## Alignment check procedure

### Step 1 — Extract the three components

From the lesson plan or instructional design, identify:

1. **Learning outcome (LO):** What verb does it use? What content does it
   target?
2. **Learning activity (LA):** What cognitive operation does this activity
   require the learner to perform?
3. **Assessment task (AT):** What cognitive operation does this assessment
   require the learner to perform?

If any of the three is absent or vague, flag it before checking alignment.

### Step 2 — Map to cognitive level

Map each component's verb to a level of Bloom's revised taxonomy:

| Level | Verbs |
|-------|-------|
| 1 — Remember | recall, list, name, identify, recognise |
| 2 — Understand | explain, describe, summarise, classify, paraphrase |
| 3 — Apply | use, solve, demonstrate, implement, calculate |
| 4 — Analyse | compare, differentiate, examine, break down, infer |
| 5 — Evaluate | judge, critique, justify, assess, argue |
| 6 — Create | design, construct, plan, produce, generate |

### Step 3 — Check alignment

For alignment, the three components must target the same level (or the
activity and assessment must target ≥ the level named in the objective).

**Aligned example:**
- LO: "Students will be able to *evaluate* the strengths and limitations
  of two teaching strategies." (Level 5)
- LA: Students read two case studies and argue for one approach in writing.
  (Level 5)
- AT: Students write a justified critique of an unfamiliar teaching scenario.
  (Level 5) ✓

**Misaligned example:**
- LO: "Students will *evaluate* classroom management strategies." (Level 5)
- LA: Teacher lectures on three strategies. (Level 1–2 for student)
- AT: Multiple-choice quiz on strategy names. (Level 1) ✗
  → Activity and assessment are two to four levels below the objective.

### Step 4 — Identify the misalignment type

| Type | Description |
|------|-------------|
| **Ceiling misalignment** | Objective sets a high level; activity/assessment aim lower |
| **Floor misalignment** | Activity/assessment aim higher than objective warrants |
| **Content misalignment** | Same cognitive level but different content |
| **Missing component** | One of the three is absent or too vague to assess |

### Step 5 — Produce the alignment diagnosis

State clearly which components are misaligned and at which levels. Do not
just say "this is misaligned" — specify the levels for each component and
where the gap is.

### Step 6 — Suggest specific revisions

For each misalignment, offer a concrete revision option. Give at least two
options (it is usually possible to fix misalignment by raising the activity/
assessment OR by lowering the objective — the choice depends on the educational
context and purpose):

- **Option A:** Raise the activity/assessment to match the objective.
- **Option B:** Revise the objective to match what the activity/assessment
  actually requires.

---

## Output format

```
Alignment check:

Learning outcome: "[text]" → Bloom level: [N] ([level name])
Learning activity: "[description]" → Bloom level: [N] ([level name])
Assessment task: "[description]" → Bloom level: [N] ([level name])

Alignment status: [ALIGNED / MISALIGNED — specify type]

[If misaligned:]
Gap identified: [specific description of the mismatch]

Revision options:
Option A: [specific change to activity/assessment to raise to LO level]
Option B: [specific revision to the LO to match current activity/assessment]
```

---

## Success criteria

- All three components have been mapped to a Bloom level.
- The diagnosis names the specific type and direction of misalignment.
- At least two concrete revision options are offered.
- The diagnosis distinguishes between cognitive level misalignment and content
  misalignment — they require different fixes.

## Failure modes to avoid

- **Approving alignment superficially:** "It looks fine" — without actually
  mapping the verbs to Bloom levels.
- **Only checking the objective:** the most common oversight is ensuring
  the objective is well-written while ignoring whether the activity and
  assessment match it.
- **Prescribing only one fix:** the agent should not insist the objective
  must be right and the assessment must change. Alignment can be achieved
  in multiple directions.
- **Treating "understand" as acceptable:** "Students will understand X" is
  not alignable because "understand" is not testable. Flag it as vague and
  ask for a specific verb.

---

## Example

**Scenario:** Learner submits a lesson plan with:
- LO: "Students will understand the water cycle."
- LA: Teacher draws a diagram on the board and explains each stage.
- AT: Students label a blank diagram at the end.

**Alignment check:**

> Learning outcome: "understand the water cycle" → vague ("understand"
> is not a Bloom verb — cannot be aligned until specified)
>
> Learning activity: Teacher-led diagram explanation → Student cognitive
> operation: Remember / Understand (Level 1–2) — students receive, not
> produce
>
> Assessment task: Label a diagram → Bloom level: 1 — Remember (recall
> of stage names)
>
> **Alignment status: MISALIGNED — two issues**
>
> Issue 1: "Understand" is not a testable verb. What should the student
> actually be able to do? If the intent is Level 2, the verb should be
> "explain"; if the intent is Level 3, it should be "apply" or "predict".
>
> Issue 2: Even accepting Level 2 (Understand), the activity (teacher
> explains) does not require the student to perform at Level 2 — listening
> is Level 1 for the learner. The assessment (labelling) only requires
> Level 1 recall.
>
> **Revision options:**
>
> Option A (raise activity and assessment to Level 2):
> - Revise LO to: "Students will be able to explain the water cycle and
>   describe how water moves between stages."
> - Revise LA to: Students construct a diagram themselves from a description,
>   then explain it to a partner.
> - Revise AT to: Students write a paragraph explaining what happens at one
>   stage of their choice, and why it leads to the next stage.
>
> Option B (lower objective to match current activity and assessment):
> - Revise LO to: "Students will be able to identify and name the four
>   stages of the water cycle."
> - Keep the activity and assessment as is.
> - Note: this is appropriate only if identification/recall is genuinely the
>   intended outcome for this lesson (e.g. it is a foundation lesson before
>   a deeper follow-up).
