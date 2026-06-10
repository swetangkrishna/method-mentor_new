# Pedagogical Skills — Master Index

**Project:** Pedagogical Skills in GenAI Educational Agents
**Skill format:** Anthropic SKILL.md (YAML frontmatter + markdown body)
**Total skills:** 16
**Roles covered:** Tutor, Teacher, Educator, Mentor

Each skill is a directory containing a `SKILL.md` file. The YAML frontmatter
`name` and `description` fields are pre-loaded into the agent's system prompt
(first-level disclosure). The full body is loaded only when the agent
determines the skill is relevant to the current task (second-level disclosure).

---

## Skills by paper

### Shulman (1986, 1987) — Pedagogical Content Knowledge (PCK)
*Harvard Educational Review; Educational Researcher*

| # | Skill name | Directory | Role |
|---|-----------|-----------|------|
| 1 | transform-content | `shulman/transform-content/` | Tutor / Teacher |
| 2 | identify-misconceptions | `shulman/identify-misconceptions/` | Tutor / Teacher |
| 3 | reflect-on-pedagogy | `shulman/reflect-on-pedagogy/` | Educator |

**Core contribution:** Teachers must transform content (not merely transmit it),
diagnose misconceptions (not just mark errors), and reflect on their own
pedagogical reasoning after each instructional cycle.

---

### Vygotsky (1978) + Wood, Bruner & Ross (1976) — ZPD & Scaffolding
*Mind in Society; Journal of Child Psychology and Psychiatry*

| # | Skill name | Directory | Role |
|---|-----------|-----------|------|
| 4 | diagnose-zpd | `vygotsky/diagnose-zpd/` | Tutor |
| 5 | scaffold-and-release | `vygotsky/scaffold-and-release/` | Tutor |

**Core contribution:** Effective tutors identify the ZPD (the productive
difficulty zone between independent and impossible performance), provide
graduated support (scaffolding), and remove that support as the learner
gains mastery (release).

---

### Hattie (2009) — Visible Learning
*Routledge; meta-analysis of 800+ studies, 80M+ students*

| # | Skill name | Directory | Role | Effect size |
|---|-----------|-----------|------|------------|
| 6 | provide-formative-feedback | `hattie/provide-formative-feedback/` | Tutor / Teacher | d=0.73 |
| 7 | set-learning-objectives | `hattie/set-learning-objectives/` | Teacher / Educator | d=0.75 |
| 8 | encourage-metacognition | `hattie/encourage-metacognition/` | Tutor / Teacher | d=0.69 |

**Core contribution:** The highest-impact teaching practices are feedback
(targeted at the right level), teacher clarity (explicit objectives and
success criteria), and metacognitive strategy training.

---

### Kolb, Kolb, Passarelli & Sharma (2014) — Educator Role Profile (KERP)
*Simulation & Gaming, SAGE*

| # | Skill name | Directory | Role |
|---|-----------|-----------|------|
| 9 | facilitate-discussion | `kolb/facilitate-discussion/` | Teacher / Tutor |
| 10 | design-learning-experience | `kolb/design-learning-experience/` | Teacher / Educator |

**Core contribution:** Effective educators move through four roles —
facilitator, subject expert, evaluator, coach — and design learning that
moves learners through all four experiential modes (experiencing, reflecting,
conceptualising, experimenting).

---

### Kram (1983, 1985) — Mentor Functions Framework
*Academy of Management Journal; Mentoring at Work*

| # | Skill name | Directory | Role | Function type |
|---|-----------|-----------|------|--------------|
| 11 | assign-stretch-tasks | `kram/assign-stretch-tasks/` | Teacher / Mentor | Career |
| 12 | provide-emotional-support | `kram/provide-emotional-support/` | Mentor / Tutor | Psychosocial |
| 13 | confirm-competence | `kram/confirm-competence/` | Mentor / Tutor | Psychosocial |

**Core contribution:** Mentors provide both career functions (challenging
assignments, sponsorship, coaching) and psychosocial functions (role modelling,
counselling, acceptance and confirmation). Both categories are necessary for
full mentoring effectiveness.

---

### Clutterbuck (2004, 2015) — Developmental Mentoring Model
*Everyone Needs a Mentor, CIPD; Coaching and Mentoring, Routledge*

| # | Skill name | Directory | Role |
|---|-----------|-----------|------|
| 14 | challenge-assumptions | `clutterbuck/challenge-assumptions/` | Mentor / Tutor |
| 15 | probe-intended-decisions | `clutterbuck/probe-intended-decisions/` | Mentor |

**Core contribution:** Developmental mentors act as critical friends (surfacing
and stress-testing unexamined beliefs) and sounding boards (helping mentees
examine their own decisions through structured questioning, without
substituting the mentor's judgement).

---

### Biggs & Tang (2011) — Constructive Alignment
*Teaching for Quality Learning at University, Open University Press*

| # | Skill name | Directory | Role |
|---|-----------|-----------|------|
| 16 | align-outcomes-activities-assessment | `biggs/align-outcomes-activities-assessment/` | Educator |

**Core contribution:** Learning outcomes, teaching activities, and assessment
tasks must all target the same cognitive operation (Bloom level) and content.
Misalignment is the most common structural flaw in lesson design and explains
poor learning outcomes even when individual components are well-designed.

---

## Skills by role

### Tutor (interactive, adaptive, 1-to-1)
1. diagnose-zpd
2. scaffold-and-release
3. identify-misconceptions
4. transform-content
5. provide-formative-feedback
6. encourage-metacognition
7. provide-emotional-support *(also Mentor)*
8. confirm-competence *(also Mentor)*

### Teacher (instructional design, delivery, group)
9. set-learning-objectives
10. facilitate-discussion
11. design-learning-experience *(also Educator)*
12. assign-stretch-tasks *(also Mentor)*

### Educator (curriculum, systemic, reflective)
13. align-outcomes-activities-assessment
14. reflect-on-pedagogy
15. design-learning-experience *(also Teacher)*

### Mentor (relational, long-horizon, identity)
16. provide-emotional-support
17. confirm-competence
18. challenge-assumptions
19. probe-intended-decisions
20. assign-stretch-tasks *(also Teacher)*

---

## Relationship to experimental matrix

**M1 (human-authored skills):** All 16 SKILL.md files are the M1 skill library.
The agent receives the `name` and `description` of all 16 at startup and loads
full bodies on demand.

**M5 (compositional skill synthesis):** Complex teaching behaviours are built
by chaining skills. Example: `diagnose-zpd` → `identify-misconceptions` →
`scaffold-and-release` → `provide-formative-feedback` constitutes a complete
tutoring cycle.

**M6 (single agent replacing multi-agent):** The full 16-skill library enables
one agent to act as tutor, teacher, educator, and mentor — roles that might
otherwise require separate specialised agents.

**M2 (RL-inspired improvement):** The `reflect-on-pedagogy` skill produces
the reflection output that feeds the reward signal or skill-refinement loop.

---

## Directory structure

```
pedagogical-skills/
├── INDEX.md  ← this file
├── shulman/
│   ├── transform-content/SKILL.md
│   ├── identify-misconceptions/SKILL.md
│   └── reflect-on-pedagogy/SKILL.md
├── vygotsky/
│   ├── diagnose-zpd/SKILL.md
│   └── scaffold-and-release/SKILL.md
├── hattie/
│   ├── provide-formative-feedback/SKILL.md
│   ├── set-learning-objectives/SKILL.md
│   └── encourage-metacognition/SKILL.md
├── kolb/
│   ├── facilitate-discussion/SKILL.md
│   └── design-learning-experience/SKILL.md
├── kram/
│   ├── assign-stretch-tasks/SKILL.md
│   ├── provide-emotional-support/SKILL.md
│   └── confirm-competence/SKILL.md
├── clutterbuck/
│   ├── challenge-assumptions/SKILL.md
│   └── probe-intended-decisions/SKILL.md
└── biggs/
    └── align-outcomes-activities-assessment/SKILL.md
```
