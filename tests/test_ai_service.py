import pytest

from app.services import ai_service


@pytest.mark.asyncio
async def test_ai_service_uses_bedrock_fallback(monkeypatch):
    """ai_service should use bedrock invoke_with_fallback."""
    called_with = {}

    async def mock_invoke_with_fallback(system_prompt, messages, **kwargs):
        called_with["system_prompt"] = system_prompt
        called_with["messages"] = messages
        return "mock response", "zai.glm-5"

    monkeypatch.setattr("app.providers.bedrock.invoke_with_fallback", mock_invoke_with_fallback)

    result = await ai_service.generate_response("sys", "hello", [])
    assert result == "mock response"
    assert called_with["system_prompt"] == "sys"


@pytest.mark.asyncio
async def test_ai_service_passes_history(monkeypatch):
    """ai_service should pass history to bedrock."""
    captured = {}

    async def mock_invoke_with_fallback(system_prompt, messages, **kwargs):
        captured["messages"] = messages
        return "ok", "zai.glm-5"

    monkeypatch.setattr("app.providers.bedrock.invoke_with_fallback", mock_invoke_with_fallback)

    history = [{"role": "customer", "content": "hi"}, {"role": "ai", "content": "hello"}]
    await ai_service.generate_response("sys", "bye", history)

    # Messages should have been built with _build_converse_messages
    assert len(captured["messages"]) == 3  # 2 history + 1 new
    assert captured["messages"][-1]["role"] == "user"
