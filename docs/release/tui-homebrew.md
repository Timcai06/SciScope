# SciScope TUI Homebrew Release

This release path packages only the Go terminal client. The Python backend,
PostgreSQL data services, and local LLM remain separate local services.

## One-time setup

1. Create the tap repository:

   ```bash
   gh repo create Timcai06/homebrew-sciscope --public --confirm
   ```

2. Add a repository secret on `Timcai06/SciScope`:

   ```text
   HOMEBREW_TAP_GITHUB_TOKEN
   ```

   The token needs write access to `Timcai06/homebrew-sciscope`.

## Preflight

Run from the SciScope repository root:

```bash
cd tui && GOCACHE=../.cache/go-build go test ./... && cd ..
make tui-build TUI_VERSION=0.1.0
./tui/sciscope-tui --version
./tui/sciscope-tui --help
make -n tui-demo
cd tui && goreleaser check && cd ..
```

Expected version output:

```text
sciscope-tui 0.1.0
```

## Cut a release

```bash
git tag v0.1.0
git push origin v0.1.0
```

The GitHub Actions release workflow runs GoReleaser from `tui/`, uploads
multi-platform archives, writes checksums, and opens/updates the Homebrew cask
in `Timcai06/homebrew-sciscope`.

## User install

```bash
brew install Timcai06/sciscope/sciscope-tui
sciscope-tui --demo
```

For a real backend:

```bash
make backend
make llm
sciscope-tui
```
