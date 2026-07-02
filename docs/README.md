# SciScope Docs Index

This index separates **living product** material (evolves with the codebase) from
**frozen delivery** material (competition submission artifacts — done, do not edit
as if current). When they differ, the living zone and the root README win.

---

## 一、活的产品（Living Product — 会随代码演进）

### 方向：为什么 & 往哪走

- [项目方针与目标](project/): SciScope 的魂与北极星。
  - [Charter](project/charter.md): evidence-grounded soul, protocol-first,
    evidence-backend positioning, the "should we build it" three questions.
  - [Roadmap](project/roadmap.md): the `[n]` relatedness→entailment north star
    and the first concrete step.

### Start Here

- [Project README](../README.md): product positioning, install paths, common
  Makefile commands.
- [TUI README](../tui/README.md): terminal client usage, hosted backend defaults,
  local development, troubleshooting.
- [Runbook](operations/runbook.md): daily development, validation, failure recovery.
- [Project structure](architecture/project_structure.md): module ownership and
  architecture boundaries.

### Development And Architecture

- [Data and agent boundary](architecture/data-agent-boundary.md): data-governance
  and tool execution rules.
- [MCP integration](developer/mcp.md): MCP server/client entry points — the
  evidence-backend front door.
- [Hosted backend deployment](operations/deploy-hosted-backend.md): Render +
  Supabase demo deployment and release checks.

### User And Release Guides

- [Download and release index](release/README.md): npm, Homebrew, Scoop, and
  GitHub Release paths in one place.
- [Homebrew install notes](release/tui-homebrew.md) ·
  [Windows Scoop notes](release/tui-windows.md) ·
  [npm notes](release/tui-npm.md).

### Contribution Standards

- [Contributing](../CONTRIBUTING.md) ·
  [Security policy](../SECURITY.md) ·
  [Code of conduct](../CODE_OF_CONDUCT.md)

---

## 二、交付存档（Frozen Delivery — 竞赛提交物，勿当现行真相）

These are the competition submission record. They are complete and frozen; keep
them for reproducibility and judging, but do not treat them as the current
product roadmap.

- Judge index: root [`交付说明.md`](../交付说明.md).
- [Report optimization guide](reports/report-optimization.md): screenshot,
  narrative, and report-polish backlog (submission-era).
- [Final submission checklist](reports/final_submission_checklist.md): final
  package and judge-facing consistency gates.
- [Submission manifest](reports/submission_manifest.md): whitelist package scope.
- [Golden verify-claim session](examples/golden_verify_claim_session.md):
  judge-facing agent transcript example.
- [Competition materials](competition/): original contest files.
- [Research notes](research/): external research writeups used as supporting
  material during the submission.
- [Product architecture note](architecture/2026-06-16-sciscope-product-architecture.md):
  **historical** architecture record; contains aspirational goals (机会生成器 /
  交互式 Web 工作台) that are NOT the current delivery. Prefer the living zone
  above, the README, runbook, and project structure when they differ.

### Planning archive

- [`../plan/`](../plan/): execution planning tree. The forward-looking roadmap now
  lives in [project/roadmap.md](project/roadmap.md); `plan/` is kept as the
  build/delivery history and current-state snapshot.

---

## Removed Historical Areas

The old agent execution traces under `docs/superpowers/` and the superseded plan
archive under `plan/archive/` were intentionally removed. Current operational
truth lives in this index, the root README, the runbook, and Makefile targets.
