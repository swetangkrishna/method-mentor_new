---
name: identify-misconceptions
description: >
  Use this skill when a learner gives an answer, explanation, or question that
  reveals an incorrect mental model — not just a missing fact, but a wrong
  underlying belief that will keep generating errors. Triggers: learner answer
  is wrong in a patterned way, learner's reasoning is visible and flawed,
  learner asks a question that only makes sense if they hold a false belief.
  Role: Tutor / Teacher.
  Source: Shulman (1986, 1987) — PCK; common-misconceptions strand.
---

# Identify Misconceptions

## Why this skill exists

A missing fact can be corrected by supplying the fact. A misconception cannot.
Misconceptions are coherent-but-wrong mental models that actively resist
correction because they fit the learner's prior experience and feel true.
Shulman (1987) placed the ability to anticipate and diagnose misconceptions at
the centre of PCK — it is what distinguishes a subject-expert from an expert
teacher. An agent that simply marks an answer wrong and gives the right answer
will not dislodge a misconception. This skill identifies the misconception
precisely so that the correction can target the root, not the symptom.

**Research grounding:** Shulman, L. S. (1987). Knowledge and teaching:
Foundations of the new reform. *Harvard Educational Review, 57*(1), 1–22.

---

## When to use this skill

- The learner gives a wrong answer that follows a consistent internal logic.
- The learner asks a question that presupposes something false.
- The learner has made the same type of error more than once.
- The learner explains their reasoning and the reasoning reveals a false belief.

## When NOT to use this skill

- The error is a random slip or calculation mistake, not a conceptual one.
- The learner has given no reasoning — there is not enough signal to diagnose.

---

## Diagnosis procedure

### Step 1 — Identify the error surface
What did the learner say or do that was wrong? State it precisely.

### Step 2 — Hypothesise the underlying belief
Ask: "What would someone have to believe in order to produce this error?"
Generate one or two candidate misconceptions. Common categories:
- **Overgeneralisation**: a rule that works in one context applied too broadly.
- **Prior-domain interference**: a concept from everyday life or a previous
  subject imported incorrectly (e.g. maths conventions into programming).
- **Partial understanding**: knows part of the concept, fills the gap with
  intuition.
- **Surface-feature matching**: responds to how something looks rather than
  what it means.

### Step 3 — Test the hypothesis
Ask a diagnostic question designed to confirm or refute your candidate
misconception. The question should be answerable correctly only if the
misconception is absent. Do not reveal the answer yet.

### Step 4 — Confirm the misconception
Based on the learner's response to Step 3, confirm which misconception is
present. Name it clearly in your own reasoning (not necessarily to the learner
in those terms).

### Step 5 — Target the root
Now address the misconception at its source — not the surface error.
Explain why the false belief generates the error pattern, not just what the
right answer is.

### Step 6 — Reconstruct the correct model
Help the learner build the correct mental model from scratch. Use contrast:
show the misconceived model alongside the correct one so the learner can see
the difference explicitly.

---

## Output format

```
[Diagnostic question to test the hypothesised misconception]

[After learner responds — targeted correction that names the root false belief,
not just the wrong answer, followed by the correct model]
```

---

## Success criteria

- The diagnostic question would give different answers depending on whether
  the misconception is present.
- The correction addresses the false belief, not just the wrong answer.
- The learner is shown the correct model alongside the incorrect one so they
  can see the contrast.

## Failure modes to avoid

- Correcting the surface error without touching the underlying belief.
- Giving the right answer without explaining why the misconception produces
  wrong answers — the learner will repeat the error on the next problem.
- Telling the learner they are "wrong" without naming what the error is.
- Using a diagnostic question whose answer reveals nothing about the belief
  (e.g. "Can you try again?").

---

## Example

**Scenario:** Learner says that `0.1 + 0.2 = 0.3` should be True in Python,
and is confused why it is not.

**Step 1 — Error surface:** Learner expects floating-point arithmetic to behave
like pencil-and-paper decimal arithmetic.

**Step 2 — Hypothesis:** Overgeneralisation from everyday decimal notation.
The learner believes computers store decimal numbers exactly.

**Step 3 — Diagnostic question:**
> "Before I explain — what do you think the computer stores when you type `0.1`?
> Does it store exactly one tenth, or something else?"

**Step 4 — Confirm:** If the learner says "exactly 0.1", the misconception is
confirmed — they believe floating-point is exact decimal storage.

**Step 5 & 6 — Root correction:**
> "Here's the actual source of the surprise: computers store numbers in binary,
> not decimal. Just like 1/3 has no exact decimal (0.333...), the fraction 1/10
> has no exact binary representation. So `0.1` in Python is stored as
> 0.1000000000000000055511151231... — close, but not exact. When you add two
> of these close-but-not-exact numbers, the tiny errors accumulate, and you get
> 0.30000000000000004 instead of 0.3. The rule 'computers do maths like
> calculators' only holds for integers. Floating-point is different."
