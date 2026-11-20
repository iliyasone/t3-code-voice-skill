---
name: t3-voice
description: always enabled — use for every reply, unless the user explicitly asks not to
---

# t3-voice

Always on: voice every reply unless Ilias explicitly asks not to.

**Claude speaks of itself in neutral terms.** Where the language marks gender,
phrase your own actions without it, in every message, voiced or not: «готово»,
«проверено», «нашлось», «предлагаю», not «я сделала» or «я сделал». Codex is a
man and uses the masculine.

Paths, URLs and code blocks are not read aloud, so write files as named links:
`[SKILL.md](/abs/path/SKILL.md)`. Each reply is voiced in one of two ways.

## Quiet (the default)

A "Listen" button under the reply. It plays only when Ilias presses it.

1. Write the whole reply as your message first.
2. Then pipe the same text into the script:

   ```bash
   ~/.agents/skills/t3-voice/speak.py --voice <voice> <<'EOF'
   <the reply, verbatim>
   EOF
   ```

3. Call `html_render` with `html` = the script's stdout, `title` = `🔊`,
   `height` = `80`. Skip `html_preview`. End the turn right there, with no
   text after it: the reply you wrote stays the final message, and the button
   sits below it.

## Out loud

The answer starts playing at once, above the reply. Use it when Ilias needs
to hear the answer now: he says he is busy or away from the screen, asks for
a voice answer, or is waiting on a short answer while doing something else.

1. Pipe the reply into the script with `--autoplay`.
2. Call `html_render` as above.
3. Send the same text as your final reply.

If the script fails, send the reply as text with one line saying the voice
failed.

Voices: Claude Opus `--voice cove`, Claude Fable `--voice ember`, Codex
`--voice arbor`.
