import logging
from types import SimpleNamespace

import tag_rewriter
from tag_rewriter import resolve_tag_limit, rewrite_audio_script


def response(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_accepts_allowlisted_tags_without_changing_spoken_words():
    source = "I did not know how to say goodbye, but I am grateful we had this time."
    tagged = "[quietly] I did not know how to say goodbye, but I am grateful we had this time. [a slow breath]"
    captured = {}

    def fake_call(**kwargs):
        captured.update(kwargs)
        return response(tagged)

    assert rewrite_audio_script(source, max_tags=2, call_llm=fake_call) == tagged
    assert captured["task"] == "idealphase_elevenlabs_audio_tags"


def test_fails_closed_when_spoken_words_change():
    source = "The deployment is ready."
    changed = "[warmly] The deployment is completely ready."
    assert rewrite_audio_script(source, max_tags=2, call_llm=lambda **_: response(changed)) == source


def test_rejects_freeform_and_respects_existing_brackets():
    source = "The build passed [42 tests]."
    assert rewrite_audio_script(source, max_tags=2, call_llm=lambda **_: response(source)) == source
    plain = "That was unexpected, but it made me smile."
    invalid = "[strong pirate accent] That was unexpected, but it made me smile."
    assert rewrite_audio_script(plain, max_tags=2, call_llm=lambda **_: response(invalid)) == plain


def test_capacity_miss_speaks_the_original_line_without_a_second_model():
    source = "To get to the other side."
    calls = {"n": 0}

    def boom(**kwargs):
        calls["n"] += 1
        raise RuntimeError("The model is currently at capacity due to high demand")

    assert rewrite_audio_script(source, max_tags=2, call_llm=boom) == source
    assert calls["n"] == 1


def test_default_path_uses_one_configured_attempt(monkeypatch):
    import tag_rewriter

    source = "To get to the other side."
    seen = {}

    def once(messages, *, temperature):
        seen["messages"] = messages
        seen["temperature"] = temperature
        raise RuntimeError("at capacity")

    monkeypatch.setattr(tag_rewriter, "_call_configured_tag_model", once)
    assert rewrite_audio_script(source, max_tags=2) == source
    assert seen["temperature"] == 0.2
    assert any("TRANSCRIPT TO TAG:" in str(item.get("content")) for item in seen["messages"])
    system_prompt = next(
        item["content"] for item in seen["messages"] if item.get("role") == "system"
    )
    assert "[moan] can sound adult or sexual." in system_prompt
    assert "never infer it from ordinary warmth, humor, or appreciation." in system_prompt
    assert "Never add accents, character voices, or sound effects not already warranted by the words." in system_prompt


def test_configured_attempt_does_not_call_hermes_fallback(monkeypatch):
    import tag_rewriter

    class FakeCompletions:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            raise RuntimeError("at capacity")

    class FakeClient:
        def __init__(self):
            self.chat = type("Chat", (), {})()
            self.chat.completions = FakeCompletions()

    client = FakeClient()

    def resolve_provider_client(**kwargs):
        assert kwargs["provider"] == "xai-oauth"
        assert kwargs["model"] == "grok-4.20-0309-non-reasoning"
        return client, kwargs["model"]

    monkeypatch.setattr(
        "agent.auxiliary_client._get_auxiliary_task_config",
        lambda task: {
            "provider": "xai-oauth",
            "model": "grok-4.20-0309-non-reasoning",
            "timeout": 15,
        },
    )
    monkeypatch.setattr(
        "agent.auxiliary_client.resolve_provider_client",
        resolve_provider_client,
    )
    monkeypatch.setattr(
        "agent.auxiliary_client.call_llm",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("call_llm fallback path used")),
    )

    try:
        tag_rewriter._call_configured_tag_model([{"role": "user", "content": "hi"}], temperature=0.2)
    except RuntimeError as exc:
        assert "at capacity" in str(exc)
    else:
        raise AssertionError("capacity error should surface to the fail-closed caller")

    assert len(client.chat.completions.calls) == 1
    assert client.chat.completions.calls[0]["timeout"] == 3.0
    assert client.chat.completions.calls[0]["model"] == "grok-4.20-0309-non-reasoning"


def test_length_scaled_limit_is_bounded():
    assert resolve_tag_limit("x" * 100) == 2
    assert resolve_tag_limit("x" * 1500) == 4
    assert resolve_tag_limit("x" * 9000) == 6
    assert resolve_tag_limit("x" * 9000, 99) == 12


def test_logs_tagged_outcome_without_spoken_content(monkeypatch, caplog):
    source = "PRIVATE SPEECH: I am so glad this worked."
    tagged = "[warmly] PRIVATE SPEECH: I am so glad this worked."
    monkeypatch.setattr(tag_rewriter, "_route_for_observability", lambda: ("xai-oauth", "grok-test"))

    with caplog.at_level(logging.INFO, logger="tag_rewriter"):
        assert rewrite_audio_script(source, max_tags=2, call_llm=lambda **_: response(tagged)) == tagged

    record = next(item.message for item in caplog.records if "event=elevenlabs_tagger" in item.message)
    assert "outcome=tagged" in record
    assert "tag_count=1" in record
    assert "provider=xai-oauth" in record
    assert "model=grok-test" in record
    assert "no_progress_cap_ms=3000" in record
    assert source not in record
    assert tagged not in record


def test_logs_timeout_type_without_exception_or_spoken_content(monkeypatch, caplog):
    source = "PRIVATE SPEECH: Do not log this sentence."
    monkeypatch.setattr(tag_rewriter, "_route_for_observability", lambda: ("xai-oauth", "grok-test"))

    def timed_out(**_kwargs):
        raise TimeoutError("PRIVATE ERROR: Do not log this either.")

    with caplog.at_level(logging.INFO, logger="tag_rewriter"):
        assert rewrite_audio_script(source, max_tags=2, call_llm=timed_out) == source

    record = next(item.message for item in caplog.records if "event=elevenlabs_tagger" in item.message)
    assert "outcome=timeout" in record
    assert "error_type=TimeoutError" in record
    assert source not in record
    assert "PRIVATE ERROR" not in record
