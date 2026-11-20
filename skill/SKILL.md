---
name: t3-voice
description: always enabled — use for every reply, unless the user explicitly asks not to
---

# t3-voice

Always on: voice every reply unless Ilias explicitly asks not to.

Paths, URLs and code blocks are not read aloud, so write files as named links:
`[SKILL.md](/abs/path/SKILL.md)`.

1. Write the reply as usual.
2. Pipe the exact text into the script:

   ```bash
   ~/.agents/skills/t3-voice/speak.py --voice <voice> [--autoplay] <<'EOF'
   <the reply, verbatim>
   EOF
   ```

3. Call `html_render` with `html` = the script's stdout, `title` = `🔊`,
   `height` = `80`. Skip `html_preview`.
4. Send the same text as your final reply. The player sits above it.

Without `--autoplay` the player is a quiet "Listen" button: the default. Add
`--autoplay` only when Ilias needs to hear the answer now: he says he is busy
or away from the screen, or asks for a voice answer.

If the script fails, send the reply as text with one line saying the voice
failed.

Voices: Claude Opus `--voice cove`, Claude Fable `--voice ember`, Codex
`--voice arbor`.
