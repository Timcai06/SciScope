# Security Policy

SciScope includes a hosted FastAPI backend, environment-based secrets, database
connection strings, package-manager installers, and a networked terminal client.
Please report security issues privately instead of opening a public issue.

## Supported Versions

Security fixes target the current `main` branch and the latest published
terminal-client release.

| Component | Supported |
| --- | --- |
| Hosted backend | Current deployed service |
| npm/Homebrew/Scoop TUI | Latest published version |
| Source development stack | Current `main` branch |

## Reporting a Vulnerability

Please email the maintainer or open a private GitHub security advisory if that
option is available for the repository. Include:

- A short description of the issue.
- Affected component or path.
- Reproduction steps or proof of concept.
- Expected impact.
- Any suggested mitigation.

Do not include secrets, database credentials, private API keys, or real user
data in a public issue.

## Security-Sensitive Areas

- `backend/app/core/` and request-budget logic.
- `backend/app/api/` public routes.
- `backend/app/services/deepseek_provider.py` and model-provider settings.
- `configs/`, `.env*`, Render/Supabase deployment settings.
- `packaging/npm/`, `packaging/scoop/`, `packaging/winget/`, and release
  workflows.
- Proxy header handling and client IP trust boundaries.

## Disclosure

We aim to acknowledge credible reports quickly, reproduce the issue, prepare a
fix, and publish a clear advisory or release note when appropriate.
