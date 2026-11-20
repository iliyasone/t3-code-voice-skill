#!/usr/bin/env python3
"""Listening statistics for voiced replies, per agent.

A reply counts as seen when its player loaded within two minutes of being made,
that is, while Ilias was in the thread. Among seen replies:
- played: the audio ran (by itself or after a press);
- finished: playback reached 90% of the audio;
- right call: an autoplay reply that he let play past half, or a quiet reply he
  never pressed. Wrong: an autoplay reply stopped before half, or a quiet reply
  he chose to play.
"""

import argparse
import json
import os
import time
from collections import defaultdict

STATS_FILE = os.path.expanduser("~/.local/share/t3-voice/events.jsonl")
NAMES = {"cove": "Opus", "sol": "Opus", "ember": "Fable", "breeze": "Fable", "arbor": "GPT"}


def replies(since):
    made, events = {}, defaultdict(list)
    with open(STATS_FILE) as f:
        for line in f:
            event = json.loads(line)
            if event["e"] == "made":
                if event["time"] >= since:
                    made[event["id"]] = event
            else:
                events[event["id"]].append(event)
    for reply_id, reply in made.items():
        log = events.get(reply_id, [])
        duration = max((e.get("d") or 0 for e in log), default=0)
        ended = any(e["e"] == "ended" for e in log)
        reached = max((e.get("at") or 0 for e in log if e["e"] in ("pause", "leave")), default=None)
        if ended:
            reached = duration
        plays = [e for e in log if e["e"] == "play"]
        yield {
            "agent": NAMES.get(reply["voice"], reply["voice"]),
            "autoplay": reply["autoplay"],
            "seen": any(e["e"] == "shown" and e.get("fresh") for e in log),
            "played": bool(plays),
            "pressed": any(e.get("by") == "user" for e in plays),
            "blocked": any(e["e"] == "blocked" for e in log),
            "share": reached / duration if reached is not None and duration else None,
        }


def verdict(r):
    if not r["seen"]:
        return None
    if r["autoplay"]:
        if (r["blocked"] and not r["pressed"]) or r["share"] is None:
            return None
        return r["share"] >= 0.5
    return not r["pressed"]


def summary(rows):
    seen = [r for r in rows if r["seen"]]
    played = [r for r in seen if r["played"]]
    finished = [r for r in played if (r["share"] or 0) >= 0.9]
    calls = [v for v in map(verdict, seen) if v is not None]
    auto = [r for r in seen if r["autoplay"]]
    pct = lambda a, b: f"{len(a)}/{len(b)} ({100 * len(a) // len(b)}%)" if b else "—"
    return [
        ("Replies", str(len(rows))),
        ("Seen live", str(len(seen))),
        ("Autoplay", pct(auto, seen)),
        ("Played", pct(played, seen)),
        ("Finished", pct(finished, played)),
        ("Right call", pct([c for c in calls if c], calls)),
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--days", type=float, default=30, help="look back this many days (default 30)")
    args = parser.parse_args()
    rows = list(replies(time.time() - args.days * 86400))
    groups = {"All": rows} | {a: [r for r in rows if r["agent"] == a] for a in sorted({r["agent"] for r in rows})}
    tables = {name: dict(summary(group)) for name, group in groups.items()}
    labels = [label for label, _ in summary(rows)]
    width = max(len(label) for label in labels)
    print(" " * width + "".join(f"{name:>16}" for name in tables))
    for label in labels:
        print(f"{label:<{width}}" + "".join(f"{t[label]:>16}" for t in tables.values()))


if __name__ == "__main__":
    main()
