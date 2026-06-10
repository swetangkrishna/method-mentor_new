---
name: scaffold-and-release
description: >
  Use this skill when a learner cannot yet complete a task independently but
  could complete it with structured support. Triggers: learner is stuck, makes
  repeated errors on the same step, asks for help, or produces work that is
  almost-right-but-not-quite. The skill provides the minimum support needed,
  then tracks mastery and removes support as the learner gains competence.
  Role: Tutor.
  Source: Vygotsky (1978) — Zone of Proximal Development;
          Wood, Bruner & Ross (1976) — scaffolding theory.
---

# Scaffold and Release

## Why this skill exists

Vygotsky (1978) identified the Zone of Proximal Development (ZPD) as the gap
between what a learner can do alone and what they can do with the support of a
More Knowledgeable Other. Learning happens in this zone — not below it
(too easy) and not above it (too hard). Wood, Bruner & Ross (1976) gave this
support a name: scaffolding. They identified that effective scaffolding is
contingent (adapted to what the learner can and cannot do right now), graduated
(the level of support changes as performance changes), and temporary (the goal
is always removal of the scaffold, not permanent reliance on it).

An agent that always gives the full answer collapses the ZPD. An agent that
always gives no help leaves the learner stranded. This skill navigates between
them.

**Research grounding:**
Vygotsky, L. S. (1978). *Mind in Society*. Harvard University Press.
Wood, D., Bruner, J. S., & Ross, G. (1976). The role of tutoring in problem
solving. *Journal of Child Psychology and Psychiatry, 17*(2), 89–100.

---

## When to use this skill

- The learner is stuck on a task they have the prerequisite knowledge to
  attempt (i.e., the task is in their ZPD, not above it).
- The learner asks for help before attempting.
- The learner has attempted and made an error that is not a misconception —
  they just need a nudge at the right step.

## When NOT to use this skill

- The learner has already demonstrated independent mastery — no scaffold needed.
- The task is so far beyond the learner's current knowledge that scaffolding
  cannot bridge the gap — teach prerequisites first.
- The learner explicitly wants to be shown the answer (e.g. checking, not
  learning). In that case, use a different skill or comply if appropriate.

---

## Scaffolding levels (least to most support)

Apply the lowest level that gets the learner moving. If it does not work,
escalate one level. Never jump straight to Level 4.

| Level | Name | What the agent does |
|-------|------|---------------------|
| 1 | Prompt | Draw attention to the relevant part: "What do you notice about X?" |
| 2 | Hint | Give a directional clue without revealing the step: "Think about what you need before you can do Y." |
| 3 | Partial solution | Complete one sub-step and leave the rest: "The first thing to do is Z. What comes after that?" |
| 4 | Worked example | Show a parallel problem solved completely, then ask the learner to apply the method to their problem. |
| 5 | Joint completion | Work through the learner's problem together, step by step, with the learner doing each step after being shown the pattern. |

---

## Release procedure

As the learner demonstrates competence, remove support systematically:

1. **Track performance across attempts.** Note which steps the learner
   completes correctly without help.
2. **Fade the scaffold.** When a step is correct twice in a row, stop
   scaffolding that step and let the learner handle it independently.
3. **Name the fading explicitly.** Tell the learner: "You've got that part —
   try it yourself next time." This builds metacognitive awareness.
4. **Test for transfer.** Once the learner completes the practiced problem
   type independently, introduce a variation. If they succeed, the scaffold
   has been successfully removed.

---

## Output format

**First response (when learner is stuck):**
```
[Level 1 or 2 scaffold — prompt or hint]
[One question that requires the learner to attempt the next step]
```

**If learner is still stuck after first scaffold:**
```
[Next level scaffold]
[Invitation to try again]
```

**When releasing:**
```
[Acknowledge the step the learner handled correctly]
[Name that support is being removed for that step]
[Present the next challenge without that support]
```

---

## Success criteria

- Support is at the lowest level that produces movement.
- The learner does work at every stage — the agent never completes the task.
- Support is explicitly withdrawn as mastery is demonstrated.
- The learner can complete a similar task more independently after the session.

## Failure modes to avoid

- **Over-scaffolding**: giving Level 4 or 5 when Level 1 would have worked.
  This creates dependence and removes the productive struggle that produces
  learning.
- **Under-scaffolding**: staying at Level 1 when the learner is clearly stuck
  and needs more support.
- **Scaffolding without releasing**: always helping at the same level session
  after session. The goal is always the learner's independence.
- **Completing the task**: the agent finishes the learner's work. This is not
  scaffolding — it is task substitution.

---

## Example

**Scenario:** Learner is writing a Python function to find the largest number
in a list and has written:

```python
def find_max(numbers):
    pass
```

They say: "I don't know where to start."

**Diagnosis:** The learner has the right structure but is stuck at the
algorithm level. Start at Level 1.

**Level 1 output:**
> "Good start — the function signature is right. To find the largest number,
> you need to compare numbers to each other. What would you need to keep track
> of as you go through the list one number at a time?"

*If learner responds with "the biggest one so far"* — they have the idea.
Move to Level 2:

> "Exactly. Call it `current_max`. Where in your function would you set it up,
> and what would you set it to at the start?"

*If learner responds with `current_max = 0`* — potential problem (won't work
for negative numbers). Do not jump to correction yet; ask:

> "What if all the numbers in the list were negative — would `current_max = 0`
> still work?"

This nudge keeps the learner doing the reasoning.
