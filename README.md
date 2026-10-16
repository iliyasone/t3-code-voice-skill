<img src="assets/icon.svg" width="64" height="64" alt="">

# t3-voice

Agent skill that reads the agent's reply aloud in T3 Code: text → an MP3
disguised as a PNG (so `html_render` inlines it) → a tiny `<audio>` player
that autoplays in the desktop app.

Voices are ChatGPT's Read Aloud voices, served by the local `arbor-tts`
service ([iliyasone/arbor-chatgpt-voice](https://github.com/iliyasone/arbor-chatgpt-voice)):
Claude Opus speaks with `sol`, Claude Fable with `breeze`, Codex with `arbor`.
When `arbor-tts` fails, `speak.py` falls back to the free Google Translate voice
and posts the error to a T3 webhook task, which opens a new thread that repairs
the service (at most once per 3 hours). Paid OpenAI `gpt-audio-1.5` is used only
when Google fails too.

The webhook URL lives in `~/.config/t3-voice/repair-webhook`, outside the repo.
It belongs to the T3 scheduled task "t3-voice repair" in this project; the
task's prompt is the brief the repair thread gets. If the task is deleted,
recreate it with the `schedule_task` T3 tool (`{"type":"webhook"}`,
`bindToCurrentThread: false`) and write the new URL to that file.

The skill's source lives in [iliyasone/skills](https://github.com/iliyasone/skills/tree/main/skills/t3-voice);
`skill/` here is a symlink to its local clone, `/root/repositories/skills/skills/t3-voice`,
which is also what `~/.agents/skills/t3-voice` points to (linked into
`~/.claude/skills` and `~/.codex/skills`).
