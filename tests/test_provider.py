import sys
from types import ModuleType

import provider as provider_module


def test_provider_sends_only_audio_copy_to_elevenlabs(tmp_path, monkeypatch):
    captured = {}

    class FakeSpeech:
        def convert(self, **kwargs):
            captured.update(kwargs)
            return [b"audio"]

    class FakeElevenLabs:
        def __init__(self, *, api_key):
            captured["api_key"] = api_key
            self.text_to_speech = FakeSpeech()

    elevenlabs = ModuleType("elevenlabs")
    client = ModuleType("elevenlabs.client")
    client.ElevenLabs = FakeElevenLabs
    monkeypatch.setitem(sys.modules, "elevenlabs", elevenlabs)
    monkeypatch.setitem(sys.modules, "elevenlabs.client", client)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(provider_module, "rewrite_audio_script", lambda text, **_: f"[softly] {text}")

    settings = {
        "voice_id": "voice-id",
        "model_id": "eleven_v4",
        "auto_speech_tags": True,
    }
    service = provider_module.ElevenLabsAudioTagsProvider(lambda key, default=None: settings.get(key, default))
    output = tmp_path / "out.mp3"
    assert service.synthesize("Hello there.", str(output)) == str(output)

    assert output.read_bytes() == b"audio"
    assert captured["api_key"] == "test-key"
    assert captured["text"] == "[softly] Hello there."
    assert captured["voice_id"] == "voice-id"
    assert captured["model_id"] == "eleven_v4"
    assert "pronunciation_dictionary_locators" not in captured


def _synthesize(tmp_path, monkeypatch, settings):
    captured = {}

    class FakeSpeech:
        def convert(self, **kwargs):
            captured.update(kwargs)
            return [b"audio"]

    class FakeElevenLabs:
        def __init__(self, *, api_key):
            captured["api_key"] = api_key
            self.text_to_speech = FakeSpeech()

    elevenlabs = ModuleType("elevenlabs")
    client = ModuleType("elevenlabs.client")
    client.ElevenLabs = FakeElevenLabs
    monkeypatch.setitem(sys.modules, "elevenlabs", elevenlabs)
    monkeypatch.setitem(sys.modules, "elevenlabs.client", client)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(provider_module, "rewrite_audio_script", lambda text, **_: text)

    service = provider_module.ElevenLabsAudioTagsProvider(
        lambda key, default=None: settings.get(key, default)
    )
    output = tmp_path / "out.mp3"
    assert service.synthesize("Hello there.", str(output)) == str(output)
    return captured


def test_configured_dictionary_id_is_sent_to_elevenlabs(tmp_path, monkeypatch):
    captured = _synthesize(tmp_path, monkeypatch, {
        "voice_id": "voice-id",
        "model_id": "eleven_v4",
        "auto_speech_tags": False,
        "pronunciation_dictionary_id": "dict_test_id",
    })
    assert captured["pronunciation_dictionary_locators"] == [
        {"pronunciation_dictionary_id": "dict_test_id"}
    ]


def test_optional_dictionary_version_is_included_when_set(tmp_path, monkeypatch):
    captured = _synthesize(tmp_path, monkeypatch, {
        "voice_id": "voice-id",
        "model_id": "eleven_v4",
        "auto_speech_tags": False,
        "pronunciation_dictionary_id": "dict_test_id",
        "pronunciation_dictionary_version_id": "version_test_id",
    })
    assert captured["pronunciation_dictionary_locators"] == [{
        "pronunciation_dictionary_id": "dict_test_id",
        "version_id": "version_test_id",
    }]


def test_blank_dictionary_id_does_not_send_locators():
    settings = {"pronunciation_dictionary_id": "  ", "pronunciation_dictionary_version_id": "abc"}
    assert provider_module.pronunciation_dictionary_locators(
        lambda key, default=None: settings.get(key, default)
    ) is None


def test_explicit_timeout_is_passed_to_the_elevenlabs_client(tmp_path, monkeypatch):
    captured = {}

    class FakeSpeech:
        def convert(self, **kwargs):
            del kwargs
            return [b"audio"]

    class FakeElevenLabs:
        def __init__(self, *, api_key, timeout=None):
            captured["api_key"] = api_key
            captured["timeout"] = timeout
            self.text_to_speech = FakeSpeech()

    elevenlabs = ModuleType("elevenlabs")
    client = ModuleType("elevenlabs.client")
    client.ElevenLabs = FakeElevenLabs
    monkeypatch.setitem(sys.modules, "elevenlabs", elevenlabs)
    monkeypatch.setitem(sys.modules, "elevenlabs.client", client)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(provider_module, "rewrite_audio_script", lambda text, **_: text)

    service = provider_module.ElevenLabsAudioTagsProvider(lambda key, default=None: default)
    output = tmp_path / "out.mp3"
    assert service.synthesize("Hello there.", str(output), timeout=180) == str(output)
    assert captured["timeout"] == 180.0
