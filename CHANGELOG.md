# Changelog

## 0.2.0 - 2026-08-12

- Standalone ChatGPT OAuth PKCE login flow.
- Convert existing Codex/Sub2API-style OAuth JSON into Agent Identity.
- Generate Ed25519 Agent Identity keys and register `responsesapi`.
- Register and decrypt encrypted run `task_id` responses.
- Export Sub2API-compatible or Codex identity-only `auth.json`.
- Sign per-request `AgentAssertion` headers.
- Verify Codex Responses and optional conversation isolation.
- Offline end-to-end mock simulation.
- Reject ambiguous files containing multiple distinct OAuth identities.
