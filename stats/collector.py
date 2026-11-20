#!/usr/bin/env python3
"""Collect listening events from the voice player.

The player in each voiced reply sends beacons (shown, play, pause, ended, leave,
blocked, rate) to this server; it appends them to the same JSON Lines file where
speak.py logs every voiced reply. stats/report.py reads that file. A GET tells a
reopened player where it stopped and which speed was chosen last.
"""

import json
import os
import re
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATS_FILE = os.path.expanduser("~/.local/share/t3-voice/events.jsonl")
EVENTS = {"shown", "play", "pause", "ended", "leave", "blocked", "rate"}
FIELDS = {"id", "e", "at", "d", "rate", "dev", "by", "fresh"}


class Handler(BaseHTTPRequestHandler):
    def reply(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    do_OPTIONS = reply

    def do_GET(self):
        """Where the player of reply ?id= stopped and the last speed: the frame has no storage of its own."""
        reply_id = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("id", [""])[0]
        state = {"at": 0, "rate": 1}
        try:
            with open(STATS_FILE) as f:
                for line in f:
                    event = json.loads(line)
                    if event.get("rate") and event["e"] in ("rate", "pause", "leave", "ended"):
                        state["rate"] = event["rate"]
                    if event.get("id") == reply_id and event["e"] in ("pause", "leave", "ended"):
                        state["at"] = 0 if event["e"] == "ended" else event.get("at") or 0
        except (OSError, ValueError):
            pass
        body = json.dumps(state).encode()
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if 0 < length <= 2048:
            try:
                event = json.loads(self.rfile.read(length))
            except ValueError:
                event = None
            if (
                isinstance(event, dict)
                and event.get("e") in EVENTS
                and re.fullmatch(r"[0-9a-f]{12}", str(event.get("id")))
            ):
                event = {k: v for k, v in event.items() if k in FIELDS}
                event["time"] = time.time()
                with open(STATS_FILE, "a") as f:
                    f.write(json.dumps(event) + "\n")
        self.reply()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    os.makedirs(os.path.dirname(STATS_FILE), exist_ok=True)
    ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", 8812))), Handler).serve_forever()
