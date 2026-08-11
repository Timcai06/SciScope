# A04a historical failed attempts — superseded

> This note records pre-success attempts only. It is superseded by
> `deepseek_agent.response.json`, `deepseek_agent_stream.raw.sse`, and the
> current A04a report. The current scoped verdict is engineering `PASS` on the
> legacy full-size public-only Mac snapshot.

- `2026-08-10` real backend startup succeeded with the legacy local snapshot; `GET /readyz` returned all three checks `configured`.
- Local OpenAI-compatible model endpoint probe exited `7`; no local model was listening on the expected local model port.
- A mock-only rerun of `POST /api/agent` and `POST /api/agent/stream` returned HTTP `200`, but both stopped immediately with `stop_reason=no_model`, so no tool call, citation, or `structured_answer` was produced.
- A live cloud-backed `POST /api/agent` / `POST /api/agent/stream` capture was rejected by the execution safety reviewer because the request could forward the claim and retrieved SciScope corpus to the external DeepSeek API without explicit user approval.
- After explicit user authorization, two additional live attempts still remained blocked by the local execution environment:
  - sandboxed backend bind on requested port `8121` failed with `operation not permitted`
  - in-process real route execution reached `llm_step` but DeepSeek outbound failed with `urllib.error.URLError: [Errno 8] nodename nor servname provided, or not known`
- These blockers were subsequently cleared for the scoped DeepSeek live run. They do not represent the current A04a status.
