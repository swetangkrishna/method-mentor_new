---
name: diagnose-zpd
description: >
  Use this skill at the start of a tutoring or teaching interaction, or when
  the agent is unsure whether a task is at the right level for the learner.
  Triggers: new learner, new topic, learner seems frustrated (task too hard)
  or bored (task too easy), learner's responses give no signal about their
  level. The skill establishes what the learner can do independently versus
  with support — the Zone of Proximal Development boundary — so all subsequent
  instruction can be pitched correctly.
  Role: Tutor.
  Source: Vygotsky (1978) — Zone of Proximal Development.
---

# Diagnose ZPD

## Why this skill exists

Vygotsky (1978) argued that a static measure of what a learner can do alone is
an incomplete picture of their learning potential. The ZPD — the gap between
independent performance and assisted performance — is where learning happens.
A teacher or tutor who only knows what the learner can already do has no basis
for instruction. This skill probes both edges of the ZPD:

- **Lower bound**: what the learner can do independently right now.
- **Upper bound**: what the learner can do with support right now.

Instruction pitched below the lower bound wastes time. Instruction pitched
above the upper bound causes frustration with no learning. Instruction pitched
inside the ZPD — between the two bounds — is the target.

**Research grounding:**
Vygotsky, L. S. (1978). *Mind in Society*. Harvard University Press.

---

## When to use this skill

- A new learner or a learner tackling a new topic for the first time.
- The agent has received contradictory signals about the learner's level
  (e.g. confidently correct on some aspects, completely lost on others).
- After a break or significant time gap where level may have changed.
- Before designing any practice task, to ensure appropriate difficulty.

## When NOT to use this skill

- The learner's level is already established from a current-session performance.
- There is a single, well-defined task and the learner has asked for help
  with it — diagnose during the task rather than before.

---

## Diagnosis procedure

### Step 1 — Establish the domain and sub-skills
Break the topic into 3–5 sub-skills or component concepts. These become the
probe points.

### Step 2 — Independent performance probe
Ask the learner to attempt a task or explain a concept without any support.
Choose difficulty at roughly "expected for their stated level". Observe:
- What do they do correctly and fluently?
- Where do they hesitate or stop?
- What errors appear?

Do not help during this step. Do not correct. Just observe.

### Step 3 — Supported performance probe
Now introduce graduated support (see scaffold-and-release skill) on the point
where the learner stopped or erred. Observe:
- How much support is needed before performance improves?
- Does a small hint produce movement (ZPD — reachable with support)?
- Does even a lot of support produce no movement (above ZPD — prerequisites
  missing)?

### Step 4 — Map the ZPD
Based on Steps 2 and 3, identify:
- **Can do alone**: sub-skills/concepts the learner handles without support.
- **Can do with support**: sub-skills in the ZPD — the instructional target.
- **Cannot yet do even with support**: sub-skills above the ZPD — prerequisite
  gaps to address first.

### Step 5 — Calibrate instruction
Use the ZPD map to set the level of every subsequent task and explanation in
this session. Pitch new content at the "can do with support" level. Do not
reteach what the learner can already do alone.

---

## Output format

**Step 2 prompt to learner:**
```
[Independent task at expected level — no help offered]
```

**Step 3 probe (if learner struggles):**
```
[Minimal hint]
[Invitation to try again]
```

**Internal ZPD map (reasoning, not shown to learner):**
```
Can do alone: [list]
ZPD — instructional target: [list]
Above ZPD — prerequisites needed: [list]
```

**Session calibration note to self:**
```
Pitch instruction at: [specific sub-skill level]
Do not re-explain: [already-mastered sub-skills]
Do not yet address: [sub-skills above ZPD]
```

---

## Success criteria

- The agent has identified at least one sub-skill the learner can do
  independently and at least one that is in the ZPD.
- Subsequent instruction is pitched at the ZPD — not at already-mastered
  or above-ZPD content.
- The learner was not told their level explicitly (unless they asked) — the
  diagnosis informs agent behaviour, not learner labelling.

## Failure modes to avoid

- **Pitching at average level without probing.** "You're learning Python so
  I'll assume you know variables" — this is not a ZPD diagnosis.
- **Over-probing.** Spending the whole session diagnosing rather than
  teaching. Two or three targeted probes are enough.
- **Telling the learner their level.** "You're at beginner level" can demotivate
  and is often inaccurate across sub-skills.
- **Using a single probe.** One question cannot map a ZPD. Probe at least
  two sub-skills, with and without support.

---

## Example

**Scenario:** New learner says they want help with Python list comprehensions.

**Step 1 — Sub-skills:**
1. Understanding Python lists
2. Understanding for-loops
3. Understanding conditionals in for-loops
4. Writing basic list comprehensions
5. Writing conditional list comprehensions

**Step 2 — Independent probe:**
> "Before we start — can you write me a for-loop that takes the list
> `[1, 2, 3, 4, 5]` and creates a new list with each number doubled?"

Learner writes:
```python
doubled = []
for n in [1, 2, 3, 4, 5]:
    doubled.append(n * 2)
```
Correct and fluent → for-loops: can do alone.

**Step 2 — Next probe:**
> "Now try writing that same thing as a list comprehension — one line."

Learner writes: `doubled = [n for n in [1,2,3,4,5]]` — missing the `* 2`.

**Step 3 — Supported probe:**
> "Almost — you've got the structure right. Where would the transformation
> `n * 2` go inside the comprehension?"

Learner corrects it → list comprehension syntax: in ZPD (reachable with a hint).

**Step 4 — ZPD map:**
- Can do alone: for-loops, basic list operations.
- ZPD: list comprehension syntax, conditional comprehensions.
- Above ZPD: nested comprehensions (not yet checked, defer).

**Step 5 — Calibrate:** Teach conditional comprehensions next, with light
scaffolding. Do not reteach for-loops.
