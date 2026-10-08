<img src="assets/icon.svg" width="64" height="64" alt="">

# t3-voice

Agent skill that reads the agent's reply aloud in T3 Code: OpenAI TTS in
parallel chunks → an MP3 disguised as a PNG (so `html_render` inlines it) →
a tiny `<audio>` player that autoplays in the desktop app.

- `skill/SKILL.md` — instructions for the agent.
- `skill/speak.py` — synthesizer; stdin text or `--last`, prints the player HTML.

Installed as `~/.agents/skills/t3-voice` (symlink to `skill/`), linked into
`~/.claude/skills` and `~/.codex/skills`.

Default voice: `gpt-audio-1.5` / `marin`, whole reply in one request
(~35 s for 1764 characters). Fallback `gpt-4o-mini-tts` with parallel
chunks: ~3 s for 560 characters, ~5.7 s for 1700.
