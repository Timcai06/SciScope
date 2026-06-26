# SciScope TUI winget packaging

Goal:

```powershell
winget install SciScope.SciScopeTUI
```

`winget` distribution depends on a published GitHub Release that contains the
Windows zip archive built by GoReleaser. The current package boundary is the Go
terminal client only; the Python backend, PostgreSQL/pgvector service, corpus,
and model assets are not installed by winget.

## Release prerequisite

The release workflow is tag-driven:

```bash
git tag v0.1.1
git push origin v0.1.1
```

After GitHub Actions succeeds, confirm the release contains:

```text
sciscope-tui_windows_amd64.zip
sciscope-tui_windows_arm64.zip
checksums.txt
```

## Fill the manifest

Copy the template directory to a temporary `winget-pkgs` clone and replace:

- `__VERSION__` with the release version without the leading `v`, for example
  `0.1.1`.
- `__AMD64_SHA256__` with the SHA256 of `sciscope-tui_windows_amd64.zip`.
- `__ARM64_SHA256__` with the SHA256 of `sciscope-tui_windows_arm64.zip`.

The release URL pattern is:

```text
https://github.com/Timcai06/SciScope/releases/download/v__VERSION__/sciscope-tui_windows_amd64.zip
https://github.com/Timcai06/SciScope/releases/download/v__VERSION__/sciscope-tui_windows_arm64.zip
```

## Submit to winget-pkgs

Use either `wingetcreate` or a pull request to
`https://github.com/microsoft/winget-pkgs`.

Expected install command after approval:

```powershell
winget install SciScope.SciScopeTUI
```

Runtime examples:

```powershell
sciscope-tui --demo
$env:SCISCOPE_BACKEND="https://api.sciscope.example"
sciscope-tui
```

