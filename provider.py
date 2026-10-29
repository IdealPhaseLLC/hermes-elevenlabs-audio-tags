"""A self-contained, non-shadowing ElevenLabs TTS provider for Hermes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Optional

from agent.tts_provider import TTSProvider

try:  # Hermes loads user plugins as packages; direct-file tooling does not.
    from .tag_rewriter import resolve_tag_limit, rewrite_audio_script
except ImportError:  # pragma: no cover - direct-file compatibility only
    from tag_rewriter import resolve_tag_limit, rewrite_audio_script

DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"
DEFAULT_MODEL_ID = "eleven_multilingual_v2"


def _elevenlabs_api_key() -> str:
    """Read the ElevenLabs key through Hermes when it is installed.

    Catalog rule: secrets come from ``agent.secret_scope.get_secret``, which
    honors the active profile. A direct ``os.environ`` read is only the
    fallback for tests and tooling that import this file without Hermes.
    """
    try:
        from agent.secret_scope import get_secret
    except ImportError:
        return str(os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    return str(get_secret("ELEVENLABS_API_KEY", "") or "").strip()


def pronunciation_dictionary_locators(get_config: Callable[[str, Any], Any]) -> Optional[list[dict[str, str]]]:
    """Return API locators when a dictionary ID is configured; otherwise None.

    Empty/whitespace IDs are treated as unset so the request stays identical to
    today's no-dictionary convert() call. version_id is optional; omit it to use
    the dictionary's latest version.
    """
    dictionary_id = str(get_config("pronunciation_dictionary_id", "") or "").strip()
    if not dictionary_id:
        return None
    locator = {"pronunciation_dictionary_id": dictionary_id}
    version_id = str(get_config("pronunciation_dictionary_version_id", "") or "").strip()
    if version_id:
        locator["version_id"] = version_id
    return [locator]


class ElevenLabsAudioTagsProvider(TTSProvider):
    """ElevenLabs provider that enriches only the audio-bound script.

    Configuration is intentionally plugin-owned under
    ``plugins.entries.idealphase-elevenlabs-audio-tags.settings``. The API key
    remains in ``ELEVENLABS_API_KEY``; it is never copied into plugin config.
    """

    def __init__(self, get_config: Callable[[str, Any], Any]):
        self._get_config = get_config

    @property
    def name(self) -> str:
        return "idealphase-elevenlabs-audio-tags"

    @property
    def display_name(self) -> str:
        return "IdealPhase ElevenLabs Audio Tags"

    @property
    def voice_compatible(self) -> bool:
        return True

    def is_available(self) -> bool:
        try:
            import elevenlabs  # noqa: F401
        except ImportError:
            return False
        try:
            return bool(_elevenlabs_api_key())
        except Exception:
            return False

    def get_setup_schema(self) -> dict[str, Any]:
        return {
            "name": self.display_name,
            "badge": "private",
            "tag": "ElevenLabs with safe audio-only delivery tags",
            "env_vars": [{
                "key": "ELEVENLABS_API_KEY",
                "prompt": "ElevenLabs API key",
                "url": "https://elevenlabs.io/app/settings/api-keys",
            }],
        }

    def synthesize(
        self,
        text: str,
        output_path: str,
        *,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        speed: Optional[float] = None,
        format: str = "mp3",
        timeout: Optional[float] = None,
        **extra: Any,
    ) -> str:
        del speed, format, extra  # ElevenLabs voice/model settings are explicit below.
        api_key = _elevenlabs_api_key()
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY is not configured")

        voice_id = voice or self._get_config("voice_id", DEFAULT_VOICE_ID)
        model_id = model or self._get_config("model_id", DEFAULT_MODEL_ID)
        enabled = bool(self._get_config("auto_speech_tags", True))
        audio_text = text
        if enabled:
            audio_text = rewrite_audio_script(
                text,
                max_tags=resolve_tag_limit(text, self._get_config("max_auto_speech_tags", None)),
            )

        from elevenlabs.client import ElevenLabs

        output_format = "opus_48000_64" if output_path.endswith(".ogg") else "mp3_44100_128"
        convert_kwargs: dict[str, Any] = {
            "text": audio_text,
            "voice_id": str(voice_id),
            "model_id": str(model_id),
            "output_format": output_format,
        }
        locators = pronunciation_dictionary_locators(self._get_config)
        if locators:
            convert_kwargs["pronunciation_dictionary_locators"] = locators
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if timeout is not None:
            client_kwargs["timeout"] = float(timeout)
        audio = ElevenLabs(**client_kwargs).text_to_speech.convert(**convert_kwargs)
        path = Path(output_path)
        with path.open("wb") as handle:
            for chunk in audio:
                handle.write(chunk)
        return str(path)
