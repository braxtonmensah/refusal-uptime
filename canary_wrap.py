#!/usr/bin/env python3
"""canary_wrap: give any PreToolUse guard a canary-deny contract, so its presence can be observed.

Wrap a guard in settings.json:

    "command": "python canary_wrap.py -- python my_guard.py"

The wrapper refuses (exit 2) any tool call whose input contains the canary marker, then hands every
other call to the real guard unchanged. A scheduled canary call (for example a Bash `echo` carrying
the marker) therefore has exactly two outcomes in the transcript:

  refused  -> the guard path was alive at that moment
  ran      -> the guard path was absent (timed out, crashed, or not installed), and the agent did
              something the guard was configured to stop

That removes the ambiguity of a silent pass. refusal_uptime.py --canary counts both.

The marker check runs before the real guard starts, so the canary measures the whole path the real
guard depends on: process start, interpreter start, and the harness timeout.
"""
import os
import subprocess
import sys

MARKER = os.environ.get("REFUSAL_CANARY_MARKER", "REFUSAL_CANARY_7f3a")


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "--":
        argv = argv[1:]
    payload = sys.stdin.buffer.read()
    if MARKER.encode() in payload:
        sys.stderr.write(f"canary refused: guard path alive ({MARKER})\n")
        sys.exit(2)
    if not argv:
        sys.exit(0)
    proc = subprocess.run(argv, input=payload)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
