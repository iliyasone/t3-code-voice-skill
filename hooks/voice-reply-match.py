#!/usr/bin/env python3
"""Claude Code Stop hook: the final message must say what the voice said.

speak.py leaves the voiced reply in ~/.cache/t3-voice/pending-<session>.md. When the
turn ends, this hook compares it with the final message, ignoring formatting, links and
paths (the voice skips them). If the words differ, for example because the agent wrote
the reply again in another language, it sends the voiced text back to send unchanged.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "skill"))
from speak import OUT_DIR, speakable  # noqa: E402


def words(text):
    return re.findall(r"\w+", speakable(text).lower())


def main():
    event = json.load(sys.stdin)
    path = f"{OUT_DIR}/pending-{event.get('session_id')}.md"
    try:
        with open(path) as f:
            voiced = f.read()
    except OSError:
        return
    final = event.get("last_assistant_message") or ""
    if words(final) == words(voiced) or event.get("stop_hook_active"):
        os.remove(path)
        return
    print(json.dumps({
        "decision": "block",
        "reason": "The final message differs from the reply you voiced. Send exactly this text as the "
        "final message, in its language, with nothing before or after it:\n\n" + voiced.strip(),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
