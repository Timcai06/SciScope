# SciScope TUI npm Release Guide

The npm package is the cross-platform developer install path:

```bash
npm install -g sciscope-tui
sciscope-tui
```

It does not reimplement the client in Node.js. The package is a thin installer
and command proxy for the Go binary published by GitHub Releases.

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

## Publish

One-time setup:

1. Claim the `sciscope-tui` package name on npm.
2. Create an npm automation token.
3. Add `NPM_TOKEN` to the `Timcai06/SciScope` GitHub repository secrets.

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
