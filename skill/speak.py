#!/usr/bin/env python3
"""Voice an agent reply in T3 Code.

Reads the reply text from stdin (or, with --last, the previous reply from this
Claude Code session's transcript), reads it aloud with OpenAI gpt-audio-1.5 (voice
marin) in one request, and prints a small HTML player to stdout for the html_render tool.

The audio is stored as an MP3 behind an 8-byte PNG signature with a .png name:
html_render only inlines local files that look like images, and the player
strips the signature again before playback.
"""

import argparse
import base64
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid

ENV_FILE = os.path.expanduser("~/.config/openai-voice/env")
OUT_DIR = os.path.expanduser("~/.cache/t3-voice")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MODEL = "gpt-audio-1.5"
VOICE = "marin"
READER_PROMPT = (
    "You are a voice actor. Read the user's text aloud exactly as written, word for word, "
    "in its language. Do not add, drop, translate or rephrase anything; no greeting, no comments. "
    "Natural, warm, lively conversational delivery, like a smart friend explaining something."
)


def api_key():
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    with open(ENV_FILE) as f:
        for line in f:
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
    sys.exit(f"OPENAI_API_KEY not found in env or {ENV_FILE}")


def last_reply():
    """Final text of the previous completed turn in this Claude Code session."""
    session = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not session:
        sys.exit("--last needs CLAUDE_CODE_SESSION_ID (Claude Code only); pipe the text instead")
    paths = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{session}.jsonl"))
    if not paths:
        sys.exit(f"transcript for session {session} not found")
    turns, current = [], []
    for line in open(paths[0]):
        entry = json.loads(line)
        if entry.get("isSidechain"):
            continue
        content = (entry.get("message") or {}).get("content")
        if entry.get("type") == "user":
            is_prompt = isinstance(content, str) or (
                isinstance(content, list) and any(b.get("type") == "text" for b in content)
            )
            if is_prompt and not entry.get("isMeta"):
                turns.append(current)
                current = []
        elif entry.get("type") == "assistant" and isinstance(content, list):
            for block in content:
                if block.get("type") == "tool_use":
                    current = []  # only text after the last tool call is the final reply
                elif block.get("type") == "text" and block["text"].strip():
                    current.append(block["text"])
    turns.append(current)
    # The last turn is the one asking to speak; the reply before it is the target.
    for texts in reversed(turns[:-1]):
        if texts:
            return "\n\n".join(texts)
    sys.exit("no previous reply found in the transcript")


def speakable(md):
    """Strip Markdown markup only; the words themselves stay untouched."""
    text = re.sub(r"```.*?```", " ", md, flags=re.S)
    text = re.sub(r"<[^>\n]+>", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "ссылка", text)
    lines = []
    for line in text.splitlines():
        if re.fullmatch(r"\s*\|?[\s:|-]+\|?\s*", line) and "-" in line:
            continue  # table separator row
        line = re.sub(r"^\s*(#{1,6}|>+|[-*+])\s+", "", line)
        line = re.sub(r"\s*\|\s*", ", ", line.strip().strip("|").strip())
        if line:
            lines.append(line if re.search(r"[.!?…:;,]$", line) else line + ".")
    text = " ".join(lines)
    text = re.sub(r"(\*\*|__|\*|`|~~)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def synthesize(key, text):
    body = {
        "model": MODEL,
        "modalities": ["text", "audio"],
        "audio": {"voice": VOICE, "format": "mp3"},
        "messages": [
            {"role": "system", "content": READER_PROMPT},
            {"role": "user", "content": text},
        ],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        json.dumps(body).encode(),
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return base64.b64decode(json.load(response)["choices"][0]["message"]["audio"]["data"])
        except urllib.error.HTTPError as error:
            raise SystemExit(f"OpenAI {MODEL} failed: {error.code} {error.read().decode()[:500]}")
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt == 2:
                raise SystemExit(f"OpenAI {MODEL} unreachable: {error}")
            time.sleep(0.5)


PLAYER = (
    '<audio id=a controls style="width:100%;height:40px"></audio><script>'
    'const S="__PATH__",b=atob(S.slice(S.indexOf(",")+1));'
    'a.src=URL.createObjectURL(new Blob([Uint8Array.from(b,c=>c.charCodeAt(0)).slice(8)],{type:"audio/mpeg"}));'
    'Date.now()-__MADE__<12e4&&a.play().catch(()=>{})</script>'
)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--last", action="store_true", help="speak the previous reply of this session")
    args = parser.parse_args()

    started = time.time()
    text = speakable(last_reply() if args.last else sys.stdin.read())
    if not text:
        sys.exit("nothing to speak")
    audio = synthesize(api_key(), text)

    os.makedirs(OUT_DIR, exist_ok=True)
    for old in glob.glob(f"{OUT_DIR}/*.png"):
        if time.time() - os.path.getmtime(old) > 7 * 86400:
            os.remove(old)
    path = f"{OUT_DIR}/{uuid.uuid4().hex[:12]}.png"
    with open(path, "wb") as f:
        f.write(PNG_SIGNATURE + audio)

    print(PLAYER.replace("__PATH__", path).replace("__MADE__", str(int(time.time() * 1000))))
    print(
        f"t3-voice: {MODEL}/{VOICE}, {len(text)} chars, {len(audio) // 1024} KiB, "
        f"synthesized in {time.time() - started:.1f}s",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
