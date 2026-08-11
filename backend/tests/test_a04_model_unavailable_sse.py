from fastapi.testclient import TestClient

from backend.app.main import create_app


def _client(monkeypatch):
    monkeypatch.setenv("SCISCOPE_ENV", "local")
    monkeypatch.setenv("SCISCOPE_USE_MOCK_LLM", "false")
    monkeypatch.setenv("SCISCOPE_LLM_PROVIDER", "vllm")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://model-unavailable.invalid/v1")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def test_agent_stream_surfaces_model_unavailable_as_ordered_sse(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.post(
            "/api/agent/stream",
            json={"question": "请核查检索增强生成是否能降低大语言模型幻觉风险"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert '"type": "final"' in body
    assert '"stop_reason": "no_model"' in body
    assert "本地大模型未运行" in body
    assert ":8001" not in body
    assert "data: [DONE]" in body
    frames = [line.removeprefix("data: ") for line in body.splitlines() if line.startswith("data: ")]
    assert len(frames) == 2
    assert '"type": "final"' in frames[0]
    assert frames[1] == "[DONE]"


def test_agent_aggregate_surfaces_model_unavailable_without_structured_success(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.post(
            "/api/agent",
            json={"question": "请核查检索增强生成是否能降低大语言模型幻觉风险"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"].startswith("本地大模型未运行")
    assert ":8001" not in payload["answer"]
    assert payload["stop_reason"] == "no_model"
    assert payload["tools_used"] == []
    assert payload["model"] is None
    assert "structured_answer" not in payload
