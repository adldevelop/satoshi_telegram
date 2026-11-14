# Development Rules

## Architecture
- Use clean architecture.
- Keep components modular.
- Separate business logic from infrastructure.

## Development
- Always write tests.
- Follow SOLID principles.
- Avoid unnecessary dependencies.
- Use environment variables for secrets.

## Workflow
- Analyze before implementing.
- Create a plan for complex changes.
- Run tests after modifications.
- Never deploy to production without approval.
- Never expose credentials or API keys.

## Documentation
- Keep README updated.
- Document important architectural decisions.

## Security Rules
- NEVER commit, push, upload, or expose credentials, API keys, access tokens, passwords, private keys, certificates, or secrets.
- NEVER include sensitive information in source code, logs, error messages, documentation, or Git history.
- NEVER commit .env, .env.*, credentials files, service account JSON files, private keys, or local configuration containing secrets.
- Always use environment variables for sensitive configuration.
- Always maintain and verify .gitignore to exclude secrets and sensitive files.
- Before every Git commit or push, inspect staged files for credentials, secrets, tokens, and sensitive information.
- If a secret is detected, STOP immediately. Do not commit or push until the issue is resolved.
- Never bypass Git hooks, secret scanners, or security checks.
- Never assume a file is safe to commit based only on its filename.
- Never print or reproduce actual secret values when investigating security issues.
- If credentials are accidentally committed or exposed, notify the user immediately. Recommend revoking and rotating the affected credentials. Removing the file from the latest commit is not sufficient because Git history may retain it.
- Never push directly to production branches without explicit user approval.
- Never deploy applications or infrastructure to production without explicit user approval.