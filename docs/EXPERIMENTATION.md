# Method Mentor — experimentation and research handoff

Prepared 7 November 2026. Use with [developer operations](DEVELOPER_OPERATIONS.md). Rehearsal testing, pedagogical policy learning and model-weight training are different activities. This application supports the first two; these scripts do not fine-tune model weights.

## Keep evaluation reproducible

Create an experiment record before running a comparison: question, protocol ID/version, hypothesis/outcome, conditions, inclusion/exclusion rules, participant allocation and split seed, model deployment/version, request profile, source revision, skill hashes, RAG manifest/settings, action schema, policy ID and budget. Preserve the frozen protocol and provenance with private results.

Use a separate pilot protocol and synthetic account for development. Pilot sessions have `synthetic=True` and are excluded from formal group means and policy training. A protocol version is frozen against code/configuration changes; allocate a new version for prompt, code, model, skill, policy, retrieval or configuration changes. Never silently change a condition halfway through a study.

The current rehearsal does not collect a baseline reasoning assessment. It therefore cannot estimate pre/post reasoning gain. Restoring that outcome requires a baseline and an appropriately configured and approved formal protocol. Formal mode also requires external storage, a recovery rehearsal, approval reference, researcher contact, participant information and allocation seed. Those validation requirements are not an ethics approval process.

## Available conditions

| Condition | Main comparison |
|---|---|
| `descriptions` | Skill descriptions; fixed policy, RAG, single mentor |
| `full_skills` | Full selected skill procedure; fixed policy, RAG, single mentor |
| `no_skills` | Move-only action space, no authored skill, fixed policy, RAG |
| `no_skills_learned` | Move-only action space with approved learned policy |
| `no_rag` | Full skills without retrieval |
| `multi_agent` | Planner, mentor and critic architecture |
| `learned_policy` | Full skills with approved learned policy |
| `composite_skills` | Approved bounded action sequences |

Condition definitions are in `study_protocol.CONDITIONS`. Assignment is deterministic using the protocol’s private allocation seed and participant/study key. Changing that seed is a study-design change. Do not describe this as stratified allocation or verified group balance without checking the design and resulting counts.

The action schemas are `skills-moves-v1` and `moves-only-v1`. Do not combine their observations into one learned policy. The v12 fixed closing-policy change records `fixed-stage-v2` or `fixed-moves-v2`; the schemas remain unchanged. Learned-policy probabilities are not overridden by that fixed-policy tie-breaking change. Planner and composite conditions have their own policy identities and need separate evaluation.

## Evaluation sequence

1. Run `tests/run_release_checks.py` against the candidate. Inspect every failure and skip. Verify module origins so tests cannot silently import older code.
2. Run synthetic end-to-end tests with the intended model and request profile. Include the original failure context, ambiguous short replies, long replies, explicit uncertainty, a rejected method, citation-search discussion and an explicit wish to finish.
3. Conduct manual browser conversations through all six stages. Test beyond the original 23-turn failure point and toward the configured limit. In the current freeform scenario the configured limit is 40 tutor turns, including the opening tutor message; inspect the actual scenario before assuming that value for another experiment.
4. Refresh, use a fresh browser client, and resume. Test after prolonged idle and, in a controlled rehearsal, after host replacement. A browser refresh alone does not prove process-restart durability.
5. Check exact canonical message order, event counts, action probabilities, provenance, RAG hashes, failure references, consent, end, five-question feedback and the separate final assessment/SUS save. Check rejected inputs do not appear as accepted messages.
6. Review the conversation itself: relevance, repeated prompts, premature closure, unsupported claims, method endorsement and learner autonomy. A response that passes JSON validation can still be pedagogically poor.
7. Record latency, model requests/retries, token usage when supplied, quota failures, generation/format/filter failures and cost. Log missing usage explicitly rather than assigning zero. A provider’s safety block remains a failed turn; do not relabel it as success because the UI preserved the conversation.
8. Approve an explicit release only after reviewing the evidence and known limitations. Then repeat the live save/recovery checks. Test private evidence stays outside public uploads.

No finite test establishes that a probabilistic model will never fail. Robust operation requires recoverable errors, durable accepted-turn saves, monitoring and incident follow-up alongside model/prompt improvements.

## Human scoring and policy learning

The tooling in `research_tools.py` uses the runtime selected by `PYTHONPATH`. Set the database connection privately. Write exports to a private directory outside the public runtime checkout. Commands below illustrate one named approved study; substitute its full `id:version` value.

```sh
umask 077
export PYTHONPATH="$PWD"
python research_tools.py blind --study 'STUDY_ID:VERSION' --output /private/research/blinded-reasoning.json
python research_tools.py actions --study 'STUDY_ID:VERSION' --output /private/research/action-packet.json
python research_tools.py ratings --study 'STUDY_ID:VERSION' --rater raterA --input /private/research/ratings.json
python research_tools.py analyse --study 'STUDY_ID:VERSION' --output /private/research/analysis.json
python research_tools.py dataset --study 'STUDY_ID:VERSION' --output /private/research/learning-rows.json
python research_tools.py train --input /private/research/learning-rows.json --action-space skills --minimum 3 --output /private/research/policy-candidate.json
python research_tools.py evaluate --input /private/research/learning-rows.json --action-space skills --policy /private/research/policy-candidate.json --output /private/research/policy-evaluation.json
```

`blind` and `actions` may create blinded identifiers in the configured database; `ratings` writes human ratings. Use authorized research access, not a read-only incident connection. Training/evaluation consume local files. `qtrain` and `compose` are additional offline candidate-generation commands; inspect their assumptions before use. Nothing is promoted automatically.

Reasoning scoring has four 0–4 dimensions: question/method alignment, alternatives/trade-offs, feasibility/ethics and critical reasoning. The normalized total is the sum divided by 16. The action rubric separately evaluates skill enactment, move enactment, autonomy and context fit; move-only actions omit skill enactment. Use independent human review rather than equating generated labels or selected actions with successful teaching.

Five conversation-feedback ratings contribute to the application reward. SUS uses ten alternating positive/negative items, scored 0–100 with the standard transformation in `sus_score()`. Preserve item wording, order and 1–5 agreement scale. The final assessment is stored separately from the five-question feedback.

Policy-learning export requires protocol permission for reuse, a completed usable session, sufficient feedback and verified action enactment. Participant splits must remain separate across train/test; do not randomly split turns from the same person across partitions. Exclude synthetic, withdrawn and missing/invalid observations. Keep the blind-ID crosswalk private. Inspect the actual exported eligibility fields before fitting.

Offline IPS estimates require target-policy support under the logged behavior policy and can have high variance. A deterministic fixed policy provides little support for unchosen actions. The evaluator explicitly returns `promotion_ready=False`; it is not evidence of causal effectiveness. Pre-register prospective comparisons and account for repeated observations within participants before making effectiveness claims.

## Proposed next experiment

V12 is activated and live saves have been rechecked. The diaries/attrition sentence still produces a provider block. Preserve the incident privately and resolve it with the provider before treating the release as suitable for unrestricted study use. After that, run at least two manual long sessions on different benign topics, including a delayed resume. Preserve any filter references. Compare the repeated-summary rate and successful-turn rate with v11 using a fixed synthetic test set, then have a reviewer inspect responses without seeing the condition. Do not start formal recruitment while the current idle-resume failure or unverified live save paths remain unresolved.
