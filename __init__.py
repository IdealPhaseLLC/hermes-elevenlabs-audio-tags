"""Hermes TTS provider plugin: audio-only ElevenLabs tag enrichment."""

try:  # Hermes loads user plugins as packages; pytest may load this file directly.
    from .provider import ElevenLabsAudioTagsProvider
except ImportError:  # pragma: no cover - direct-file compatibility only
    from provider import ElevenLabsAudioTagsProvider


AUXILIARY_TASK = "idealphase_elevenlabs_audio_tags"


def register(ctx):
    """Register the provider and a tag task that follows the user's main model."""
    ctx.register_auxiliary_task(
        key=AUXILIARY_TASK,
        display_name="IdealPhase ElevenLabs audio tags",
        description="Sparse audio-only delivery-tag enrichment for ElevenLabs",
        # No provider or model: Hermes "auto" uses the installer's main chat
        # model. An auxiliary.<key> override still wins.
        defaults={"timeout": 15},
    )
    ctx.register_tts_provider(ElevenLabsAudioTagsProvider(ctx.get_config))
