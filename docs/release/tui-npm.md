# SciScope TUI npm Install And Release Guide

The npm package is live as `sciscope-tui` and is the simplest cross-platform
install path when Node.js is already available:

```bash
npm install -g sciscope-tui
sciscope-tui
```

The package does not reimplement the client in Node.js. It is a thin installer
and command proxy for the Go binary published by GitHub Releases.

## User Commands

```bash
sciscope-tui
sciscope-tui demo
sciscope-tui doctor
sciscope-tui --version
```

Local backend override:

```bash
SCISCOPE_BACKEND=http://127.0.0.1:8000 sciscope-tui
```

PowerShell:

```powershell
$env:SCISCOPE_BACKEND="http://127.0.0.1:8000"
sciscope-tui
```

## Scope

- Package directory: `packaging/npm/sciscope-tui/`.
- Runtime binary: downloaded from the matching GitHub Release during
  `postinstall`.
- Supported platforms: macOS, Windows, and Linux on arm64/x64.
- Excluded scope: Python backend, PostgreSQL/pgvector, corpora, embeddings, and
  model assets.

## Asset Contract

The npm installer expects these GoReleaser asset names:

```text
sciscope-tui_darwin_arm64.tar.gz
sciscope-tui_darwin_amd64.tar.gz
sciscope-tui_linux_arm64.tar.gz
sciscope-tui_linux_amd64.tar.gz
sciscope-tui_windows_arm64.zip
sciscope-tui_windows_amd64.zip
```

The version in npm maps to GitHub tag `v<version>`. For example,
`sciscope-tui@0.2.1` downloads assets from release tag `v0.2.1`.

## Local Validation

From repo root:

```bash
make npm-package-smoke
make npm-package-pack
```

The smoke target uses `SCISCOPE_TUI_SKIP_DOWNLOAD=1`, so it validates the npm
wrapper without downloading release assets.

To test a real release download:

```bash
cd packaging/npm/sciscope-tui
node scripts/install.js
node bin/sciscope-tui.js --version
```

## Maintainer Publish Notes

One-time setup if automatic publishing is not configured:

1. Create an npm automation token.
2. Add `NPM_TOKEN` to the `Timcai06/SciScope` GitHub repository secrets.

Tag-driven release:

```bash
git tag v0.2.1
git push origin v0.2.1
```

The release workflow publishes the GoReleaser assets first, then publishes the
npm package if `NPM_TOKEN` is configured.

Manual fallback:

```bash
cd packaging/npm/sciscope-tui
npm publish
```

## Runtime Overrides

Use the same environment variables as other TUI channels:

```bash
SCISCOPE_BACKEND=http://127.0.0.1:8000 sciscope-tui
```

Maintainer-only installer overrides:

```bash
SCISCOPE_TUI_SKIP_DOWNLOAD=1 npm pack --dry-run
SCISCOPE_TUI_RELEASE_BASE=https://example.com/releases/v0.2.1 npm install -g sciscope-tui
```
