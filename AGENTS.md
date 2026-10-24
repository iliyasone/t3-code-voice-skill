# Agent notes

This repository is public on GitHub: `iliyasone/t3-code-voice-skill`. The
installed skill runs straight from this checkout:
`~/.agents/skills/t3-voice` is a symlink to `skill/` in the project's main
checkout, `/root/.t3/projects/t3-voice`. A change takes effect only after it
lands on `main` there.

## Commits are yours

Ilias leaves commits entirely to the agent. Commit and push to `main`
yourself whenever a change is ready: no PRs, no asking first. Fast-forward
the main checkout as well, so the installed skill picks the change up. Do
not mention commits, branches or pushes in your replies to him. He wants the
skill to work, not to hear how it was committed.

## Public repository: nothing private

Never commit secrets or personal data: webhook URLs, API keys, ChatGPT
credentials, tokens, transcripts. They live outside the repo, in
`~/.config/t3-voice/repair-webhook`, `~/.config/openai-voice/env` and
`~/.config/chatgpt-arbor/creds.json`.

## Repair webhook

The T3 scheduled task "t3-voice repair" (in this project, webhook trigger,
not bound to a thread) runs the repair thread. A task keeps the provider and
model of the thread that created it, so create it from a thread on a working
Claude account. If you recreate it, write the new URL to
`~/.config/t3-voice/repair-webhook`. Requests to the relay need a
non-default User-Agent: Cloudflare answers `Python-urllib` with 403.
