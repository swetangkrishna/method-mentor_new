# Method Mentor — public verification summary

V12 is deployed. Private SQL readback verified accepted transcript messages, tutor events, consent, sanitized error diagnostics, feedback, and the separate final assessment with ten usability answers. A fresh browser restored the same accepted conversation and feedback state. Repeating final-assessment submission retained the original save. Temporary audit access was removed. Detailed resource addresses, session/reference identifiers, timestamps and extracts are held in the private operator handoff, not this public repository.

## Evidence and limits

- A manual baseline conversation completed 30 learner replies and 31 tutor messages without generation errors; refresh/resume preserved visible text. Its repeated-summary behavior prompted a correction.
- Another baseline scenario encountered a provider filter block on benign methodological discussion. The same issue recurred during live v12 acceptance. V12 keeps the pending input and chat visible and shows a persistent explanation/reference. **The provider block is not resolved.**
- The baseline running process failed to resume after prolonged idle because its database connection was reset. V12 adds a read-only connection preflight and reconnect, without write replay. Local fault tests pass and immediate fresh-client recovery passes; a real overnight/process-replacement recovery test is not yet complete.
- Canonical synthetic snapshot fields, event counts, revisions and action distributions were checked. An isolated local restore/reopen preserved the audited records. This is not a live Azure SQL restore/PITR test.
- Five final synthetic Azure continuation turns passed generation and manual review: focused follow-up on unresolved reasoning, no repeated summary question, and acknowledgement of explicit closure. This is a small continuation test, not proof of general pedagogical quality.
- The original runtime suite ran 92 checks: 91 passed and one optional live SQL check was skipped. The self-contained GitHub suite adds three package-integrity and three private-asset safety checks: 98 run, 97 passed, one skipped. See [runtime results](verification/checks.json) and [repository results](verification/github-checks.json).
- Historical text-prefix fixtures fail against the unchanged JSON-protocol baseline and are superseded by the current protocol checks; [baseline fixture summary](verification/legacy-baseline-check.json).

## Required follow-up

Resolve the recurring apparent provider false positive through supported review, then repeat long manual conversations and a delayed/process-replacement recovery check. Live database disaster recovery, retention enforcement, multiworker/load testing and independent pedagogy scoring remain separate checks. Do not describe the service as permanently error-free or ready for unrestricted study use on the basis of the current results.

The public source uses placeholder private-reference bindings. Reconfigure them privately, review updated provenance and allocate a new protocol version before any new deployment. The exact audited private release remains in the local operator handoff.
