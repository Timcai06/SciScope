# SciScope Docs Index

This index is the maintained entry point for repository documents. It separates
current handoff material from background references so readers do not need to
guess which notes are still authoritative.

## Start Here

- [Project README](../README.md): product positioning, install paths, and common
  Makefile commands.
- [TUI README](../tui/README.md): terminal client usage, hosted backend defaults,
  local development, and troubleshooting.
- [Runbook](operations/runbook.md): daily development, validation, and failure recovery.
- [Project structure](architecture/project_structure.md): module ownership and architecture
  boundaries.

## User And Demo Guides

- [Golden verify-claim session](examples/golden_verify_claim_session.md):
  judge-facing agent transcript example.
- [Homebrew install notes](release/tui-homebrew.md): macOS package path.
- [Windows Scoop install notes](release/tui-windows.md): Windows package path.
- [npm install notes](release/tui-npm.md): cross-platform developer package path.

## Development And Architecture

- [Data and agent boundary](architecture/data-agent-boundary.md): data-governance and tool
  execution rules.
- [MCP integration](developer/mcp.md): MCP server/client entry points.
- [Product architecture note](architecture/2026-06-16-sciscope-product-architecture.md):
  background architecture record; prefer the current README, runbook, and
  project structure when they differ.
- [Hosted backend deployment](operations/deploy-hosted-backend.md): Render + Supabase demo
  deployment and release checks.

## Reports And Submission

- [Report optimization guide](reports/report-optimization.md): screenshot, narrative,
  and report-polish backlog.
- [Final submission checklist](reports/final_submission_checklist.md): final package and
  judge-facing consistency gates.
- [Submission manifest](reports/submission_manifest.md): whitelist package scope.

## Source Materials And Research Notes

- [Competition materials](competition/): original contest files.
- [Research notes](research/): external research writeups used as supporting
  material.
- [Visual assets](assets/): maintained document images.

## Removed Historical Areas

The old agent execution traces under `docs/superpowers/` and the superseded plan
archive under `plan/archive/` were intentionally removed. Current operational
truth lives in this index, the root README, the runbook, and Makefile targets.
