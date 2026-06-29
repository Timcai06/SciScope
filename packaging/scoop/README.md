# SciScope TUI Scoop Packaging

Scoop is the preferred Windows package-manager path while the winget submission
waits for Microsoft moderator review. It is controlled by our own bucket
repository, so releases can move at the same pace as GitHub tags.

## User install flow

```powershell
scoop bucket add sciscope https://github.com/Timcai06/scoop-sciscope
scoop install sciscope-tui
sciscope-tui --demo
```

Production attach:

```powershell
$env:SCISCOPE_BACKEND="https://api.sciscope.example"
sciscope-tui
```

## Bucket repository

The public bucket repository is:

```text
https://github.com/Timcai06/scoop-sciscope
```

It uses this layout:

```text
scoop-sciscope/
└── bucket/
    └── sciscope-tui.json
```

Keep `packaging/scoop/bucket/sciscope-tui.json` in this repository aligned with
`bucket/sciscope-tui.json` in the bucket repository.

## Release update flow

1. Tag and publish SciScope, for example `v0.2.0`.
2. Confirm the GitHub Release contains:
   - `sciscope-tui_windows_amd64.zip`
   - `sciscope-tui_windows_arm64.zip`
   - `checksums.txt`
3. Update `bucket/sciscope-tui.json`:
   - `version`
   - release URLs
   - `hash` values
4. Commit and push the bucket repository.

Scoop users can then run:

```powershell
scoop update
scoop update sciscope-tui
```

## Local validation

The manifest is plain JSON and should parse before it is copied to the bucket:

```bash
python3 -m json.tool packaging/scoop/bucket/sciscope-tui.json >/dev/null
```

On a Windows machine with Scoop:

```powershell
scoop bucket add sciscope https://github.com/Timcai06/scoop-sciscope
scoop install sciscope-tui
sciscope-tui --version
sciscope-tui --demo
```

## Packaging boundary

This package installs only the terminal client. It does not install the Python
backend, PostgreSQL/pgvector, corpora, embeddings, or model assets. Those remain
source/Docker/cloud responsibilities.
