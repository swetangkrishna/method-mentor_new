---
name: reflect-on-pedagogy
description: >
  Use this skill after any instructional interaction — tutoring session,
  lesson delivery, or feedback exchange — to evaluate whether the pedagogical
  decisions made were effective and identify specific improvements for the
  next interaction. Triggers: end of a session, learner showed signs of
  persistent confusion despite instruction, an explanation did not land, or
  an assessment revealed unexpected gaps. The agent reviews its own teaching
  decisions and produces a structured reflection.
  Role: Educator.
  Source: Shulman (1987) — pedagogical reasoning cycle: reflection and
          new comprehension steps; Hattie (2009) — teachers as evaluators
          of their own teaching.
---

# Reflect on Pedagogy

## Why this skill exists

Shulman (1987) described pedagogical reasoning as a cycle that does not end
with instruction. After delivering, evaluating, and receiving learner responses,
the teacher must reflect — examining whether the instructional decisions made
were sound, and whether the learner's subsequent performance demonstrates that
the teaching worked. This reflection feeds "new comprehension": a revised
understanding of both the content and how to teach it. Without this step,
teaching becomes static. Hattie (2009) extended this by arguing that teachers
who see themselves as evaluators of their own impact — asking "did my teaching
change this learner's performance?" — are significantly more effective than
those who attribute outcomes to learner ability or motivation.

For an agent, this skill drives self-improvement in M1 (human-authored skills)
and is especially relevant to M2 (RL-inspired improvement) — the reflection
output is the basis for reward signals or skill refinement.

**Research grounding:**
Shulman, L. S. (1987). Knowledge and teaching: Foundations of the new reform.
*Harvard Educational Review, 57*(1), 1–22.
Hattie, J. (2009). *Visible Learning*. Routledge.

---

## When to use this skill

- After a complete tutoring or teaching session.
- After an explanation or scaffold attempt where the learner's response
  revealed whether it worked.
- After a formative assessment where results were unexpected.
- When the agent is asked "How could this lesson be improved?"
- As an internal routine between interactions in a longer session.

## When NOT to use this skill

- Mid-explanation — reflection disrupts delivery. Complete the instructional
  move first.
- When the learner is waiting for a response — reflection is a between-moves
  process, not a real-time one.

---

## Reflection framework

Shulman's reflection asks six questions. Work through them in order:

### Question 1 — What was the goal?
What was the learning objective for this interaction? Was it stated explicitly?

### Question 2 — What did I do?
What instructional decisions were made? What representations, strategies, or
feedback were used?

### Question 3 — What happened?
What was the learner's response? What did the learner do, say, or produce after
each instructional decision?

### Question 4 — Did it work?
Compare Question 3 to Question 1. Did the learner's performance move toward
the objective? What is the evidence?

### Question 5 — Why did it work or not work?
Identify the specific decision that produced the outcome — both positive and
negative. Avoid attributing outcomes to the learner ("they didn't try") or to
the content ("it's just hard"). Attribute outcomes to instructional decisions
that can be changed.

### Question 6 — What would I do differently?
Based on Questions 4 and 5, identify one or two specific instructional changes
to make in the next interaction with this learner or on this topic.

---

## Procedure

### Step 1 — Reconstruct the interaction
Briefly summarise the key instructional moves made, in sequence:
- Objective set (or not).
- Explanation or activity type used.
- Feedback given.
- Learner response at each step.

### Step 2 — Identify the decision points
From the reconstruction, identify 2–3 moments where a decision was made that
could have gone differently. These are the reflection targets.

### Step 3 — Apply Questions 4–6 to each decision point
For each decision point, answer: Did it work? Why? What would I change?

### Step 4 — Produce the reflection output
Write a structured reflection that: names what worked and why, names what did
not work and why, and gives specific changes for next time. Be precise —
"explain earlier" is not a change, "use a contrast case before a direct
explanation when the learner has a prior-domain misconception" is.

### Step 5 — Update skill or approach
If the reflection identifies a systematic issue (a representation that
consistently fails, a feedback style that does not produce movement), note
it as a revision to the relevant skill description — not just this interaction.

---

## Output format

```
Pedagogical reflection — [session/topic identifier]

Goal: [what the learning objective was]

What was done:
- [Key instructional move 1]
- [Key instructional move 2]
- [Key instructional move 3]

What worked:
[Specific decision + evidence it worked + why it worked]

What did not work:
[Specific decision + evidence it did not work + why it did not work]

What I would change:
1. [Specific change — precise enough to implement]
2. [Specific change — precise enough to implement]

Skill update note (if applicable):
[If a skill description needs revision based on this reflection]
```

---

## Success criteria

- The reflection attributes outcomes to instructional decisions, not to
  learner ability or content difficulty.
- "What I would change" contains at least one specific, implementable revision.
- The reflection distinguishes between what worked and what did not with
  evidence from the learner's actual responses.

## Failure modes to avoid

- **Attributing failure to the learner:** "They just weren't motivated" —
  this blocks improvement. Every outcome is at least partly a function of
  an instructional decision.
- **Vague improvements:** "Do better next time" — not actionable. The
  improvement must be specific enough to implement.
- **Only reflecting on failures:** reflecting on what worked is equally
  important — it identifies what to preserve and repeat.
- **Skipping reflection entirely:** especially in M1, the skills library
  only improves through reflection on what works and what does not.

---

## Example

**Session:** Tutor agent worked with a learner on list comprehensions in Python.
Learner initially could not write any comprehension. Agent used an analogy
(comprehensions as "for-loops in one line"). Learner understood the basic form
but failed on conditional comprehensions despite two explanations.

**Reflection output:**

> **Goal:** Learner able to write conditional list comprehensions independently.
>
> **What was done:**
> - Used for-loop-to-comprehension analogy to introduce syntax.
> - Gave two direct explanations of the conditional syntax `[x for x in y if z]`.
> - Gave a practice task: filter a list of numbers to keep only even ones.
>
> **What worked:**
> The for-loop analogy worked well for basic comprehensions — the learner
> understood `[x*2 for x in numbers]` after one explanation. The structural
> parallel between the for-loop they already knew and the comprehension syntax
> gave them a handle on the new form.
>
> **What did not work:**
> Two direct explanations of conditional syntax did not produce independent
> performance. The learner could reproduce the pattern when shown it but could
> not generate it from scratch. This suggests the syntax was memorised, not
> understood. The condition position (`if` at the end, not at the start as
> in a regular if-statement) is likely the source of confusion — this is a
> prior-domain interference misconception.
>
> **What I would change:**
> 1. Before explaining conditional comprehension syntax, use a contrast case:
>    show a conditional for-loop and ask the learner where the `if` goes in
>    the comprehension — let them predict the position before revealing it.
>    This activates the misconception before correction.
> 2. Give a worked example where the condition is removed and added back,
>    with explicit commentary on why the position is different from a
>    standard if-statement.
>
> **Skill update note:**
> The identify-misconceptions skill should include "if-condition position in
> comprehensions" as a known prior-domain interference case for Python learners.
