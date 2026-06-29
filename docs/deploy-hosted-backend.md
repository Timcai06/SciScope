# Hosted Backend Deployment

This is the production path for the packaged TUI: users run `sciscope-tui`, and
the binary connects to the hosted FastAPI backend compiled into the release.

## Platform

The checked-in `render.yaml` is the first hosted target:

- Render web service from `Dockerfile.backend`
- Render Postgres for `SCISCOPE_DB_DSN`
- PostgreSQL `pgvector` extension enabled by `infra/postgres/pgvector.sql`
- DeepSeek API key kept server-side

Use a paid web service/database for a stable backend. Render free services can
spin down, and free Postgres expires; that is not acceptable for a package
default.

## Required Secrets

Render prompts for:

```text
DEEPSEEK_API_KEY
```

GitHub Actions needs this repository secret before tagging `v0.2.1`:

```text
SCISCOPE_HOSTED_BACKEND_URL=https://<render-service>.onrender.com
```

`HOMEBREW_TAP_GITHUB_TOKEN` is already the Homebrew publishing secret.

## Database Bootstrap

After Render creates the Postgres database, copy its external connection string
and run the data bootstrap locally:

```bash
export HOSTED_DB_DSN="postgresql://..."
make hosted-db-refresh
```

This applies the schema, enables pgvector, loads papers/chunks, builds chunk
embeddings, and materializes `paper_embeddings` for recommendations.

Then verify the hosted API:

```bash
export SCISCOPE_HOSTED_BACKEND_URL="https://<render-service>.onrender.com"
make hosted-smoke
curl -fsS "$SCISCOPE_HOSTED_BACKEND_URL/api/ingest/status"
SCISCOPE_HOSTED_BACKEND="$SCISCOPE_HOSTED_BACKEND_URL" make tui-doctor
```

`/readyz` must report `ready`. If it is `not_ready`, do not tag a release.

## Release Cut

Only after the hosted smoke checks pass:

```bash
gh secret set SCISCOPE_HOSTED_BACKEND_URL --repo Timcai06/SciScope --body "$SCISCOPE_HOSTED_BACKEND_URL"
git tag v0.2.1
git push origin v0.2.1
```

After GoReleaser publishes assets, update `packaging/scoop/bucket/sciscope-tui.json`
with the v0.2.1 Windows URLs and hashes, copy it to `Timcai06/scoop-sciscope`,
and verify Homebrew/Scoop.

## Proxy Header Policy

`SCISCOPE_TRUST_PROXY_HEADERS=false` is the safe default. Only enable it when the
edge proxy is known to overwrite client-supplied `X-Forwarded-For`; otherwise a
caller can spoof IPs and bypass anonymous request budgets.
