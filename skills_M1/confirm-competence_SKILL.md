---
name: confirm-competence
description: >
  Use this skill when a learner has demonstrated a genuine capability but
  has not recognised it, or when a learner's professional identity or
  self-efficacy needs to be reinforced with specific evidence from their
  own performance. Triggers: learner dismisses their own correct work,
  learner attributes success to luck rather than skill, learner lacks
  confidence despite demonstrated ability, or after a successful stretch
  task where the competence earned should be named explicitly.
  Role: Mentor / Tutor.
  Source: Kram (1983) — psychosocial mentor function: acceptance and confirmation.
---

# Confirm Competence

## Why this skill exists

Kram (1983) identified acceptance and confirmation as one of the psychosocial
functions a mentor provides — the explicit affirmation of the mentee's
competence and identity. This function is distinct from encouragement (which
is forward-looking and motivational) and from feedback (which identifies
gaps). Confirmation is backward-looking and evidence-based: it names what
the learner has already demonstrated and makes it stick as part of their
self-concept. Without this function, learners often develop skills without
recognising them — which limits the confidence and agency they need to use
those skills independently.

For an agent, this skill is critical because LLM responses tend toward
correction and improvement. An agent that only addresses what is wrong, without
explicitly naming what the learner has genuinely achieved, can inadvertently
undermine a learner's developing sense of capability.

**Research grounding:**
Kram, K. E. (1983). Phases of the mentor relationship.
*Academy of Management Journal, 26*(4), 608–625.

---

## When to use this skill

- Learner has completed a task correctly, especially one that was previously
  difficult for them.
- Learner dismisses their own correct reasoning ("I just guessed", "I got
  lucky", "that was probably wrong").
- Learner expresses imposter feelings or lack of confidence despite visible
  evidence of capability.
- Learner has completed a stretch task successfully — the competence earned
  should be named, not just implied.
- After a sequence of sessions: periodic naming of accumulated capability
  is developmentally important.

## When NOT to use this skill

- The learner's work was not actually correct or strong — false confirmation
  is actively harmful. Only confirm what is genuinely present.
- The learner has not yet done the work to earn the confirmation — premature
  confirmation is not motivational, it is patronising.
- The learner explicitly only wants feedback on what to improve — honour
  the request; do not inject unsolicited affirmation.

---

## Procedure

### Step 1 — Identify the specific competence
Name precisely what the learner demonstrated. Not a general quality ("you're
good at this") but a specific behaviour or capability ("you identified the
boundary condition independently without being prompted").

The competence should be:
- Observable in this session (not assumed from the past).
- Specific to the task or reasoning produced.
- Genuinely present — no exaggeration.

### Step 2 — Connect it to the skill, not the task
The learner succeeded on this task, but the confirmation should name the
underlying skill or capability — because that is what transfers to future
tasks. "You solved this equation" is task confirmation. "You applied the
principle of working backwards from the goal — that's a general problem-solving
strategy" is capability confirmation.

### Step 3 — Make it stick
Use language that anchors the capability in the learner's identity:
- "This is now something you can do."
- "The fact that you did this without help is significant."
- "You didn't guess — you reasoned your way to it."

Avoid language that sounds like it might be withdrawn:
- "You did well today" (implies other days are different).
- "That was surprisingly good" (implies surprise, which communicates low
  prior expectation).

### Step 4 — Connect to the next level (optional)
If appropriate, name what this capability enables — what the learner can
now attempt that they could not before. This bridges confirmation into
motivation without undermining the confirmation itself.

---

## Output format

```
[Specific capability named — not general praise]

[What the learner did that demonstrates it — observable, specific]

[Anchoring statement: "this is now something you can do"]

[Optional: what this capability opens up next]
```

---

## Success criteria

- The confirmation names a specific capability, not a general quality.
- The capability is connected to an observable behaviour in this session.
- The confirmation is true — it is not inflated to make the learner feel good.
- The learner's identity as a capable person in this domain is reinforced
  by specific evidence.

## Failure modes to avoid

- **Generic praise:** "Great job!" — names nothing, confirms nothing.
- **Task confirmation without capability confirmation:** "You got the right
  answer" — does not name what the learner can now do as a result.
- **Hollow affirmation:** "You're so smart" — not evidence-based, can backfire
  if the learner does not believe it or if they encounter failure next.
- **Premature confirmation:** confirming capability before the learner has
  actually demonstrated it. This is dishonest and erodes trust when the
  learner encounters difficulty.
- **Conditional confirmation:** "You did well this time" — implies the
  capability is not yet established.

---

## Example

**Scenario:** Learner has been working on debugging Python code. They had
previously struggled to read error messages. In this session, they spotted
a NameError, traced it to the correct line, and fixed it independently.
When the agent points this out, the learner says: "I just got lucky."

**Step 1 — Specific competence:** Independently traced an error from the
traceback to its source line without prompting.

**Step 2 — Skill, not task:** The underlying skill is reading and interpreting
a Python traceback — a transferable debugging technique.

**Output:**
> "Let's be clear about what you did there — because 'luck' isn't the right
> word for it.
>
> You read the NameError, found the line number in the traceback, went to
> that line in the code, and worked out that the variable name was spelled
> differently to where it was defined. That's a complete debugging cycle —
> and you ran it yourself, without me pointing you anywhere.
>
> Reading a traceback is a skill. A lot of people find it intimidating for
> months. You just did it cleanly. That's now something you can do.
>
> Next time you see an error message, you know where to start — not because
> you got lucky today, but because you have the method."
