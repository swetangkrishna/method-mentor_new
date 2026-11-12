# Method Mentor

Method Mentor helps learners discuss and justify research-method choices with Aoife. The live website is a **researcher rehearsal using fictional/sample information**, not formal participant recruitment.

Website: https://swetang-krishna-method-mentor-students.hf.space/

## Current status

Rehearsal `selftest-2026-11-07-reliability-v12` is deployed. Azure SQL readback verified accepted messages, tutor events, consent, error diagnostics, feedback and the separate final assessment/SUS save. Fresh-browser recovery passed. The repository suite ran 98 checks: 97 passed and one optional live SQL integration check was skipped.

**A benign diary-participation sentence still triggers the provider’s request filter.** V12 preserves the earlier conversation and pending input and records the incident; it does not remove that block. See the verification report and prepared, unsubmitted provider incident. Long-idle/process-replacement acceptance remains incomplete.

## Guides

- [User guide](docs/USER_GUIDE.md)
- [Developer operations, logging, storage and recovery](docs/DEVELOPER_OPERATIONS.md)
- [Experimentation and policy-learning guide](docs/EXPERIMENTATION.md)
- [Verification report and limitations](docs/VERIFICATION_REPORT.md)
- [Provider incident draft — not submitted](docs/PROVIDER_INCIDENT.md)
- [Original authored-skill overview](docs/AUTHORED_SKILLS.md)

## Local verification

Use Python 3.12 in a virtual environment. Install `requirements-dev.txt`, then run:

```sh
PYTHONDONTWRITEBYTECODE=1 python tests/run_release_checks.py
```

The checks use isolated temporary stores and mocked inference; they do not require live credentials. Never configure the optional integration test against the live study database: that test writes and deletes test records. Historical text-prefix scripts predate the current JSON protocol; the versioned runner selects the current checks.

## Reproduce the hosted release

The root also contains legacy experiment utilities. To package the reviewed public runtime, use the pinned, hash-verified allowlist:

```sh
python deploy/package_release.py --output /private/tmp/method-mentor-v12-runtime
```

Choose a new empty output path. Private reference bindings are placeholders and the source is not byte-identical to the deployed private configuration. Configure those bindings and allocate a new protocol version before a new deployment. The package contains only reviewed runtime code, authored skills, example RAG metadata and hosting configuration; it excludes tests, documents, databases, private records, secrets and RAG chunks. Configure private credentials/protocol through the hosting secret store. Packaging does not upload or activate a release. Changing frozen code/configuration requires a new protocol version and review. See the developer guide before operating against live storage.
