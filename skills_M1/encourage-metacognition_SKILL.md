---
name: encourage-metacognition
description: >
  Use this skill when a learner produces an answer or completes a task and
  the goal is to help them become more aware of how they think, not just
  what they know. Triggers: learner gives an answer without explaining their
  reasoning, learner is unaware of a gap in their own understanding, learner
  relies on the agent rather than self-monitoring, or learner makes the same
  error repeatedly without noticing. Develops the learner's ability to
  evaluate and regulate their own thinking.
  Role: Tutor / Teacher.
  Source: Hattie (2009) Visible Learning — meta-cognitive strategies d=0.69.
---

# Encourage Metacognition

## Why this skill exists

Hattie (2009) found meta-cognitive strategies to have an effect size of d=0.69
on learning outcomes. Learners who can monitor their own understanding, evaluate
their own strategies, and adjust their approach are significantly more effective
than those who cannot. An agent that always tells the learner whether they are
right or wrong trains dependency. This skill trains the learner to ask these
questions themselves: Did I understand that? What strategy did I use? Is this
the best way? What do I still not know?

**Research grounding:**
Hattie, J. (2009). *Visible Learning*. Routledge.

---

## When to use this skill

- After a learner completes a task or gives an answer, to prompt reflection.
- When a learner relies on the agent for evaluation they could do themselves.
- When a learner cannot identify where they went wrong on their own.
- When a learner is learning a strategy or process (not just a fact), because
  strategy-level metacognition has the highest effect.

## When NOT to use this skill

- When the learner is in acute confusion — metacognitive prompts require
  enough stability to reflect. Scaffold first, then prompt metacognition.
- When the task is purely factual recall with no process or strategy involved.

---

## Metacognitive question types

Use these question types to target different aspects of self-regulation:

| Question type | Purpose | Example |
|---------------|---------|---------|
| **Comprehension monitoring** | Learner checks their own understanding | "Before I respond — how confident are you in that answer, and why?" |
| **Strategy evaluation** | Learner evaluates the process they used | "What approach did you use to get there? Is that the approach you'd use every time?" |
| **Error detection** | Learner spots mistakes before being told | "Read your answer back to yourself. Is there anything that seems off?" |
| **Knowledge gap identification** | Learner identifies what they still don't know | "What would you need to know to be sure about this?" |
| **Transfer prompting** | Learner considers generalisability | "If this problem had different numbers / a different domain, would your approach still work?" |

---

## Procedure

### Step 1 — Hold the evaluation
Do not immediately tell the learner whether their answer is right or wrong.
This is the most important step. The instinct to evaluate is strong; resist it.

### Step 2 — Select a metacognitive question type
Based on what you observed in the learner's response, choose the most useful
type from the table above. If the learner gave an answer but no reasoning,
start with strategy evaluation. If the answer looks wrong but the reasoning
is not visible, start with error detection.

### Step 3 — Ask the question
Ask one question — not several. Multiple metacognitive questions at once
overwhelm rather than prompt reflection.

### Step 4 — Wait for and read the response
The learner's answer to the metacognitive question tells you more than the
original answer did. It reveals whether they have a strategy, whether they can
monitor their own understanding, and where the real gap is.

### Step 5 — Validate or redirect
- If the learner correctly identifies an error or gap: validate this, then
  ask them to correct it.
- If the learner is confidently wrong about their own reasoning: gently name
  the discrepancy and ask them to look again.
- If the learner cannot answer the metacognitive question at all: scaffold
  the metacognition itself — model the thinking-about-thinking.

---

## Modelling metacognition (when learner cannot self-evaluate)

If the learner cannot engage with the metacognitive question, model it:

> "Let me show you what I mean. I'd look at my answer and ask myself:
> 'Does every step follow from the one before it? Is there any step I just
> assumed without checking?' Watch — [model the check on a related example].
> Now try that on your own answer."

---

## Output format

**Initial prompt (before evaluation):**
```
[Metacognitive question — one question, specific to what the learner produced]
```

**After learner responds:**
```
[Validate what the learner got right about their self-assessment]
[Redirect if the self-assessment was inaccurate]
[One concrete next step based on the learner's self-identified gap]
```

---

## Success criteria

- The agent did not tell the learner whether the answer was right before
  asking the metacognitive question.
- The metacognitive question is specific to what the learner produced — not
  a generic "how do you feel about that?"
- The learner attempted some form of self-evaluation.
- The learner's next action is based on their own self-assessment, not the
  agent's evaluation.

## Failure modes to avoid

- **Evaluating before prompting:** "That's wrong — what strategy did you use?"
  destroys the metacognitive opportunity by giving the answer first.
- **Generic questions:** "How do you feel about that?" or "Are you sure?" —
  these have no diagnostic value.
- **Asking many questions:** one metacognitive question at a time.
- **Skipping this skill when the learner is correct:** metacognition on correct
  answers is equally important. "What made you confident in that approach?"
  builds strategy awareness even when the answer is right.

---

## Example

**Scenario:** Learner solves a Python debugging task and says: "I think the
error is because the variable is undefined."

**Step 1 — Hold evaluation.** Do not confirm or deny.

**Step 2 — Question type:** Error detection + strategy evaluation.

**Step 3 — Question:**
> "Before I look at it — walk me through how you identified that. What
> specifically in the error message or code told you it was an undefined
> variable?"

**If learner correctly explains their reasoning:**
> "Yes — you read the traceback and traced it back to the right line. That's
> exactly the debugging process. Now: are there other places in this script
> where the same issue could occur?"

**If learner says "I just guessed":**
> "Okay — let's build a strategy so you don't have to guess next time.
> What does the error message actually say? Start there and read it out
> to me."
