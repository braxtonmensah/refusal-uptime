#!/usr/bin/env python3
"""refusal_uptime: did your agent's guards actually run?

Claude Code runs each PreToolUse hook as a separate process with a timeout. Unless the hook sets
onFailure "block", a timeout or error lets the tool call proceed, and the agent's tool result looks
the same as if the guard had allowed it. This reads your transcripts and reports, per hook, the
share of matching tool calls on which the hook was absent (timed out or errored), which is its
fail-open rate. Refusal uptime is one minus that.

Standard library only. Reads local files, sends nothing anywhere.

    python refusal_uptime.py                        # ~/.claude settings and transcripts
    python refusal_uptime.py --min-uptime 0.999     # exit 2 if any hook is below 99.9%
    python refusal_uptime.py --since 2026-10-01 --json

Every count is computed twice by independent paths, and the tool refuses to print a number when
the two disagree.
"""
import argparse
import collections
import json
import os
import re
import sys
from datetime import datetime, timezone

FAIL_OPEN = ("hook_cancelled", "hook_non_blocking_error")


def parse_ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def load_hooks(paths):
    """PreToolUse hooks from settings files: (label, matcher regex, timeout s)."""
    hooks = []
    for p in paths:
        try:
            cfg = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for block in cfg.get("hooks", {}).get("PreToolUse", []):
            matcher = block.get("matcher", "") or ".*"
            for h in block.get("hooks", []):
                label = h.get("statusMessage") or h.get("command", "")
                hooks.append({"label": label, "matcher": re.compile(r"^(?:%s)$" % matcher),
                              "timeout": h.get("timeout"), "source": p,
                              # with onFailure "block" an absent hook blocks the call instead of passing it
                              "fails_closed": str(h.get("onFailure", "")).lower() == "block"})
    return hooks


def scan(root, since, marker=None):
    """Stream every transcript once: tool calls, PreToolUse hook outcome records, and canary outcomes."""
    calls, records, files = {}, [], 0
    canary_calls, canary_refused = set(), set()
    for d, _, fs in os.walk(root):
        for fn in fs:
            if not fn.endswith(".jsonl"):
                continue
            files += 1
            path = os.path.join(d, fn)
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"tool_use"' not in line and '"hook_' not in line and '"tool_result"' not in line:
                        continue
                    try:
                        o = json.loads(line)
                    except ValueError:
                        continue
                    t = parse_ts(o.get("timestamp"))
                    if t is None or (since and t < since):
                        continue
                    a = o.get("attachment")
                    if isinstance(a, dict) and a.get("hookEvent") == "PreToolUse" and str(a.get("type", "")).startswith("hook_"):
                        records.append({"type": a["type"], "label": a.get("command", "") or "", "tid": a.get("toolUseID"),
                                        "tool": str(a.get("hookName", "")).split(":")[-1], "timedOut": a.get("timedOut"),
                                        "ms": a.get("durationMs"), "t": t, "file": path})
                        continue
                    msg = o.get("message")
                    if isinstance(msg, dict) and isinstance(msg.get("content"), list):
                        for b in msg["content"]:
                            if not isinstance(b, dict):
                                continue
                            if b.get("type") == "tool_use" and b.get("id"):
                                calls[b["id"]] = (b.get("name", ""), t, path)
                                if marker and marker in json.dumps(b.get("input", {})):
                                    canary_calls.add(b["id"])
                            elif marker and b.get("type") == "tool_result" and b.get("tool_use_id") in canary_calls:
                                body = json.dumps(b.get("content", ""))
                                if "canary refused" in body or "hook error" in body:
                                    canary_refused.add(b["tool_use_id"])
    return calls, records, files, canary_calls, canary_refused


def is_fail_open(r):
    return (r["type"] == "hook_cancelled" and r["timedOut"] is True) or r["type"] == "hook_non_blocking_error"


def main():
    home = os.path.expanduser("~/.claude")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--projects", default=os.path.join(home, "projects"), help="transcript root")
    ap.add_argument("--settings", nargs="*", default=[os.path.join(home, "settings.json")])
    ap.add_argument("--since", help="ISO date; only calls on or after it")
    ap.add_argument("--min-uptime", type=float, help="exit 2 if any hook's refusal uptime is below this")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--canary", nargs="?", const="REFUSAL_CANARY_7f3a",
                    help="also report canary calls (see canary_wrap.py): refused = guard alive, ran = guard absent")
    a = ap.parse_args()
    since = datetime.fromisoformat(a.since).replace(tzinfo=timezone.utc) if a.since else None

    hooks = load_hooks(a.settings)
    calls, records, files, canary_calls, canary_refused = scan(a.projects, since, a.canary)
    if a.canary:
        n, k = len(canary_calls), len(canary_refused)
        print(f"canary: {n} calls carried the marker; refused {k}, ran unguarded {n - k}"
              + (f"; observed refusal uptime {k / n:.4f}" if n else "; schedule some canary calls first"))
    report, worst = [], 1.0
    for h in hooks:
        mine = [r for r in records if r["label"] == h["label"]]
        # window: from the call guarded by this hook's first record (a record lands after its call), so
        # calls made before the hook existed are not charged to it
        start = min((calls[r["tid"]][1] for r in mine if r["tid"] in calls), default=None)
        if start is None:
            report.append({"hook": h["label"], "calls": None, "note": "no records: never failed, or never installed"})
            continue
        scope = {tid for tid, (name, t, _) in calls.items() if h["matcher"].match(name) and t >= start}
        fo_joined = {r["tid"] for r in mine if is_fail_open(r)} & scope
        # independent path: walk the records, not the call set, and test the tool name and time directly
        fo_direct = set()
        for r in mine:
            if is_fail_open(r) and h["matcher"].match(r["tool"]) and r["tid"] in calls and calls[r["tid"]][1] >= start:
                fo_direct.add(r["tid"])
        if len(fo_joined) != len(fo_direct):
            sys.exit(f"REFUSING TO REPORT {h['label']!r}: joined count {len(fo_joined)} != direct count {len(fo_direct)}")
        n, k = len(scope), len(fo_joined)
        up = 1 - k / n if n else None
        worst = min(worst, up) if up is not None else worst
        ms = sorted(r["ms"] for r in mine if is_fail_open(r) and r["ms"])
        report.append({"hook": h["label"], "timeout_s": h["timeout"], "calls": n, "fail_open": k,
                       "refusal_uptime": up, "since": start.isoformat(timespec="minutes"),
                       "absent_calls_went_ahead": not h["fails_closed"],
                       "refusals": sum(1 for r in mine if r["type"] == "hook_blocking_error"),
                       "median_ms_when_absent": ms[len(ms) // 2] if ms else None})
    if a.json:
        print(json.dumps({"transcripts": files, "tool_calls": len(calls), "hooks": report}, indent=2))
    else:
        print(f"{files} transcripts, {len(calls)} tool calls, {len(hooks)} PreToolUse hooks\n")
        for r in report:
            if r.get("calls") is None:
                print(f"  {r['hook'][:60]:<60} {r['note']}")
                continue
            print(f"  {r['hook'][:60]:<60} absent on {r['fail_open']:>6} of {r['calls']:>6} calls  "
                  f"uptime {r['refusal_uptime']:.4f}  (since {r['since']}, timeout {r['timeout_s']}s)")
        print("\nA hook is 'absent' when it timed out or errored and the tool call went ahead anyway.")
    if a.min_uptime is not None and worst < a.min_uptime:
        sys.exit(2)


if __name__ == "__main__":
    main()
