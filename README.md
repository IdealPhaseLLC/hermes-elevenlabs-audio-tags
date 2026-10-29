# IdealPhase ElevenLabs Audio Tags

A native Hermes TTS-provider plugin that preserves the visible chat transcript
and sends a separately enriched **audio-only** copy to ElevenLabs. It also
accepts an optional pronunciation dictionary ID in plugin settings — stock
Hermes ElevenLabs config has no equivalent knob. The plugin lives outside the
Hermes source tree so normal upstream updates do not overwrite this behavior.

## Purpose

Talking to an agent should feel like talking to a person, not reading a
transcript out loud. The words can already be warm, funny, or careful. Flat
speech throws that away.

This plugin is a small lift for that experience. It gives ElevenLabs a few
honest delivery cues, a laugh, a softer start, a pause, so the voice note
sounds more natural. It does not invent a performance the words did not earn,
and it does not change what you can read. The feeling belongs in the audio.

## Install

```bash
hermes plugins install IdealPhaseLLC/hermes-elevenlabs-audio-tags --enable
```

To pin an exact commit instead of floating on `main`:

```bash
hermes plugins install IdealPhaseLLC/hermes-elevenlabs-audio-tags \
  --ref <full-40-char-sha> --enable
```

Put `ELEVENLABS_API_KEY` in `~/.hermes/.env` (same key as stock ElevenLabs).
Then set plugin settings and `tts.provider` as below, and restart the gateway
(`hermes gateway restart` or `/restart` in chat).

## Safety contract

- The visible Telegram/chat transcript is never modified.
- The rewriter may only add tags from a small allowlist; it cannot add prose,
  accents, character voices, arbitrary effects, or change word order.
- Existing bracketed text is left untouched.
- The allowed tag count is length-scaled and bounded.
- Any malformed response, unknown bracketed tag, auxiliary failure, or
  word/punctuation change falls back to the original transcript. A capacity
  miss does not retry on the chat model.
- Every tagger path emits content-free observability: outcome, elapsed time,
  tag count, configured provider/model, effective no-progress window, and error
  class when applicable. It never logs the transcript, rewritten transcript, prompt,
  voice ID, exception message, or credentials.

## Disclosure

The text Hermes has already prepared for speech, the voice ID, the model ID,
and any pronunciation-dictionary locator you set are sent to
`api.elevenlabs.io` with your `ELEVENLABS_API_KEY`. That call is billed to
your ElevenLabs account. Audio is written only to the path Hermes requests.

When automatic tags are on, the untagged transcript is also sent to the model
configured for `auxiliary.idealphase_elevenlabs_audio_tags`. If you did not
pin one, that is your normal chat model. The tagger uses that reply only to
add delivery tags. The visible chat text is not changed.

This plugin does not store the key, does not phone home, and does not log the
transcript, the rewrite, the prompt, the voice ID, or the key.

## Hermes integration

The plugin registers the non-shadowing provider name:

```text
idealphase-elevenlabs-audio-tags
```

Hermes built-in providers cannot be overridden, by design, so this plugin uses
its own provider name rather than monkey-patching built-in `elevenlabs`.

It expects the normal `ELEVENLABS_API_KEY` environment/config secret. Secrets
are not stored in this repository or plugin settings.

After installing and enabling the plugin, configure it under its namespaced
settings and select the provider:

```yaml
plugins:
  entries:
    idealphase-elevenlabs-audio-tags:
      settings:
        # Example voice. Use your own ElevenLabs voice ID if you want a different one.
        voice_id: EST9Ui6982FZPSi7gCHi
        model_id: eleven_v4
        auto_speech_tags: true
        # Optional hard ceiling; default scales from 2 to 6 based on length.
        # max_auto_speech_tags: 6
        # Optional. Site dictionaries do not auto-apply to API TTS.
        # Omit or leave blank to send no locator. For eleven_v4, use alias
        # rules rather than IPA/CMU phonemes.
        # pronunciation_dictionary_id: YOUR_DICTIONARY_ID
        # pronunciation_dictionary_version_id:  # optional; latest if omitted

tts:
  provider: idealphase-elevenlabs-audio-tags
```

Pronunciation dictionaries are opt-in. If `pronunciation_dictionary_id` is
missing or blank, convert() is unchanged. If set, the plugin sends that
locator on every ElevenLabs request (optional `pronunciation_dictionary_version_id`,
otherwise latest). Creating a dictionary in the ElevenLabs UI does **not**
apply it automatically; the API needs the locator. Phoneme/IPA rules only
apply on `eleven_flash_v2` / `eleven_v3` — for `eleven_v4` use alias rules.

The plugin marks itself `voice_compatible`, so Hermes may convert its audio to
Telegram's Opus voice-bubble format as it does for other compatible providers.

### Tag model

Tag enrichment is its own Hermes auxiliary task,
`auxiliary.idealphase_elevenlabs_audio_tags`. Leave provider and model unset
and Hermes uses your normal chat model. A fresh install does not ask for a
second login.

Pin a smaller, faster model if you send a lot of voice notes. Tagging is a
separate call, and a slow reasoning model can miss the 3-second window. Speech
still goes out. It just goes out without tags. Pick the slot in `hermes setup`
or `hermes model`, or set it directly:

```yaml
auxiliary:
  idealphase_elevenlabs_audio_tags:
    provider: openai-codex
    model: gpt-5.4-mini
```

That block is optional. It is an example of a cheaper pin, not a requirement.

## Hear the difference

After install, say this line and listen to the voice note:

```text
Did you like that joke? I'm SO funny
```

The visible chat text stays exactly that. The audio may not. On three live runs the tagger accepted two different rewrites, and either one is a normal result:

- `[playful] Did you like that joke? I'm SO funny`
- `Did you like that joke? [laughs] I'm SO funny`

It can also come back unchanged. A slow model, a rejected rewrite, or a timeout speaks the plain line. Do not expect one exact tag every time.

These clips are the same words, rendered with the tagger bypassed so the script is exactly what the label says. Your voice will differ. The delivery change is the thing to listen for. Press play on the page. You do not need to download the file.

No tags

https://github.com/user-attachments/assets/8cf527cb-89b6-480b-a6df-5065989f5f0e

`[laughs]` before "I'm SO funny"

https://github.com/user-attachments/assets/9370a5a9-6875-42c3-9a0f-87253c515952

`[playful]` from the start

https://github.com/user-attachments/assets/1a415ec9-aeeb-41e4-8a65-94c0adfe1851

Then check the log for a content-free tagger line:

```text
event=elevenlabs_tagger outcome=tagged elapsed_ms=2125 tag_count=1 provider=your-provider model=your-model no_progress_cap_ms=3000
```

`outcome=tagged` and `tag_count` greater than zero means a tag was inserted. `outcome=unchanged` means the model returned the original line. `rejected`, `timeout`, and `error` mean the spoken audio is the original line. The line never includes the transcript, the rewrite, the prompt, or the voice ID.

The configured `timeout` may lower the tagger's no-progress deadline, but cannot
raise it: the plugin makes one attempt with an effective **3-second
no-progress window**. A substantive streamed response re-arms that window, so
`elapsed_ms` may exceed 3000 on a healthy response that keeps making progress.
Inspect content-free `event=elevenlabs_tagger` log lines when deciding whether
to tune it; do not infer a timeout merely because a note has no tags.

## Local checks

From the repository root. Pytest is the only install these tests need. If
Hermes is importable, the suite uses it. If it is not, the tests still run
against this plugin's own behavior. That does not prove the plugin loads
inside Hermes.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

On a machine that has Hermes, also run:

```bash
hermes plugins doctor . --ci
```

## Deliberate non-goals

- No generic text rewriting.
- No hidden mutation of session history, messages, or markdown.
- No monkey-patching of Hermes internals.
