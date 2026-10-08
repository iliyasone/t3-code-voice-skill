#!/usr/bin/env python3
"""Voice an agent reply in T3 Code.

Reads the reply text from stdin (or, with --last, the previous reply from this
Claude Code session's transcript), synthesizes it with OpenAI TTS in parallel
chunks, and prints a small HTML player to stdout for the html_render tool.

The audio is stored as an MP3 behind an 8-byte PNG signature with a .png name:
html_render only inlines local files that look like images, and the player
strips the signature again before playback.
"""

import argparse
import concurrent.futures
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
MODEL = os.environ.get("T3_VOICE_MODEL", "gpt-4o-mini-tts")
VOICE = os.environ.get("T3_VOICE_VOICE", "coral")
CHUNK_CHARS = 220
INSTRUCTIONS = (
    "Read the text exactly as written, word for word, in its own language. "
    "Natural, warm, conversational tone, like a colleague answering out loud. "
    "Moderately brisk pace."
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


def chunks(text):
    sentences = re.split(r"(?<=[.!?…;:])\s+", text)
    pieces = []
    for s in sentences:
        while len(s) > CHUNK_CHARS * 2:  # one huge sentence: cut at a comma or space
            cut = max(s.rfind(", ", 0, CHUNK_CHARS * 2), s.rfind(" ", 0, CHUNK_CHARS * 2))
            cut = cut + 1 if cut > 0 else CHUNK_CHARS * 2
            pieces.append(s[:cut].strip())
            s = s[cut:].strip()
        pieces.append(s)
    out, cur = [], ""
    for p in pieces:
        if cur and len(cur) + len(p) + 1 > CHUNK_CHARS:
            out.append(cur)
            cur = p
        else:
            cur = f"{cur} {p}".strip()
    if cur:
        out.append(cur)
    return out


def synthesize(key, text):
    body = {"model": MODEL, "voice": VOICE, "input": text, "response_format": "mp3"}
    if MODEL.startswith("gpt-"):
        body["instructions"] = INSTRUCTIONS
    request = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        json.dumps(body).encode(),
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt == 2:
                raise SystemExit(f"OpenAI TTS failed: {getattr(error, 'read', lambda: error)()}")
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
    parts = chunks(text)
    key = api_key()
    with concurrent.futures.ThreadPoolExecutor(len(parts)) as pool:
        audio = b"".join(pool.map(lambda part: synthesize(key, part), parts))

    os.makedirs(OUT_DIR, exist_ok=True)
    for old in glob.glob(f"{OUT_DIR}/*.png"):
        if time.time() - os.path.getmtime(old) > 7 * 86400:
            os.remove(old)
    path = f"{OUT_DIR}/{uuid.uuid4().hex[:12]}.png"
    with open(path, "wb") as f:
        f.write(PNG_SIGNATURE + audio)

    seconds = len(audio) * 8 / 128000  # OpenAI MP3 is 128 kbps CBR
    duration = f"{int(seconds // 60)}:{int(seconds % 60):02d}"
    print(PLAYER.replace("__PATH__", path).replace("__MADE__", str(int(time.time() * 1000))))
    print(
        f"t3-voice: {len(text)} chars, {len(parts)} chunks, {duration} audio, "
        f"synthesized in {time.time() - started:.1f}s",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
