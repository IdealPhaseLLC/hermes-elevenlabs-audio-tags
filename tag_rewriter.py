"""Fail-closed, audio-only ElevenLabs delivery-tag enrichment."""

from __future__ import annotations

import logging
import re
import time
from typing import Callable, Optional

AUXILIARY_TASK = "idealphase_elevenlabs_audio_tags"
# A capacity miss used to fall through Hermes call_llm onto the main chat model
# and hold the voice note for the whole aux timeout. One short attempt, then
# the original line.
_TAG_ATTEMPT_TIMEOUT_S = 3.0

ALLOWED_TAGS = (
    "quietly", "warmly", "gently", "softly", "thoughtfully", "reassuringly",
    "excitedly", "solemnly", "playful", "amazed", "proud", "optimistic",
    "startled", "anxious", "vulnerable", "tired", "peaceful", "content",
    "curious", "trusting", "teasingly", "laughs", "giggles", "chuckles",
    "sighs", "gasps", "exhales", "moan", "whispers", "shouts",
    "a slow breath", "a small laugh", "short pause", "long pause",
)
_TAG_RE = re.compile(
    r"\[(?:" + "|".join(re.escape(tag) for tag in ALLOWED_TAGS) + r")\]",
    flags=re.IGNORECASE,
)
_ANY_BRACKET_RE = re.compile(r"\[[^\]\n]{1,80}\]")
_LOG = logging.getLogger(__name__)


def _route_for_observability() -> tuple[str, str]:
    """Return only non-secret configured route labels for a telemetry line."""
    try:
        from agent.auxiliary_client import _get_auxiliary_task_config

        config = _get_auxiliary_task_config(AUXILIARY_TASK)
        provider = str(config.get("provider") or "unknown").strip() or "unknown"
        model = str(config.get("model") or "unknown").strip() or "unknown"
        return provider, model
    except Exception:
        return "unknown", "unknown"


def _log_outcome(
    outcome: str,
    started_at: float,
    *,
    tag_count: int = 0,
    error_type: Optional[str] = None,
) -> None:
    """Log outcome/timing metadata only; never log spoken content or exception text."""
    provider, model = _route_for_observability()
    fields = [
        f"event=elevenlabs_tagger",
        f"outcome={outcome}",
        f"elapsed_ms={round((time.monotonic() - started_at) * 1000)}",
        f"tag_count={tag_count}",
        f"provider={provider}",
        f"model={model}",
        f"no_progress_cap_ms={round(_TAG_ATTEMPT_TIMEOUT_S * 1000)}",
    ]
    if error_type:
        fields.append(f"error_type={error_type}")
    _LOG.info(" ".join(fields))


def resolve_tag_limit(text: str, configured: object = None) -> int:
    """Allow sparse expression: two tags minimum, then one per 450 chars."""
    if configured is not None:
        try:
            return max(1, min(12, int(configured)))
        except (TypeError, ValueError):
            pass
    return min(6, max(2, (len(text) + 449) // 450))


def _normalise_without_tags(text: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", text)).strip()


def _extract_content(response: object) -> str:
    """Read the OpenAI-compatible auxiliary response shape defensively."""
    try:
        return str(response.choices[0].message.content or "")
    except (AttributeError, IndexError, TypeError):
        return ""


def _call_configured_tag_model(messages: list, *, temperature: float) -> object:
    """One attempt at the configured tag model. Never falls back to the chat model.

    ``agent.auxiliary_client.call_llm`` treats a capacity error as a reason to
    retry on the main agent model. That retry is the voice-note stall. This
    path resolves the task's own provider and makes a single completion.
    """
    from agent.auxiliary_client import _get_auxiliary_task_config, resolve_provider_client

    cfg = _get_auxiliary_task_config(AUXILIARY_TASK)
    provider = str(cfg.get("provider") or "").strip()
    model = str(cfg.get("model") or "").strip() or None
    if not provider or provider.lower() == "auto":
        raise RuntimeError("tagger requires an explicit auxiliary provider")
    try:
        configured_timeout = float(cfg.get("timeout") or _TAG_ATTEMPT_TIMEOUT_S)
    except (TypeError, ValueError):
        configured_timeout = _TAG_ATTEMPT_TIMEOUT_S
    timeout = min(configured_timeout, _TAG_ATTEMPT_TIMEOUT_S)
    client, resolved_model = resolve_provider_client(
        provider=provider, model=model or "", task=AUXILIARY_TASK,
    )
    wire_model = resolved_model or model
    if client is None or not wire_model:
        raise RuntimeError("tagger model unavailable")
    return client.chat.completions.create(
        model=wire_model,
        messages=messages,
        temperature=temperature,
        timeout=timeout,
        max_tokens=400,
    )


def rewrite_audio_script(
    text: str,
    *,
    max_tags: int,
    call_llm: Optional[Callable[..., object]] = None,
) -> str:
    """Return a safely tagged copy, or exactly the original text on any doubt.

    This function is intentionally fail-closed. It never changes the visible
    transcript; callers pass its result only to the TTS provider.
    """
    started_at = time.monotonic()
    transcript = text.strip()
    if not transcript:
        _log_outcome("skipped_empty", started_at)
        return text
    if _ANY_BRACKET_RE.search(transcript):
        _log_outcome("skipped_preformatted", started_at)
        return text

    def _default_caller(**kwargs):
        messages = kwargs.get("messages") or []
        return _call_configured_tag_model(
            list(messages),
            temperature=float(kwargs.get("temperature") or 0.2),
        )

    caller: Callable[..., object] = call_llm or _default_caller

    prompt = (
        "You add sparse ElevenLabs audio tags to a transcript. Tags are audio "
        "direction only and must never change the spoken words.\n\n"
        "Allowed tags: " + ", ".join(f"[{tag}]" for tag in ALLOWED_TAGS) + ".\n\n"
        "Rules:\n"
        "- Preserve every original spoken character, word order, and punctuation.\n"
        f"- Insert at most {max_tags} allowed tags, only where context clearly earns one.\n"
        "- Do not add tags to dry technical, factual, or safety-critical text.\n"
        "- Use playful tags only when the words are genuinely playful.\n"
        "- [moan] can sound adult or sexual. Use it only when the source text explicitly warrants that delivery; never infer it from ordinary warmth, humor, or appreciation.\n"
        "- Never add accents, character voices, or sound effects not already warranted by the words.\n"
        "- Do not add dialogue, narration, explanation, markdown, or code fences.\n"
        "- Return only the tagged TTS script."
    )
    try:
        response = caller(
            task=AUXILIARY_TASK,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"TRANSCRIPT TO TAG:\n{transcript}"},
            ],
            temperature=0.2,
        )
        tagged = _extract_content(response).strip()
        fenced = re.fullmatch(r"```(?:[A-Za-z0-9_-]+)?\s*(.*?)\s*```", tagged, flags=re.DOTALL)
        if fenced:
            tagged = fenced.group(1).strip()
        found_tags = _TAG_RE.findall(tagged)
        if (
            not tagged
            or len(found_tags) > max_tags
            or _ANY_BRACKET_RE.sub("", tagged) != _TAG_RE.sub("", tagged)
            or _normalise_without_tags(tagged) != _normalise_without_tags(transcript)
        ):
            _log_outcome("rejected", started_at, tag_count=len(found_tags))
            return text
        _log_outcome("tagged" if found_tags else "unchanged", started_at, tag_count=len(found_tags))
        return tagged
    except TimeoutError as exc:
        _log_outcome("timeout", started_at, error_type=type(exc).__name__)
        return text
    except Exception as exc:
        _log_outcome("error", started_at, error_type=type(exc).__name__)
        return text
