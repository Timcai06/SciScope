# SciScope TUI Homebrew Release Guide

This guide targets only the Go terminal client.
Python backend, database services, and model artifacts are **not** included in the
Homebrew artifact.

## Scope and packaging boundary

- Packaging target: `tui/sciscope-tui` binary and `homebrew-cask` formula metadata.
- Distribution artifact scope: cross-platform Go binaries + cask metadata.
- Excluded scope: backend API, PostgreSQL/PGVector, crawlers, RAG data, and model assets.

## Release architecture (handoff view)

- Release is driven by git tags matching `v*`.
- `.github/workflows/release.yml` runs:
  - checkout
  - setup Go
  - `goreleaser release --clean` with `workdir: tui`
- `tui/.goreleaser.yaml` builds `darwin`/`linux × amd64/arm64`, generates checksums,
  then publishes Homebrew cask to `Timcai06/homebrew-sciscope`.
- Cask install hook strips macOS quarantine xattr after install.

## Version injection policy

- In Go binary build config:
  - `ldflags: -s -w -X main.version={{ .Version }} -X main.defaultHostedBackendURL={{ .Env.SCISCOPE_HOSTED_BACKEND_URL }}`
  - `{{ .Version }}` is derived from the release tag (for CI) or
    `TUI_VERSION` in local wrappers.
  - `SCISCOPE_HOSTED_BACKEND_URL` sets the release default backend URL; users can
    still override it with `SCISCOPE_BACKEND`.
- Local CI-equivalent verification:

```bash
make tui-build TUI_VERSION=0.2.0
./tui/sciscope-tui --version   # expect: sciscope-tui 0.2.0
```

## One-time setup

1. Create tap repository:

   ```bash
   gh repo create Timcai06/homebrew-sciscope --public --confirm
   ```

2. Add repository secret to `Timcai06/SciScope`:

   - `HOMEBREW_TAP_GITHUB_TOKEN` with write access to `Timcai06/homebrew-sciscope`.

3. Ensure tooling:

   ```bash
   go version
   goreleaser --version
   ```

## Preflight checklist

From repo root:

```bash
make tui-build TUI_VERSION=0.2.0
./tui/sciscope-tui --help
make tui-demo
make tui-doctor
cd tui && go test ./... && cd ..
cd tui && goreleaser check && cd ..
```

After a session exists, optionally verify shell export with `make tui-export-last`.

Snapshot validation (optional):

```bash
cd tui
goreleaser release --snapshot --clean
cd ..
```

## Release operations

```bash
git tag v0.2.0
git push origin v0.2.0
```

This triggers `.github/workflows/release.yml`.

## User install

Newer Homebrew refuses to load casks from third-party taps until the tap is
trusted, so the flow is **tap → trust → install**:

```bash
brew tap Timcai06/sciscope
brew trust --cask timcai06/sciscope/sciscope-tui
brew install --cask sciscope-tui
sciscope-tui
```

Verified on macOS arm64 with Homebrew: installs `sciscope-tui` to
`/opt/homebrew/bin`, `--version` prints the release tag, and the install hook
strips the macOS quarantine xattr so the unsigned binary runs.

## Developer local backend override

For local backend development, start a compatible backend separately from source
and point the TUI at it:

```bash
SCISCOPE_BACKEND=http://127.0.0.1:8000 sciscope-tui
```

## Failure triage

- Token / permission issue:
  check `HOMEBREW_TAP_GITHUB_TOKEN` scope and tap existence.
- Version mismatch:
  check git tag and `TUI_VERSION` alignment.
- Workflow/asset path issue:
  verify `.github/workflows/release.yml` workdir (`tui`) and
  `tui/.goreleaser.yaml` entries.
