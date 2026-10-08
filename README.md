<img src="assets/icon.svg" width="64" height="64" alt="">

# t3-voice

Agent skill that reads the agent's reply aloud in T3 Code — Claude as
Клауди (`gpt-audio-1.5`, voice `marin`), Codex with `tts-1-hd` / `echo`:
OpenAI TTS → an MP3 disguised as a PNG (so
`html_render` inlines it) → a tiny `<audio>` player that autoplays in the
desktop app.

The skill's source lives in [iliyasone/skills](https://github.com/iliyasone/skills/tree/main/skills/t3-voice);
`skill/` here is a symlink to its local clone, `/root/repositories/skills/skills/t3-voice`,
which is also what `~/.agents/skills/t3-voice` points to (linked into
`~/.claude/skills` and `~/.codex/skills`).
