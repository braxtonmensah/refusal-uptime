"""Replica of a transcript-reading PreToolUse guard (the shape of no_poll.py): fresh interpreter,
read the last 3 MB of the session transcript, JSON-parse the relevant lines, allow."""
import json
import os
import sys

TAIL = 3_000_000
payload = json.loads(sys.stdin.read() or "{}")
path = payload.get("transcript_path", "")
size = os.path.getsize(path)
with open(path, "rb") as fh:
    if size > TAIL:
        fh.seek(size - TAIL)
        fh.readline()
    lines = fh.read().decode("utf-8", errors="replace").splitlines()
seen = 0
for line in lines:
    if '"tool_use"' not in line:
        continue
    try:
        row = json.loads(line)
    except ValueError:
        continue
    seen += len(row.get("message", {}).get("content") or [])
sys.exit(0)
