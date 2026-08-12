# Security Policy

OAuth2Agent handles high-value credentials. Treat every OAuth source file and every generated Agent Identity file as a secret.

## Supported versions

Only the current `main` branch and latest tagged release are supported.

## Reporting a vulnerability

Please do not publish real OAuth tokens, Agent private keys, task IDs, or Sub2API administrator keys in a public issue. Open a GitHub issue with redacted reproduction details first, or use a private contact channel if one is configured on the repository.

## Credential handling guarantees

- OAuth access tokens are used in memory for Agent registration and are not written by the converter.
- Generated identity files are written atomically and the tool attempts to set mode `0600`.
- Agent Identity private keys remain sensitive even though they cannot be used as ordinary ChatGPT OAuth tokens.
- `verify --check-isolation` is a runtime check, not a permanent guarantee of upstream authorization policy.
