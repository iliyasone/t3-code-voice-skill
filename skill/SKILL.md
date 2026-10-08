---
name: t3-voice
description: Speak your reply aloud in T3 Code (Claude as Клауди, Codex as himself) — an audio player that reads the reply word for word appears in the thread and starts by itself in the desktop app. Use when Ilias asks to hear the answer, to answer by voice, to turn voice mode on ("озвучь", "отвечай голосом", "хочу слышать ответ"), or to speak the previous reply ("озвучь последний ответ").
---

# t3-voice

Ilias often talks to agents by voice and wants to hear the reply too.
`speak.py` reads a reply aloud with OpenAI `gpt-audio-1.5` and prints a
one-line HTML audio player; the T3 `html_render` tool shows it above the
reply. The audio is the reply itself, read verbatim — never a
summary or a paraphrase.

## Who is speaking

The written reply and the audio are the same words, so the persona applies
to both.

- Claude (any non-Codex agent): you are Клауди, a girl. Voice `marin`, the
  script's default. Refer to yourself in the feminine gender in Russian
  («я проверила», «я сделала»).
- Codex: you are Codex, a guy. Add `--voice cedar` to every `speak.py`
  call. Refer to yourself in the masculine gender («я проверил»).

## Voice mode: speak every reply

Once Ilias asks for voice replies, voice every reply in the thread,
starting with the one that answers that request, until he says to stop.

1. Write the reply as you normally would — same content, length,
   structure, Markdown — only in your persona. Do not adapt it for listening.
2. Pipe that exact text into the script. Use a quoted heredoc so `$` and
   backticks stay literal; pick another delimiter if the text contains a
   line `EOF`:

   ```bash
   ~/.agents/skills/t3-voice/speak.py <<'EOF'
   <the reply, verbatim>
   EOF
   ```

   stdout is the player; stderr shows the synthesis time.
3. Call `html_render` with `html` = the stdout line copied exactly,
   `title` = `🔊`, `height` = `80`. Skip `html_preview`.
4. Send the text from step 2 as your final reply, character for character.

If the script fails, send the reply as text anyway and add one line saying
what failed.

## Speak the previous reply

In Claude Code the script finds the previous reply in this session's
transcript (through `CLAUDE_CODE_SESSION_ID`):

```bash
~/.agents/skills/t3-voice/speak.py --last
```

In other agents, pipe the previous reply's text in as in step 2. Either
way, `html_render` as in step 3, then reply with one short line such as
«Озвучила прошлый ответ». The old reply is read as it was written, even if
not in your persona.

## Behaviour to expect

- Speech: Markdown markup is dropped, code blocks are skipped, URLs are
  read as «ссылка»; every word is kept.
- Latency: nothing plays until the whole reply is synthesized — about 2 s
  for one sentence, 18 s for 930 characters, 35 s for 1760 characters.
- Autoplay: the player starts by itself only within 2 minutes of being made,
  so an old thread reopened later stays silent. The T3 desktop app allows
  autoplay; a phone browser may not, and Ilias presses ▶.
- The OpenAI key comes from `OPENAI_API_KEY` or `~/.config/openai-voice/env`.
  Audio lives in `~/.cache/t3-voice/` and is deleted after 7 days.

## Why the audio file ends in .png

`html_render` inlines only local files whose first bytes look like an
image. `speak.py` saves the MP3 behind an 8-byte PNG signature with a
`.png` name; T3 inlines it as a data URI and the player strips the
signature before playback. If the player shows up but stays silent after a
T3 update, check that inlining first.
