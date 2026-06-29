# SciScope TUI npm package

This package installs the SciScope Go terminal client through npm. It downloads
the matching GitHub Release archive during install, then exposes the
`sciscope-tui` command.

## Install And Run

```bash
npm install -g sciscope-tui
sciscope-tui
```

Offline demo:

```bash
sciscope-tui --demo
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

## Supported Platforms

- macOS arm64 / x64
- Windows arm64 / x64
- Linux arm64 / x64

## Maintainer Notes

The wrapper expects GitHub Release assets named like:

```text
sciscope-tui_darwin_arm64.tar.gz
sciscope-tui_darwin_amd64.tar.gz
sciscope-tui_linux_arm64.tar.gz
sciscope-tui_linux_amd64.tar.gz
sciscope-tui_windows_arm64.zip
sciscope-tui_windows_amd64.zip
```

Publish from this directory after the matching GitHub Release exists:

```bash
npm publish
```

Set `SCISCOPE_TUI_SKIP_DOWNLOAD=1` for dry-run package checks, or
`SCISCOPE_TUI_RELEASE_BASE` to override the release download base URL.
