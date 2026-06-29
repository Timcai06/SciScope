# Contributing to SciScope

SciScope is an open-source research-agent project for evidence-grounded
scientific literature analysis. Contributions are welcome across the Python
backend, data/RAG pipeline, Go terminal client, packaging, documentation, tests,
and report workflows.

## Good First Contribution Areas

- Documentation fixes in `README.md`, `docs/`, and `tui/README.md`.
- TUI usability improvements in `tui/`.
- Backend tests under `backend/tests/`.
- Data and retrieval pipeline improvements under `src/` and `backend/app/services/`.
- Packaging fixes for npm, Homebrew, Scoop, and GitHub Releases under
  `packaging/`, `tui/.goreleaser.yaml`, and `.github/workflows/`.

## Development Setup

```bash
make install
make backend
```

For the terminal client:

```bash
make tui-demo
make tui-doctor
```

For package checks:

```bash
make npm-package-smoke
make npm-package-pack
```

## Before Opening a Pull Request

Run the smallest verification loop that matches your change:

- Backend or data pipeline: `make test-backend`
- TUI: `cd tui && go test ./...`
- npm wrapper: `make npm-package-smoke && make npm-package-pack`
- Documentation: check Markdown links and make sure examples still match the
  current hosted/local architecture.

If a full verification pass is too expensive for the change, explain what you
ran and what remains unverified in the pull request.

## Project Boundaries

- The Python backend and data/RAG pipeline own retrieval, evidence grounding,
  tools, and model assets.
- The Go TUI is a terminal client and consumes backend SSE events; it should not
  duplicate backend reasoning logic.
- Package-manager releases install only the TUI client. They do not install the
  Python backend, PostgreSQL/pgvector, corpora, embeddings, or model assets.

## License

By contributing, you agree that your contribution is licensed under the Apache
License 2.0.
