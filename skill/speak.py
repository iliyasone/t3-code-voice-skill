#!/usr/bin/env python3
"""Voice an agent reply in T3 Code.

Reads the reply text from stdin (or, with --last, the previous reply from this
Claude Code session's transcript), reads it aloud and prints a small HTML player
to stdout for the html_render tool.

Voices, in order of preference:
1. A ChatGPT Read Aloud voice from the local arbor-tts service
   (github.com/iliyasone/arbor-chatgpt-voice). When it fails, the script asks a
   T3 webhook (URL in ~/.config/t3-voice/repair-webhook) to start a thread that
   repairs it, at most once per REPAIR_COOLDOWN.
2. The free Google Translate voice.

The audio is stored as an MP3 behind an 8-byte PNG signature with a .png name:
html_render only inlines local files that look like images, and the player
strips the signature again before playback.
"""

import argparse
import concurrent.futures
import glob
import html
import http.client
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

REPAIR_WEBHOOK_FILE = os.path.expanduser("~/.config/t3-voice/repair-webhook")
REPAIR_COOLDOWN = 3 * 3600  # one repair thread at a time is enough; it may take a while
OUT_DIR = os.path.expanduser("~/.cache/t3-voice")
STATS_URL_FILE = os.path.expanduser("~/.config/t3-voice/stats-url")
STATS_FILE = os.path.expanduser("~/.local/share/t3-voice/events.jsonl")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ARBOR_URL = os.environ.get("ARBOR_TTS_URL", "http://127.0.0.1:8811/v1/audio/speech")
GOOGLE_TTS_URL = "https://translate.google.com/translate_tts"
GOOGLE_MAX_CHARS = 190  # translate_tts rejects requests over ~200 characters
GOOGLE_TEMPO = 1.25  # Ilias listens to the Google voice sped up; ffmpeg applies it (translate_tts ignores ttsspeed)
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


PATH = re.compile(r"(?<![\w/])[~.]{0,2}/?(?:[\w.@+-]+/)+[\w.@+-]*(?::\d+(?:-\d+)?)?")


def is_path(token):
    """File paths are noise when heard: /abs, ~/x, ./x, a/b/c, or dir/file.ext."""
    return bool(
        re.match(r"[~./]", token)
        or token.count("/") >= 2
        or re.search(r"\.\w{1,5}(?::\d+(?:-\d+)?)?$", token)
    )


def drop_path(match):
    token = match.group(0)
    core = token.rstrip(".")  # a path can end a sentence; keep the full stop
    return " " + token[len(core):] if is_path(core) else token


def speakable(md):
    """Strip Markdown markup, code blocks, URLs and file paths; other words stay untouched."""
    text = re.sub(r"```.*?```", " ", md, flags=re.S)
    text = re.sub(r"<[^>\n]+>", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = PATH.sub(drop_path, text)
    lines = []
    for line in text.splitlines():
        if re.fullmatch(r"\s*\|?[\s:|-]+\|?\s*", line) and "-" in line:
            continue  # table separator row
        line = re.sub(r"^\s*(#{1,6}|>+|[-*+])\s+", "", line)
        line = re.sub(r"\s*\|\s*", ", ", line.strip().strip("|").strip())
        line = re.sub(r"(\*\*|__|\*|`|~~)", "", line)
        # Tidy punctuation left behind by removed paths: "файл: , скрипт: ." -> "файл, скрипт."
        line = re.sub(r"\((?:\s*(?:см|see)\.?)?\s*\)", " ", line)
        line = re.sub(r"\s+([,.;:!?])", r"\1", line)
        line = re.sub(r"([,;:])(?:\s*[,;:])+", r"\1", line)
        line = re.sub(r"[,;:]+(?=\s*[.!?]|$)", "", line)
        line = re.sub(r"^[\s,.;:—–-]+", "", line).strip()
        if re.search(r"\w", line):
            lines.append(line if re.search(r"[.!?…:;,]$", line) else line + ".")
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def chatgpt(text, voice):
    """ChatGPT Read Aloud voice from the local arbor-tts service; it writes numbers out as words first."""
    body = {"input": text, "voice": voice, "spell_numbers": True}
    request = urllib.request.Request(ARBOR_URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                audio = response.read()
            break
        except http.client.IncompleteRead as error:  # ChatGPT reset the audio stream midway; usually one-off
            if attempt:
                raise SystemExit(f"arbor-tts failed: {error}")
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError) as error:
            raise SystemExit(f"arbor-tts failed: {error}")
    if not audio:
        raise SystemExit("arbor-tts returned no audio")
    return audio


def google_pieces(text):
    """Split at sentence ends, then at commas and spaces, into pieces Google Translate accepts."""
    pieces, current = [], ""
    for part in re.split(r"(?<=[.!?…,;:])\s+", text):
        while len(part) > GOOGLE_MAX_CHARS:
            cut = part.rfind(" ", 0, GOOGLE_MAX_CHARS)
            cut = cut if cut > 0 else GOOGLE_MAX_CHARS
            if current:
                pieces.append(current)
                current = ""
            pieces.append(part[:cut])
            part = part[cut:].strip()
        if current and len(current) + len(part) + 1 > GOOGLE_MAX_CHARS:
            pieces.append(current)
            current = ""
        current = f"{current} {part}".strip()
    return pieces + [current] if current else pieces


def google(text):
    """Free Google Translate voice: the fallback when the ChatGPT voice fails."""
    def fetch(piece):
        lang = "ru" if re.search(r"[а-яё]", piece, re.I) else "en"
        query = urllib.parse.urlencode({"ie": "UTF-8", "client": "tw-ob", "tl": lang, "q": piece})
        request = urllib.request.Request(f"{GOOGLE_TTS_URL}?{query}", headers={"User-Agent": "Mozilla/5.0"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return response.read()
            except (urllib.error.URLError, TimeoutError) as error:
                if attempt == 2:
                    raise SystemExit(f"Google Translate TTS failed: {error}")
                time.sleep(0.5)

    with concurrent.futures.ThreadPoolExecutor(6) as pool:
        audio = b"".join(pool.map(fetch, google_pieces(text)))
    try:
        slowed = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-filter:a", f"atempo={GOOGLE_TEMPO}", "-f", "mp3", "pipe:1"],
            input=audio, capture_output=True, check=True, timeout=120,
        ).stdout
        return slowed or audio
    except (OSError, subprocess.SubprocessError):
        return audio


def request_repair(error, fallback):
    """Start a T3 thread that repairs the ChatGPT voice, unless one was started recently."""
    stamp = f"{OUT_DIR}/repair-requested"
    if os.path.exists(stamp) and time.time() - os.path.getmtime(stamp) < REPAIR_COOLDOWN:
        return
    try:
        with open(REPAIR_WEBHOOK_FILE) as f:
            url = f.read().strip()
        body = {"error": error, "fallback": fallback, "time": time.strftime("%Y-%m-%d %H:%M:%S %Z")}
        # The relay sits behind Cloudflare, which answers 403 (error 1010) to the Python-urllib User-Agent.
        headers = {"Content-Type": "application/json", "User-Agent": "t3-voice/1"}
        request = urllib.request.Request(url, json.dumps(body).encode(), headers)
        urllib.request.urlopen(request, timeout=15).close()
    except (OSError, urllib.error.URLError, http.client.HTTPException) as e:
        print(f"t3-voice: could not request a repair: {e}", file=sys.stderr)
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    open(stamp, "w").close()
    print("t3-voice: started a repair thread", file=sys.stderr)


def stats_url():
    """Public address of the listening-stats collector (stats/collector.py), or "" to send nothing."""
    try:
        with open(STATS_URL_FILE) as f:
            return f.read().strip()
    except OSError:
        return ""


def log_reply(reply_id, args, engine, text):
    """One line per voiced reply; the player's events join it by id in stats/report.py."""
    record = {
        "id": reply_id, "e": "made", "time": time.time(), "autoplay": args.autoplay, "voice": args.voice,
        "engine": engine, "text": text, "agent": "claude" if os.environ.get("CLAUDECODE") else "codex",
        "thread": os.environ.get("T3CODE_THREAD_ID"), "karaoke": args.karaoke,
    }
    try:
        os.makedirs(os.path.dirname(STATS_FILE), exist_ok=True)
        with open(STATS_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as error:
        print(f"t3-voice: could not log the reply: {error}", file=sys.stderr)


PLAYER = (
    # Own controls instead of <audio controls>: T3's full-screen button covers the native speed menu.
    # The right 44px stay empty for that button. Until the first play it is one quiet "Listen" pill;
    # seek and speed appear once it plays.
    '<style>#p{display:flex;align-items:center;gap:10px;height:44px;padding-right:44px;font:13px var(--font-sans)}'
    '#p button{flex:none;height:32px;border:1px solid var(--border);border-radius:16px;background:var(--secondary);'
    'color:var(--secondary-foreground);font:inherit;cursor:pointer;padding:0 12px}#r{min-width:52px}'
    '#s{flex:1;min-width:40px;accent-color:var(--primary)}#t{flex:none;color:var(--muted-foreground);font-variant-numeric:tabular-nums}'
    '#p.c #s,#p.c #r{display:none}</style>'
    '<div id=p class=c><button id=g>▶&#xFE0E; __LABEL__</button><input id=s type=range min=0 max=1 step=any value=0>'
    '<span id=t></span><button id=r>1×</button></div><audio id=a preload=metadata></audio><script>'
    'const S="__PATH__",b=atob(S.slice(S.indexOf(",")+1));'
    'a.src=URL.createObjectURL(new Blob([Uint8Array.from(b,c=>c.charCodeAt(0)).slice(8)],{type:"audio/mpeg"}));'
    'const R=[1,1.25,1.5,1.75,2],f=x=>(x/60|0)+":"+String(x%60|0).padStart(2,"0");'
    'let k=0,pos=0;const rate=()=>{a.defaultPlaybackRate=a.playbackRate=R[k];r.textContent=R[k]+"×"};rate();'
    # Listening statistics: each event goes to the collector as a beacon (no reply needed, no CORS preflight).
    'const E="__STATS__",I="__ID__",F=Date.now()-__MADE__<12e4;let U="user";'
    'const L=(e,x)=>{if(E)try{navigator.sendBeacon(E,JSON.stringify({id:I,e,at:Math.round(a.currentTime*10)/10,'
    'd:Math.round((a.duration||0)*10)/10,rate:R[k],dev:/Mobi|Android/i.test(navigator.userAgent)?"phone":"desktop",...x}))}catch(_){}};'
    'r.onclick=()=>{k=(k+1)%R.length;rate();L("rate")};'
    # The frame has an opaque origin and no storage, so the collector remembers where this reply stopped
    # and the last chosen speed; a reopened reply resumes from there.
    'const go=()=>{if(pos&&a.readyState&&a.paused&&!a.currentTime)a.currentTime=pos};'
    'E&&fetch(E+"?id="+I).then(x=>x.json()).then(x=>{k=Math.max(0,R.indexOf(x.rate));rate();'
    'if(x.at>1&&p.className){pos=x.at;g.textContent="▶\uFE0E __RESUME__ · "+f(pos);go()}}).catch(()=>{});'
    'g.onclick=()=>a.paused?a.play():a.pause();'
    'a.onplay=()=>{L("play",{by:U});U="user";p.className="";g.textContent="❚❚"};'
    'a.onpause=()=>{L("pause");g.textContent="▶\uFE0E"};addEventListener("pagehide",()=>a.paused||L("leave"));'
    'a.onloadedmetadata=a.ontimeupdate=()=>{go();s.max=a.duration||1;s.value=a.currentTime;'
    't.textContent=p.className?f(a.duration||0):f(a.currentTime)+" / "+f(a.duration||0)};s.oninput=()=>a.currentTime=+s.value;'
    # Media keys and a "play/pause" gesture reach the reply through the app's media session; at the end it
    # rewinds and stays paused, so the session (and the gesture) survives to play it again.
    'const M=navigator.mediaSession;if(M){M.setActionHandler("play",()=>a.play());M.setActionHandler("pause",()=>a.pause());'
    'M.setActionHandler("stop",()=>{a.pause();a.currentTime=0})}a.onended=()=>{L("ended");a.currentTime=0;a.pause()};L("shown",{fresh:F});'
    # Only an --autoplay reply starts by itself, and only when freshly made, not when the thread is reopened.
    '__AUTOPLAY__&&F&&(U="auto",a.play().catch(()=>{U="user";L("blocked")}))</script>'
)


def inline_html(md):
    out = html.escape(md, quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<![\w*])\*([^*]+)\*(?![\w*])", r"<i>\1</i>", out)
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', out)


def sentence_spans(md, spoken):
    """A block's sentences as HTML; each one read aloud becomes a span and adds its words to `spoken`."""
    parts = []
    for piece in re.split(r"(?<=[.!?…:;])\s+(?=[A-ZА-ЯЁ«\[`*\d])", md.strip()):
        words = speakable(piece)
        if words:
            parts.append(f"<span class=s data-i={len(spoken)}>{inline_html(piece)}</span>")
            spoken.append(words)
        else:
            parts.append(inline_html(piece))
    return " ".join(parts)


def karaoke_body(md):
    """The reply's Markdown (paragraphs, headings, lists, code blocks) as HTML, and the sentences to read."""
    spoken, out, lines, i = [], [], md.strip().splitlines(), 0
    item = re.compile(r"\s*(?:[-*+]|\d+\.)\s+(.*)")
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre>" + html.escape("\n".join(lines[i + 1:j])) + "</pre>")
            i = j + 1
        elif m := re.match(r"(#{1,6})\s+(.*)", line):
            out.append(f"<h{len(m[1]) + 1}>{sentence_spans(m[2], spoken)}</h{len(m[1]) + 1}>")
            i += 1
        elif item.match(line):
            tag = "ol" if re.match(r"\s*\d+\.", line) else "ul"
            items = []
            while i < len(lines) and (m := item.match(lines[i])):
                items.append(f"<li>{sentence_spans(m[1], spoken)}</li>")
                i += 1
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
        elif line.strip():
            j = i
            while j < len(lines) and lines[j].strip() and not re.match(r"```|#{1,6}\s", lines[j]) and not item.match(lines[j]):
                j += 1
            out.append(f"<p>{sentence_spans(' '.join(lines[i:j]), spoken)}</p>")
            i = j
        else:
            i += 1
    return "".join(out), spoken


def sentence_starts(spoken, audio):
    """Start second of each sentence: the time expected from its length, moved to the nearest pause in the audio."""
    log = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", "pipe:0", "-af", "silencedetect=noise=-38dB:d=0.18", "-f", "null", "-"],
        input=audio, capture_output=True,
    ).stderr.decode()
    gaps = list(zip(*([float(x) for x in re.findall(rf"silence_{k}: ([\d.]+)", log)] for k in ("start", "end"))))
    clock = re.findall(r"time=(\d+):(\d+):([\d.]+)", log)
    duration = max((int(h) * 3600 + int(m) * 60 + float(s) for h, m, s in clock), default=0)
    times, at, left = [0.0], 0.0, sum(len(s) for s in spoken)
    for sentence in spoken[:-1]:
        length = len(sentence) * (duration - at) / left
        guess = at + length
        near = [g for g in gaps if g[0] > at + 0.3 and abs(g[0] - guess) < max(1.5, length * 0.45)]
        if near:  # a longer pause is more likely a sentence end
            gap = min(near, key=lambda g: abs(g[0] - guess) - 3 * (g[1] - g[0]))
            guess = gap[1] - 0.05
            gaps = [g for g in gaps if g[0] > gap[0]]
        at, left = guess, left - len(sentence)
        times.append(round(at, 2))
    return times


KARAOKE = (
    # --karaoke: the whole reply sits under the player, and the sentence being read is highlighted.
    # A click on a sentence plays from it. Links to local files do not open from a frame.
    '<style>#b{font:14px/1.65 var(--font-sans);overflow-wrap:anywhere}#b p{margin:.6em 0}'
    '#b ul,#b ol{margin:.6em 0;padding-left:1.4em}#b li{margin:.25em 0}'
    '#b code,#b pre{font:12.5px var(--font-mono);background:var(--code-background);border-radius:4px;padding:1px 4px}'
    '#b pre{padding:10px;overflow-x:auto}#b a{color:var(--primary)}'
    '.s{cursor:pointer;border-radius:3px;transition:background .15s;box-decoration-break:clone;-webkit-box-decoration-break:clone}'
    '.s.on{background:color-mix(in srgb,var(--primary) 22%,transparent)}</style>'
    '__PLAYER__<div id=b>__BODY__</div><script>const T=__TIMES__,Q=[...document.querySelectorAll(".s")];'
    'const mark=()=>{let n=-1;if(!p.className&&a.currentTime)for(let i=0;i<T.length&&T[i]<=a.currentTime+.05;i++)n=i;'
    'Q.forEach(q=>q.classList.toggle("on",+q.dataset.i===n))};'
    '["timeupdate","seeked","ended"].forEach(e=>a.addEventListener(e,mark));'
    'Q.forEach(q=>q.onclick=e=>{if(e.target.closest("a")||String(getSelection()))return;a.currentTime=T[+q.dataset.i];a.play()})</script>'
)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--last", action="store_true", help="speak the previous reply of this session")
    parser.add_argument("--autoplay", action="store_true", help="start playing as soon as the reply appears")
    parser.add_argument("--karaoke", action="store_true", help="show the whole reply and highlight the sentence being read")
    parser.add_argument("--voice", default="sol", help="ChatGPT voice: arbor, sol, breeze, juniper, maple, vale, ... (default: sol)")
    args = parser.parse_args()

    started = time.time()
    reply = last_reply() if args.last else sys.stdin.read()
    if args.karaoke:
        body, spoken = karaoke_body(reply)
        text = " ".join(spoken)
    else:
        text = speakable(reply)
    if not text:
        sys.exit("nothing to speak")
    try:
        audio, engine = chatgpt(text, args.voice), f"chatgpt/{args.voice}"
    except SystemExit as error:
        failure = str(error)
        print(f"t3-voice: {failure}; using Google Translate", file=sys.stderr)
        request_repair(failure, "Google Translate")
        try:
            audio, engine = google(text), "google (fallback)"
        except SystemExit as google_error:
            sys.exit(f"t3-voice: {failure}; Google Translate failed too: {google_error}")

    os.makedirs(OUT_DIR, exist_ok=True)
    for old in glob.glob(f"{OUT_DIR}/*.png"):
        if time.time() - os.path.getmtime(old) > 7 * 86400:
            os.remove(old)
    reply_id = uuid.uuid4().hex[:12]
    path = f"{OUT_DIR}/{reply_id}.png"
    with open(path, "wb") as f:
        f.write(PNG_SIGNATURE + audio)

    russian = re.search(r"[а-яё]", text, re.I)
    player = PLAYER.replace("__LABEL__", "Прослушать" if russian else "Listen")
    player = player.replace("__RESUME__", "Продолжить" if russian else "Resume").replace("__AUTOPLAY__", str(int(args.autoplay)))
    player = player.replace("__ID__", reply_id).replace("__STATS__", stats_url())
    if args.karaoke:
        times = json.dumps(sentence_starts(spoken, audio))
        player = KARAOKE.replace("__BODY__", body).replace("__PLAYER__", player).replace("__TIMES__", times)
    print(player.replace("__PATH__", path).replace("__MADE__", str(int(time.time() * 1000))))
    log_reply(reply_id, args, engine, text)
    print(
        f"t3-voice: {engine}, {len(text)} chars, {len(audio) // 1024} KiB, "
        f"synthesized in {time.time() - started:.1f}s",
        file=sys.stderr,
    )
    # Agents tended to write the final message anew after voicing it, sometimes in another language.
    if args.karaoke:
        print("t3-voice: the reply is in the player; send one short line as the final message.", file=sys.stderr)
    elif not args.last:
        print(f"t3-voice: send exactly this as the final message, same words and language:\n{reply.strip()}", file=sys.stderr)


if __name__ == "__main__":
    main()
