---
name: assign-stretch-tasks
description: >
  Use this skill when a learner has demonstrated mastery of a current task
  level and is ready to be challenged beyond their current comfort zone, or
  when a learner needs productive difficulty to develop capability rather than
  just confirm existing knowledge. Triggers: learner completes a task
  correctly with little effort, learner asks "what should I work on next?",
  or the agent has diagnosed a ZPD upper bound that can now be targeted.
  Role: Teacher / Mentor.
  Source: Kram (1983) — career mentor function: challenging assignments;
          Vygotsky (1978) — ZPD upper boundary.
---

# Assign Stretch Tasks

## Why this skill exists

Kram (1983) identified challenging assignments as one of the core career
functions of a mentor — tasks that stretch capability by placing the learner
in situations that require performance slightly beyond their current level.
This is not the same as giving an easy task or an impossibly hard one; it is
the deliberate selection of difficulty at the upper edge of the ZPD (Vygotsky,
1978). Tasks that are too easy confirm existing knowledge without developing
new capability. Tasks that are too hard cause disengagement. The stretch task
occupies the productive zone in between — difficult enough to require growth,
achievable enough to be motivating.

**Research grounding:**
Kram, K. E. (1983). Phases of the mentor relationship.
*Academy of Management Journal, 26*(4), 608–625.
Vygotsky, L. S. (1978). *Mind in Society*. Harvard University Press.

---

## When to use this skill

- The learner has completed the current task correctly and with apparent ease.
- The learner has demonstrated consistent mastery of a skill or concept.
- The learner asks what to work on next.
- The learning objective calls for deeper, more complex, or more independent
  application than what has been practiced so far.

## When NOT to use this skill

- The learner is still consolidating a current level — stretch tasks are
  premature if the learner cannot yet perform reliably at the current level.
- The learner is discouraged or anxious — assign a confidence-building task
  first, then escalate. (Use provide-emotional-support first if needed.)
- The task is arbitrary difficulty rather than a genuine developmental step —
  harder for its own sake is not a stretch task.

---

## Stretch task design principles

A stretch task must meet four criteria:

1. **Requires a genuine new capability:** The task cannot be completed by
   applying the same procedure the learner already knows. It requires
   generalisation, synthesis, transfer, or a new decision layer.

2. **Calibrated to the ZPD upper bound:** The task is achievable — with
   effort and possibly some support — by this learner now. It is not the task
   they will be able to do in six months.

3. **Has a clear success criterion:** The learner must be able to recognise
   whether they have completed it successfully without depending on the agent
   to judge.

4. **Connects to a meaningful purpose:** The learner should understand why
   this level of challenge matters — what capability it is building toward.

---

## Difficulty escalation ladder

Use this to calibrate the stretch level. Move up one rung at a time:

| Rung | Type | Description |
|------|------|-------------|
| 1 | **Variation** | Same procedure, different data or surface context |
| 2 | **Extension** | Familiar procedure with an added step or constraint |
| 3 | **Transfer** | Same concept in a genuinely different domain |
| 4 | **Synthesis** | Combine two previously separate skills or concepts |
| 5 | **Open-ended** | Real-world problem with no predetermined method |
| 6 | **Design/Create** | Build something new using multiple skills |

A learner performing reliably at Rung 1 is ready for Rung 2 — not Rung 4.

---

## Procedure

### Step 1 — Confirm current mastery
Verify that the learner has demonstrated reliable performance at the current
level before assigning a stretch task. Do not stretch prematurely.

### Step 2 — Name what the stretch task is developing
Tell the learner what new capability the task is designed to build. This
connects effort to purpose and makes the difficulty feel meaningful rather
than arbitrary.

### Step 3 — Select the task at the right rung
Use the difficulty escalation ladder. Identify the current rung and select
a task one rung above. Be specific about what makes this task harder than
the previous one.

### Step 4 — Set clear success criteria
Tell the learner specifically what success looks like — not just "do this
task", but "you'll know you've done it well when [specific criterion]."

### Step 5 — Offer bounded support
Unlike in scaffolding (where support is given when needed), in stretch tasks
the learner is expected to struggle productively. Offer bounded support:
"I won't step in until you've made a genuine attempt — then I'm here if
you need a nudge."

### Step 6 — Acknowledge the difficulty explicitly
Name that the task is harder than what the learner has been doing. This is
not a warning — it is a signal that the difficulty is intentional and
appropriate, not a mistake.

---

## Output format

```
[Acknowledgement of current mastery — specific]

[What new capability this task is developing]

[The task — clearly described, with success criteria]

[Why this is harder than the previous task — one sentence]

[Offer of bounded support — available but not proactive]
```

---

## Success criteria for this skill

- The task is genuinely one rung above the learner's current level —
  not the same task with different numbers, and not an impossibly hard task.
- The success criteria are stated and the learner can self-assess against them.
- The difficulty is explicitly framed as intentional and appropriate.
- The learner understands what capability the task is building.

## Failure modes to avoid

- **Stretching without consolidation:** assigning a harder task before the
  current level is mastered. Produces failure without learning.
- **Arbitrary difficulty:** making a task harder without a developmental
  rationale. "Try a harder problem" without explaining what skill it develops.
- **Jumping rungs:** moving from Rung 1 to Rung 5 in one step.
- **Removing all challenge with pre-emptive scaffolding:** a stretch task
  with extensive hints is no longer a stretch task.

---

## Example

**Scenario:** Learner has reliably written for-loops and list comprehensions
(Rung 1 performance). Learning Python.

**Step 1 — Confirm mastery:** Three correct, fluent examples. ✓

**Step 2 — Name capability:** Moving from Rung 1 (variation) to Rung 3
(transfer) — using comprehensions with a new data structure (dictionaries).

**Output:**
> "You've nailed list comprehensions across several examples — that's solid.
> The next step is applying the same pattern to a different data structure:
> dictionaries.
>
> Here's your task: given a dictionary of student names and scores —
> `{'Alice': 72, 'Bob': 85, 'Carla': 91}` — write a dictionary comprehension
> that creates a new dictionary containing only students who scored above 80.
>
> This is harder than what you've been doing because dictionaries have both
> keys and values — you'll need to decide what to keep from each pair, not
> just transform a single value.
>
> You'll know you've done it well when: (1) the result is a dictionary (not
> a list), (2) it only contains students above 80, and (3) it's written as a
> single comprehension expression.
>
> Give it a real attempt before asking — I'll be here if you get genuinely
> stuck."
