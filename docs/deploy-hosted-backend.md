# Hosted Backend Deployment

This is the production path for the packaged TUI: users run `sciscope-tui`, and
the binary connects to the hosted FastAPI backend compiled into the release.

## Platform

Current public demo deployment:

- Render Web Service from `Dockerfile.backend`
- Supabase Postgres + pgvector for `SCISCOPE_DB_DSN`
- DeepSeek API key kept server-side in Render environment variables
- `SCISCOPE_ENABLE_RUNTIME_EMBEDDINGS=false` on small/free web instances

The checked-in `render.yaml` is a paid Render Blueprint reference that provisions
Render Postgres. Do not use it for the current Supabase free/demo deployment
unless you intentionally want a separate Render-managed database.

Render free services can spin down. The package default is acceptable for a
public demo, but a long-lived production service should move to a paid always-on
web instance and either paid Supabase/Render Postgres capacity.

## Required Secrets

Render prompts for:

```text
DEEPSEEK_API_KEY
SCISCOPE_DB_DSN
```

For free/small web instances, set:

```text
SCISCOPE_ENABLE_RUNTIME_EMBEDDINGS=false
```

This keeps hosted search/chat on PostgreSQL full-text retrieval instead of
loading the local sentence-transformers model inside the web container. Keep the
pgvector tables populated; larger instances can switch this back to `true`.

GitHub Actions needs this repository secret before tagging `v0.2.1`:

```text
SCISCOPE_HOSTED_BACKEND_URL=https://<render-service>.onrender.com
```

`HOMEBREW_TAP_GITHUB_TOKEN` is already the Homebrew publishing secret.

## Database Bootstrap

For the current Supabase deployment, copy the Supabase Shared Pooler connection
string and run the data bootstrap locally:

```bash
export HOSTED_DB_DSN="postgresql://..."
make hosted-db-refresh
```

This applies the schema, enables pgvector, loads papers/chunks, builds chunk
embeddings, and materializes `paper_embeddings` for recommendations.

For the free hosted demo, use a small corpus subset. Full local assets are too
large for the free database tier and should remain in the local development
environment until production capacity is upgraded.

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
