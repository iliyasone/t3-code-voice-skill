---
name: t3-voice
description: Speak your reply aloud in T3 Code — an audio player with the reply read word for word appears in the thread and starts by itself in the desktop app. Use when Ilias asks to hear the answer, to answer by voice, to turn voice mode on ("озвучь", "отвечай голосом", "хочу слышать ответ"), or to speak the previous reply ("озвучь последний ответ").
---

# t3-voice

Ilias often talks to agents by voice and wants to hear the reply too. This
skill turns a finished reply into speech (OpenAI TTS) and shows it as an
audio player above the reply via the T3 `html_render` tool. The audio is a
reading of the reply itself, never a summary or a paraphrase.

## Voice mode: speak every reply

Once Ilias asks for voice replies, keep doing it for every reply in the
thread until he says to stop.

1. Write the reply exactly as you would without this skill — same content,
   length, structure, tone, Markdown. Do not adapt it for listening.
2. Before sending it, pipe that exact text into the script (quoted heredoc,
   so `$` and backticks stay literal; pick another delimiter if the text
   contains a line `EOF`):

   ```bash
   ~/.agents/skills/t3-voice/speak.py <<'EOF'
   <the reply, verbatim>
   EOF
   ```

   stdout is a one-line HTML player; stderr shows timing.
3. Call `html_render` with `html` = that stdout line copied exactly,
   `title` = `🔊`, `height` = `80`. Skip `html_preview`.
4. Send the same text from step 2 as your final reply, character for
   character. The audio and the text must match.

If the script fails, send the reply as text anyway and add one line saying
what failed.

## Speak the previous reply

When Ilias asks to voice a reply that is already in the thread (Claude Code
only — it reads this session's transcript):

```bash
~/.agents/skills/t3-voice/speak.py --last
```

Then `html_render` as in step 3, and reply with a single short line.

## What gets spoken

Markdown markup is dropped (`**`, `#`, list markers, table pipes); code
blocks are skipped; URLs are read as "ссылка"; link text and inline code
are read as written. Words are never changed.

## Latency and limits

- The reply is cut into ~220-char pieces at sentence boundaries and all
  pieces are synthesized in parallel. Measured: ~1.3 s for one sentence,
  ~3 s for 560 chars, ~6 s for 1700 chars (vs ~9 s for 560 chars unsplit).
- The player autoplays only within 2 minutes of being made, so reopening
  an old thread stays silent. The desktop app (Electron) allows autoplay;
  a phone browser may block it — then Ilias presses ▶.
- Defaults: model `gpt-4o-mini-tts`, voice `coral`. Override with env
  `T3_VOICE_MODEL=tts-1` (about 1.5 s faster, flatter Russian) or
  `T3_VOICE_VOICE=<name>`.
- The OpenAI key is read from `~/.config/openai-voice/env`
  (`OPENAI_API_KEY=...`). Audio files live in `~/.cache/t3-voice/` and are
  deleted after 7 days.

## Why the audio file ends in .png

`html_render` inlines only local files that look like images (it checks the
first bytes). `speak.py` writes the MP3 behind an 8-byte PNG signature with
a `.png` name; T3 inlines it as a data URI and the player strips the
signature before playback. If a T3 update breaks the player, check that
inlining first. Source: /root/.t3/projects/t3-voice.
