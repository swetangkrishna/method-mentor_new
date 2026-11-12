---
title: Method Mentor Student Testing
emoji: 📚
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 6.28.0
app_file: app.py
python_version: "3.12"
short_description: Research-methods conversations for invited testers
startup_duration_timeout: 30m
---

Sign in using the individual test account provided by your researcher.
No Hugging Face account is required to use the app.

This repository contains application code only. Reference text and the RAG index
are downloaded server-side from a private repository using a scoped read token.
API keys and account password hashes are configured as Space Secrets, not files.

The research workflow is deployed in rehearsal mode: use sample information only.
Consent, assessments, conversations and action traces use external Azure SQL storage.
Rehearsal records are excluded from formal effectiveness analysis and policy training.
Copy your transcript if you want your own record; formal recruitment is not enabled.
Azure Foundry model calls use the researcher's existing Azure quota and credits.

Deployment variables: `RAG_PRIVATE_SOURCE=1`, `LLM_BACKEND=azure_foundry`,
`AZURE_FOUNDRY_MODEL=llama70b`, and `AZURE_FOUNDRY_ENDPOINT`.
Required Secrets: `RAG_SOURCE_TOKEN`, `AZURE_FOUNDRY_KEY`, `PARTICIPANTS_JSON`,
and `FLASK_SECRET`. The read token needs only repository-content read permission
for the private source repository named in `rag_assets.json`.

Study deployment: `STUDY_ENABLED=1`, with `STUDY_DATABASE_URL` and
`STUDY_PROTOCOL_JSON` in encrypted Secrets. The database connection verifies TLS.
No participant data, private reference text or credentials belong in this repository.
