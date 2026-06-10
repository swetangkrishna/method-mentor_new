---
name: design-learning-experience
description: >
  Use this skill when an educational agent must plan or structure a complete
  learning sequence — not just respond to a single question. Triggers: learner
  asks how to learn a topic, agent is designing a lesson or session plan,
  a topic requires more than one interaction to master, or the agent needs
  to sequence activities across the four modes of the experiential learning
  cycle. Produces a structured plan that moves the learner from experience
  through reflection, conceptualisation, and active experimentation.
  Role: Teacher / Educator.
  Source: Kolb, Kolb, Passarelli & Sharma (2014) — KERP full-cycle design;
          Kolb, D. A. (1984) — Experiential Learning Theory.
---

# Design Learning Experience

## Why this skill exists

Kolb (1984) proposed that learning is not a single event but a cycle: learners
move through concrete experience, reflective observation, abstract
conceptualisation, and active experimentation. Kolb et al. (2014) showed that
effective educators move through all four roles — facilitator, expert,
evaluator, and coach — to support learners through all four modes. Most
instruction covers only one or two modes (typically expert delivery and
evaluation), leaving the experiential and experimental phases to chance.
This skill forces the agent to design across all four modes, producing a
more complete and durable learning experience.

**Research grounding:**
Kolb, D. A. (1984). *Experiential Learning*. Prentice-Hall.
Kolb, A. Y., Kolb, D. A., Passarelli, A., & Sharma, G. (2014). On becoming
an experiential educator. *Simulation & Gaming, 45*(2), 204–234.

---

## When to use this skill

- The learner wants to learn a new topic from scratch or significantly deepen
  an existing understanding.
- The agent is designing a session, lesson, or learning pathway (not just
  answering a single question).
- The topic requires practice, reflection, and application — not just exposure.
- The agent is acting as an educator or teacher, not just a tutor responding
  to a single query.

## When NOT to use this skill

- The learner has a single, bounded question — answer it directly.
- The learner has explicitly asked for a quick explanation, not a learning
  plan.
- Time is severely constrained and only one mode can be covered.

---

## The four-mode learning cycle

| Mode | Name | What happens here | Agent role |
|------|------|-------------------|------------|
| CE | Concrete Experience | Learner encounters the concept in a real or simulated situation | Facilitator — creates the experience |
| RO | Reflective Observation | Learner pauses and reflects on what happened | Facilitator — creates space and questions |
| AC | Abstract Conceptualisation | Learner builds a model or theory from the reflection | Subject expert — provides the framework |
| AE | Active Experimentation | Learner tests the model in a new situation | Coach — sets the challenge and gives feedback |

Effective learning moves through all four modes. Sequences can start at any
mode, but must complete the full cycle.

---

## Procedure

### Step 1 — Identify the learning objective
Use the set-learning-objectives skill if not already done. The objective drives
all four mode activities.

### Step 2 — Design the Concrete Experience (CE)
Create or select an experience that puts the learner in contact with the
phenomenon before explaining it. This is the opposite of lecture-first.

CE activity types:
- A problem to attempt before knowing the solution.
- A case study to read and respond to.
- A demonstration to observe and describe.
- A simulation or scenario to engage with.
- A question about the learner's own prior experience with the topic.

The CE should be achievable with the learner's current knowledge — it is not
a test of the new concept but an encounter with it.

### Step 3 — Design the Reflective Observation (RO) questions
After the CE, ask questions that prompt the learner to examine what happened
and what they noticed, before introducing the conceptual framework.

RO question types:
- "What did you notice?"
- "What surprised you?"
- "What did you expect to happen, and what actually happened?"
- "What patterns do you see?"

Do not explain or correct during RO. The learner is processing, not learning
the concept yet.

### Step 4 — Deliver the Abstract Conceptualisation (AC)
Now introduce the concept, theory, or framework that makes sense of the CE
and RO. This is the expert delivery step — but it comes after experience and
reflection, not before.

AC content should:
- Explicitly connect back to the CE: "What you noticed in Step 1 is explained
  by..."
- Be as minimal as possible — just the framework needed to make sense of the
  experience.
- Include at least one alternative representation (analogy, diagram, or
  worked example).

### Step 5 — Design the Active Experimentation (AE) task
Set a new task that asks the learner to apply the concept in a different
situation. This is not the same as the CE — it is a transfer task.

AE task requirements:
- Different surface context from the CE (tests generalisation, not recall).
- Requires the learner to use the concept, not just identify it.
- Has a clear success criterion that the learner can self-assess against.

### Step 6 — Plan the feedback loop
Specify how feedback will be given at the AE stage. Use the
provide-formative-feedback skill. The cycle is only complete when the learner
has received feedback on their experimentation and can connect back to the
learning objective.

---

## Output format

```
Learning objective: [one sentence]

Mode 1 — Concrete Experience:
[Activity or prompt — what the learner does before being taught]

Mode 2 — Reflective Observation:
[2–3 questions the agent will ask after the CE]

Mode 3 — Abstract Conceptualisation:
[The concept, framework, or model — minimal, connected to the CE]

Mode 4 — Active Experimentation:
[Transfer task — different context, same concept]

Feedback plan:
[How feedback will be given on the AE output]
```

---

## Success criteria

- All four modes are present in the design.
- The CE precedes the AC — learners experience before being taught.
- The AE uses a different context from the CE (transfer, not repeat).
- The learning objective can be assessed through the AE output.

## Failure modes to avoid

- **AC-only design:** deliver the concept, give an example, done. Covers one
  mode. Common in lecture-style agents.
- **CE without AC:** give the learner an experience but never explain the
  underlying concept. Produces engagement without learning.
- **AE = repeat of CE:** the learner does the same task type again with
  different numbers. Tests recall, not transfer.
- **Skipping RO:** moving directly from CE to AC. Reflection is where
  the learner makes sense of the experience — without it, the AC is
  received without the context to make it meaningful.

---

## Example

**Topic:** Learner wants to understand recursion in Python.

**Learning objective:** By the end, you will be able to write a recursive
function that solves a problem with a clear base case and recursive case.

**CE:**
> "Before I explain recursion — try to write a function that calculates the
> factorial of n (e.g. 5! = 120) using only what you know now.
> No loops either — pretend they don't exist. Write whatever you can."

**RO:**
> "What made this hard without loops? What were you trying to do that kept
> not working? What would you have needed to make it work?"

**AC:**
> "What you were trying to do is call the function from inside itself.
> That's recursion. Here's the key insight from your struggle: [explain base
> case and recursive case, connected to what the learner tried to write]."

**AE:**
> "Now apply this to a different problem: write a recursive function that
> sums all integers from 1 to n. Different problem, same structure. You
> know what you need — a base case and a recursive case."

**Feedback:** Apply provide-formative-feedback skill on the AE submission.
