# SciScope TUI Windows Release Guide

Windows distribution has three channels:

1. GitHub Release zip: immediate fallback and source of truth.
2. Scoop bucket: preferred Windows package-manager path for fast iteration.
3. winget: official ecosystem path, subject to Microsoft moderator review.

## Recommended user path

Use Scoop when the user wants a terminal package-manager workflow:

```powershell
scoop bucket add sciscope https://github.com/Timcai06/scoop-sciscope
scoop install sciscope-tui
sciscope-tui
```

Use GitHub Release when Scoop is not available:

```powershell
# Download the matching asset from:
# https://github.com/Timcai06/SciScope/releases
#
# Then unzip and run:
.\sciscope-tui.exe
```

Use winget only after the Microsoft PR has been merged:

```powershell
winget install SciScope.SciScopeTUI
```

## Maintainer release checklist

From the SciScope repository:

```bash
cd tui
goreleaser check
goreleaser release --snapshot --clean
cd ..
```

For a real release:

```bash
git tag v0.2.1
git push origin v0.2.1
```

After the release workflow completes, verify the Windows assets and checksums:

```text
sciscope-tui_windows_amd64.zip
sciscope-tui_windows_arm64.zip
checksums.txt
```

Then update the Scoop bucket manifest in `Timcai06/scoop-sciscope`:

```text
bucket/sciscope-tui.json
```

The source template lives in:

```text
packaging/scoop/bucket/sciscope-tui.json
```

## Runtime boundary

The Windows package installs only `sciscope-tui.exe`. The backend and data layer
are intentionally separate:

- product deployment: run `sciscope-tui` to use the hosted backend compiled into
  the release
- local development: run the SciScope backend from source, then set
  `SCISCOPE_BACKEND` to that local backend URL
- reproducibility: use the project reports and source pipeline, not the TUI
  package, to rebuild the research artifacts

Developer local backend override:

```powershell
$env:SCISCOPE_BACKEND="http://127.0.0.1:8000"
sciscope-tui
```
