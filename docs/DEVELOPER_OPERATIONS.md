# Method Mentor — developer operations

This public guide documents the application and operating procedures. Actual subscription/resource names, database addresses, firewall addresses, account records, private reference bindings and incident extracts belong in the operator’s private handoff and secret store. They are intentionally excluded from GitHub.

## Architecture and setup

`app.py` is the Gradio entry point. `space_bridge.py` supplies authenticated server identity to a fresh internal Flask client per operation. `human_validation_server.py` coordinates the tutor. `research_runtime.py` manages consent, frozen versions and canonical session saves. `research_store.py` provides transactions, ownership checks and optimistic revisions; `sqlserver_store.py` connects to Azure SQL with verified TLS. `agent.py`, `structured_output.py`, `pedagogical_runtime.py`, `stage_tracker.py` and `tutor_actions.py` control generation and pedagogy. Authored skills are under `skills_M1/`.

Use Python 3.12 and install `requirements-dev.txt` in a virtual environment for local checks. The managed hosting service supplies some of those packages itself. Read `.env.example`; provide real values privately. Never commit credentials, participant accounts, research records, or reference chunks.

| Configuration | Purpose |
|---|---|
| `LLM_BACKEND=azure_foundry` | Selects the model provider |
| `AZURE_FOUNDRY_ENDPOINT` | Operator’s endpoint |
| `AZURE_FOUNDRY_MODEL` | Operator’s deployment name |
| `AZURE_FOUNDRY_REQUEST_PROFILE=reasoning` | Completion-token limits and provider-default temperature |
| `AZURE_FOUNDRY_KEY` | Secret model credential |
| `STUDY_ENABLED=1` | Canonical research lifecycle |
| `STUDY_DATABASE_URL` | Secret, URL-encoded `mssql://` connection |
| `STUDY_PROTOCOL_JSON` / `STUDY_PROTOCOL_FILE` | Private protocol and allocation seed |
| `PARTICIPANTS_JSON` / `PARTICIPANTS_FILE` | Private hashed participant accounts |
| `FLASK_SECRET` | Stable, random secret of at least 32 characters |
| `COOKIE_SECURE=1` | HTTPS-only cookies |
| `METHOD_MENTOR_DATA_DIR` | Restricted runtime materialization directory |
| `RAG_PRIVATE_SOURCE=1`, `RAG_SOURCE_TOKEN` | Private reference setup and scoped read token |
| `RAG_EMBED_DEVICE=cpu` | CPU embeddings |

The repository’s reference manifest is an **example with placeholder repository/revision/checksums**. Before operating RAG, use the private handoff to set the exact approved repository binding in `student_assets.py` and provide a pinned `rag_assets.json` with real SHA-256 values. The repository-name check deliberately remains restrictive. Do not weaken that validation, expose the token or publish reference chunks. An example is in `config/rag-assets.example.json`.

## Canonical records and logs

Azure SQL is canonical in study mode. Local SQLite and runtime temporary files are auxiliary and can disappear when hosting is replaced. `dbo.research_records` has `kind`, `id`, `owner`, `study`, JSON `payload`, optimistic `revision` and `updated`.

| Kind | Content |
|---|---|
| `protocol` | Frozen protocol and code/skill/model/RAG provenance |
| `enrollment` | Consent, assigned condition, synthetic status and baseline or explicit non-collection status |
| `session` | Ordered accepted transcript, tracker, condition, provenance, events, end and feedback state |
| `error` | Private reference, category, route/session/time, allowlisted diagnostics and provenance |
| `post` | Separate final reasoning assessment, confidence and ten SUS answers/score |
| `withdrawal` | Tombstone after active owner/study records are deleted |

A `tutor_turn` event records stage state, selected action, policy ID/probabilities, declared skill/move, guard/quality flags, model trace, latency and RAG source names/content hashes. The opening tutor message also has an event. Expect one more tutor event than accepted learner replies in a normal session. `enactment_verified=False` means that human verification is still needed; selected/generated action labels do not prove skill enactment.

The five-question conversation feedback is saved inside the session with a `survey` event. The final assessment and ten-question SUS instrument are a separate `post` save. Ending alone does not save either questionnaire. Failed generation input is retained in the browser but is not an accepted transcript turn. Raw provider payloads and every attempted input are intentionally not research logs.

Error-log write failures produce a sanitized console signal. An outage can still prevent a canonical error record; monitor this signal rather than promising perfect logging during an outage. Keep references and private extracts out of public issues.

## Recovery and incident handling

V12 checks the SQL connection before operations and transaction entry, and reconnects if that read-only preflight fails. It never automatically replays a write or uncertain commit. If a save is interrupted, reopen canonical state before resubmitting. The app serializes requests within a single worker; this is not distributed locking for arbitrary multiworker scaling.

For an incident, collect the reference, version, operation and time privately. Inspect only the necessary records with approved access and parameterized queries. Check authentication, current hosting revision, model/profile, quota/rate limits, SQL connectivity, error-record persistence and the latest accepted message. Preserve sanitized evidence. Do not attempt to recover blocked output or bypass provider protection. See [provider incident template](PROVIDER_INCIDENT.md).

Use least-privilege SQL access and an exact application-egress firewall rule. Hosting restarts can change egress. Obtain the new address from sanitized diagnostics and update the existing rule when authorized. Do not use broad address ranges or allow-all access. Temporary operator access must be approved, restricted, removed in cleanup and independently checked removed. Exact identifiers and commands belong in the private operator runbook.

## Backups, retention and withdrawal

With an authorized connection configured privately, use `research_tools.py`. Set `PYTHONPATH` to the selected runtime and choose a private output directory:

```sh
umask 077
export PYTHONPATH="$PWD"
python research_tools.py backup --output /private/operator-backups/study.json
```

Backups include sensitive records and protocol allocation seeds: encrypt/restrict them and exclude them from Git. Restore only into a separate empty database:

```sh
python research_tools.py restore --input /private/operator-backups/study.json
```

The restore routine refuses a nonempty store. Verify counts, JSON content, ownership, revisions and fresh-client recovery. Do not rehearse recovery against live records. Local isolated restore/reopen tests passed; a live Azure disaster-recovery/PITR rehearsal and automatic-backup verification remain operator tasks.

The protocol retention-days value does not schedule deletion. Assign an operator to retention enforcement and backup expiry. Withdrawal deletes active records for an owner/study and writes a blocking tombstone; backups, other versions and auxiliary logs need separate policy handling. Local withdrawal tests do not establish deletion from every backup.

## Packaging, releases and rollback

Run `python tests/run_release_checks.py` for the self-contained suite. It verifies runtime import origins and isolated lifecycle, ownership, conflict, recovery, policy, JSON, model-profile, diagnostics, UI callback and packaging behavior. The optional live SQL integration check is skipped unless a designated disposable integration database is configured. Never point that test at the live study store: it writes/deletes test records.

`deploy/package_release.py` copies only the hash-verified public runtime allowlist into a new output directory. It refuses altered files, path escapes, linked sources and existing output directories. It never uploads or activates anything. The root contains legacy tools; use the allowlist rather than uploading the whole checkout.

**Public-source redaction changes provenance.** This public package contains placeholder private-reference bindings and a redacted endpoint comment. It is not byte-identical to the deployed private configuration. Use the detailed private handoff for that audited deployment. For a new deployment, configure approved private bindings, regenerate/review the manifest, rerun checks and use a new protocol version. Never reuse the frozen live version after changing code/configuration.

Before activation, preserve matching code/configuration/protocol/model rollback snapshots privately; review the expected parent revision and explicit file list. Obtain activation approval, pause/update/restart as appropriate, check egress, and verify consent/start/reply/resume/transcript/end/feedback/final-assessment saves using synthetic data. Audit canonical records and references, then remove temporary access. Earlier rehearsal versions remain read-only and new versions require consent again. Rolling back code alone can fail frozen-provenance checks.

See [experimentation](EXPERIMENTATION.md), [verification](VERIFICATION_REPORT.md) and [user guide](USER_GUIDE.md).
