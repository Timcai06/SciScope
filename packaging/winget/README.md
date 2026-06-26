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
git tag v0.1.2
git push origin v0.1.2
```

After GitHub Actions succeeds, confirm the release contains:

```text
sciscope-tui_windows_amd64.zip
sciscope-tui_windows_arm64.zip
checksums.txt
```

## Fill the manifest

Copy the template directory to a temporary `winget-pkgs` clone and replace:

- `PackageVersion` with the release version without the leading `v`, for
  example `0.1.2`.
- `InstallerSha256` with the release asset SHA256 values.

The release URL pattern is:

```text
https://github.com/Timcai06/SciScope/releases/download/v0.1.2/sciscope-tui_windows_amd64.zip
https://github.com/Timcai06/SciScope/releases/download/v0.1.2/sciscope-tui_windows_arm64.zip
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
