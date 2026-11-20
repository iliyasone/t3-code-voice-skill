# Agent notes

This repository is public on GitHub: `iliyasone/t3-code-voice-skill`. On
Ilias's machine it is not installed as a skill: the voice rules live in his
global `~/.codex/AGENTS.md`, which calls `skill/speak.py` in the project's main
checkout, `/root/.t3/projects/t3-voice`. A change to the script takes effect
only after it lands on `main` there; a change to the rules goes into that
global file, with `skill/SKILL.md` kept in step for other users.

## Commits are yours

Ilias leaves commits entirely to the agent. Commit and push to `main`
yourself whenever a change is ready: no PRs, no asking first. Fast-forward
the main checkout as well, so the script in use picks the change up. Do
not mention commits, branches or pushes in your replies to him. He wants the
skill to work, not to hear how it was committed.

## Public repository: nothing private

Never commit secrets or personal data: webhook URLs, API keys, ChatGPT
credentials, tokens, transcripts. They live outside the repo, in
`~/.config/t3-voice/repair-webhook` and `~/.config/chatgpt-arbor/creds.json`.

## Listening statistics

`stats/collector.py` runs as the systemd service `t3-voice-stats` on
127.0.0.1:8812; the Cloudflare tunnel service `cloudflared-t3-voice` publishes
it, and its public address is in `~/.config/t3-voice/stats-url` (not in the
repo).

## Repair webhook

The T3 scheduled task "t3-voice repair" (in this project, webhook trigger,
not bound to a thread) runs the repair thread. A task keeps the provider and
model of the thread that created it, so create it from a thread on a working
Claude account. If you recreate it, write the new URL to
`~/.config/t3-voice/repair-webhook`. Requests to the relay need a
non-default User-Agent: Cloudflare answers `Python-urllib` with 403.
