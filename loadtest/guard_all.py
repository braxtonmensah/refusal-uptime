"""The one-process form: the same five checks as the five per-call guard processes in sim.py (regex, transcript,
regex, transcript, regex), run in order inside a single fresh interpreter. This is the shape of the dispatcher
that replaced five hooks on the measured fleet."""
import json
import os
import re
import sys
from datetime import datetime

TAIL = 3_000_000
payload = json.loads(sys.stdin.read() or "{}")
cmd = payload.get("tool_input", {}).get("command", "")
PATTERNS = [re.compile(r"\b%s\b.*(%s)" % (a, b)) for a in ("python", "py", "node", "Rscript", "julia", "java")
            for b in ("train", "fit", "torch", "numpy", "pandas", "sklearn", "jax", "xgboost", "lightgbm", "cuda")]


def regex_check():
    _ = sum(1 for p in PATTERNS if p.search(cmd))
    _ = datetime.now().isoformat()


def transcript_check():
    path = payload.get("transcript_path", "")
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        if size > TAIL:
            fh.seek(size - TAIL)
            fh.readline()
        lines = fh.read().decode("utf-8", errors="replace").splitlines()
    for line in lines:
        if '"tool_use"' not in line:
            continue
        try:
            json.loads(line)
        except ValueError:
            continue


for check in (regex_check, transcript_check, regex_check, transcript_check, regex_check):
    check()
sys.exit(0)
