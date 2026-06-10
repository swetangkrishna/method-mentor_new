---
name: transform-content
description: >
  Use this skill when an educational agent must explain a concept to a learner
  whose background, level, or misconceptions differ from a standard presentation
  of the topic. Triggers: learner says "I don't understand", gives a wrong answer,
  asks for a simpler explanation, or the agent detects a mismatch between the
  concept's canonical form and what the learner can currently access.
  Role: Tutor / Teacher.
  Source: Shulman (1986, 1987) — Pedagogical Content Knowledge (PCK).
---

# Transform Content

## Why this skill exists

Knowing a subject is not the same as knowing how to teach it. Shulman (1987)
identified that expert teachers perform a transformation step between their own
understanding and what they present to a learner. This transformation is the
core of Pedagogical Content Knowledge (PCK). An agent that outputs its own best
explanation of a topic may produce something accurate but inaccessible. This
skill forces the agent to re-encode content specifically for the learner in
front of it.

**Research grounding:** Shulman, L. S. (1987). Knowledge and teaching:
Foundations of the new reform. *Harvard Educational Review, 57*(1), 1–22.
Shulman, L. S. (1986). Those who understand: Knowledge growth in teaching.
*Educational Researcher, 15*(2), 4–14.

---

## When to use this skill

- The learner has given a response that reveals a specific gap or confusion.
- The learner's prior knowledge is clearly different from what the canonical
  explanation assumes.
- A previous explanation attempt did not produce understanding.
- The concept has known common misconceptions that must be anticipated.

## When NOT to use this skill

- The learner has already demonstrated understanding — do not re-explain.
- The concept is procedural and needs demonstration, not re-encoding.

---

## Transformation procedure

Shulman's pedagogical reasoning cycle has six steps. Apply them in order:

### Step 1 — Comprehend
State to yourself (in reasoning, not output) the concept in its full, accurate
form. Do not simplify it yet. What is the structure of the knowledge? What are
the key relationships?

### Step 2 — Represent
Choose one or more representations: analogy, worked example, diagram
description, story, contrast case, or concrete object. The representation must
map correctly onto the concept's structure — not just feel familiar.

**Representation selection rules:**
- Analogy: use when the concept has a structural parallel in everyday life.
- Worked example: use when the concept is a procedure or method.
- Contrast case: use when the learner is confusing two similar things.
- Story or narrative: use when the concept involves causation or sequence.

### Step 3 — Select instructional approach
Choose one of:
- **Direct explanation**: state the concept, then the representation.
- **Guided discovery**: give the representation first, ask the learner to
  draw the concept from it.
- **Error-and-correction**: name the common misconception, explain why it is
  wrong, then give the correct version.

### Step 4 — Adapt to this learner
Adjust vocabulary, cognitive demand, and assumed prior knowledge to what you
have already observed about this learner in this conversation. Do not use a
generic difficulty level.

### Step 5 — Deliver the transformed explanation
Output the explanation. Keep it to the minimum that bridges the gap. Do not
add extra content the learner did not ask for.

### Step 6 — Check comprehension
After delivering, ask one targeted question to verify the transformation worked.
Do not ask "Does that make sense?" — ask a question that requires the learner
to demonstrate understanding.

---

## Output format

```
[Transformed explanation — adapted to this learner's level and gap]

[One comprehension-check question]
```

---

## Success criteria

- The explanation uses a representation the learner can access.
- The representation maps correctly onto the concept — no misleading analogies.
- The vocabulary matches the learner's demonstrated level.
- The comprehension-check question would reveal whether the gap is closed.

## Failure modes to avoid

- Using the same explanation that already failed, only longer.
- Choosing an analogy that maps onto the surface of the concept but not its
  structure (e.g. describing electricity as "water in a pipe" then confusing
  voltage and current).
- Asking "Do you understand?" instead of a real comprehension check.
- Over-explaining: solving the whole problem when the learner only needed one
  concept bridged.

---

## Example

**Scenario:** Learner (secondary school) is confused about why `=` in Python
means assignment, not equality.

**Step 1 — Comprehend:** `=` is an assignment operator; it binds a name to a
value in memory. `==` tests equality. These are semantically unrelated in Python
despite visual similarity.

**Step 2 — Represent:** Contrast case — show `x = 5` vs `x == 5` with their
effects. Analogy: `=` is like sticking a label on a box; `==` is like asking
"are these two boxes the same?"

**Step 3 — Approach:** Error-and-correction, because the learner has likely
brought a maths intuition into the wrong context.

**Step 4 — Adapt:** No jargon; use concrete box analogy.

**Step 5 — Output:**
> "In maths, `=` means 'these two things are equal'. Python borrowed the symbol
> but gave it a different job. Think of `x = 5` as sticking a label that says
> 'x' onto a box that holds the number 5. You're not saying they're equal —
> you're just naming the box. If you want to *ask* whether two things are equal,
> Python uses `==`. Try this: what do you think `x = 5` followed by `x = 10`
> does to the label?"

**Step 6 — Comprehension check:** The final question requires the learner to
reason about reassignment, revealing whether the label metaphor landed.
