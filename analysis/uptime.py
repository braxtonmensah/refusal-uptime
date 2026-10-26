"""Refusal uptime: how often did each PreToolUse guard actually run on the calls it exists to check?

Reads the compact extracts from extract.sh. Pre-registered in PREREG_REFUSAL_UPTIME.md
(silicyte-0029 Q1, silicyte-0030 Q2). Every headline count goes through aggcheck with an
independently computed second count.

usage: python uptime.py <data_dir> <aggcheck_dir>
"""
import collections
import json
import sys
from datetime import datetime, timedelta, timezone

data, agg = sys.argv[1], sys.argv[2]
sys.path.insert(0, agg)
from aggcheck import count  # noqa: E402

GUARDS = {
    # name: (tools it always matched, how its records identify it, window-B start = script creation, UTC)
    "gpu_before_cpu": ({"Bash", "PowerShell"}, lambda c: c.startswith("Checking GPU-before-CPU"),
                       datetime(2026, 9, 30, 18, 53, 14, tzinfo=timezone.utc)),
    "no_poll": ({"Bash", "PowerShell"}, lambda c: c.startswith("Checking no-polling"),
                datetime(2026, 10, 17, 11, 6, 26, tzinfo=timezone.utc)),
    "stamp_guard": ({"Write", "Edit"}, lambda c: "stamp_guard" in c,
                    datetime(2026, 10, 19, 10, 43, 26, tzinfo=timezone.utc)),
}


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---- tool calls
calls = {}
for line in open(f"{data}/calls.tsv", encoding="utf-8", errors="replace"):
    p = line.rstrip("\n").split("\t")
    if len(p) != 4:
        continue
    f, tid, name, t = p
    try:
        calls[tid] = (f, name, ts(t))
    except ValueError:
        pass
print(f"tool calls parsed: {len(calls)} distinct ids from {len({v[0] for v in calls.values()})} transcript files")

# ---- guard failure records
events = []
bad = 0
for line in open(f"{data}/hookfail.tsv", encoding="utf-8", errors="replace"):
    f, _, js = line.rstrip("\n").partition("\t")
    try:
        o = json.loads(js)
    except ValueError:
        bad += 1
        continue
    a = o.get("attachment", {})
    events.append({"file": f, "type": a.get("type"), "hookName": a.get("hookName", ""), "event": a.get("hookEvent"),
                   "tid": a.get("toolUseID"), "cmd": a.get("command", "") or "", "timedOut": a.get("timedOut"),
                   "dur": a.get("durationMs"), "t": ts(o["timestamp"]) if o.get("timestamp") else None})
print(f"guard failure/deny records: {len(events)} parsed, {bad} unparseable")
print("by type:", dict(collections.Counter(e["type"] for e in events)))
print("cancelled with timedOut true / other:",
      sum(1 for e in events if e["type"] == "hook_cancelled" and e["timedOut"] is True),
      sum(1 for e in events if e["type"] == "hook_cancelled" and e["timedOut"] is not True))

results = set(l.rstrip("\n").split("\t")[1] for l in open(f"{data}/results.tsv", encoding="utf-8", errors="replace") if "\t" in l)
hookerr = set(l.rstrip("\n").split("\t")[1] for l in open(f"{data}/results_hookerr.tsv", encoding="utf-8", errors="replace") if "\t" in l)


def failopen(e):
    return (e["type"] == "hook_cancelled" and e["timedOut"] is True) or e["type"] == "hook_non_blocking_error"


# minute bucket concurrency: distinct transcript files with a tool call in the same 10-minute bucket
def bucket(t):
    return t.replace(minute=t.minute - t.minute % 10, second=0, microsecond=0)


active = collections.defaultdict(set)
for tid, (f, name, t) in calls.items():
    active[bucket(t)].add(f)


def cbin(n):
    return "1" if n == 1 else "2-3" if n <= 3 else "4-6" if n <= 6 else "7-10" if n <= 10 else "11+"


BINS = ["1", "2-3", "4-6", "7-10", "11+"]
out = {}
for g, (tools, ident, startB) in GUARDS.items():
    gev = [e for e in events if e["event"] == "PreToolUse" and ident(e["cmd"])]
    if not gev:
        print(f"\n== {g}: no records"); continue
    # window A opens at the CALL time of the guard's earliest record (a hook record lands after its call)
    startA = min(calls[e["tid"]][2] for e in gev if e["tid"] in calls)
    fo_ids = {e["tid"] for e in gev if failopen(e)}
    deny_ids = {e["tid"] for e in gev if e["type"] == "hook_blocking_error"}
    print(f"\n== {g}: tools {sorted(tools)}; window A from first record {startA:%Y-%m-%d %H:%M} UTC; "
          f"window B from script creation {startB:%Y-%m-%d %H:%M} UTC")
    for wname, start in (("A", startA), ("B", startB)):
        rows = [{"tid": tid, "name": n, "t": t, "f": f} for tid, (f, n, t) in calls.items() if n in tools and t >= start]
        primary = lambda r: r["tid"] in fo_ids  # noqa: E731  joined through tool-call ids
        # independent: count fail-open records directly (dedup by id) whose hookName tool is in scope and time in window
        direct = {e["tid"] for e in gev if failopen(e) and e["hookName"].split(":")[-1] in tools and e["t"] and e["t"] >= start}
        indep = lambda r: r["tid"] in direct  # noqa: E731
        c = count(rows, primary, indep, f"{g} fail-open, window {wname}")
        orphans = len(direct - {r["tid"] for r in rows})
        print("  ", c, f"| fail-open records with no matching call: {orphans}")
        out[(g, wname)] = (c.n, c.total)
        if wname == "A":
            ran = sum(1 for r in rows if r["tid"] in fo_ids and r["tid"] in results and r["tid"] not in hookerr)
            print(f"   of the fail-open calls, tool result present and not a hook block (the call ran unguarded): "
                  f"{ran} of {c.n}")
            print(f"   explicit refusals (guard alive and said no): {sum(1 for r in rows if r['tid'] in deny_ids)}")
            byb = collections.defaultdict(lambda: [0, 0])
            for r in rows:
                b = cbin(len(active[bucket(r["t"])]))
                byb[b][1] += 1
                byb[b][0] += r["tid"] in fo_ids
            print("   by concurrency (files active in the same 10 min):",
                  ", ".join(f"{b}: {byb[b][0]}/{byb[b][1]} = {byb[b][0]/byb[b][1]:.3f}" for b in BINS if byb[b][1]))
            byd = collections.defaultdict(lambda: [0, 0])
            for r in rows:
                d = (r["t"] - timedelta(hours=4)).strftime("%m-%d")  # ET date
                byd[d][1] += 1
                byd[d][0] += r["tid"] in fo_ids
            print("   by ET day:", ", ".join(f"{d}: {v[0]}/{v[1]}" for d, v in sorted(byd.items())))
            top2 = sorted(byd, key=lambda d: -byd[d][1])[:2]
            for d in top2:
                wb = collections.defaultdict(lambda: [0, 0])
                for r in rows:
                    if (r["t"] - timedelta(hours=4)).strftime("%m-%d") == d:
                        b = cbin(len(active[bucket(r["t"])]))
                        wb[b][1] += 1
                        wb[b][0] += r["tid"] in fo_ids
                print(f"   within {d} (control for date):",
                      ", ".join(f"{b}: {wb[b][0]}/{wb[b][1]} = {wb[b][0]/wb[b][1]:.3f}" for b in BINS if wb[b][1]))
            durs = sorted(e["dur"] for e in gev if e["type"] == "hook_cancelled" and e["timedOut"] and e["dur"])
            if durs:
                print(f"   timed-out guard durations ms: median {durs[len(durs)//2]}, max {durs[-1]}, n {len(durs)}")

json.dump({f"{g}|{w}": v for (g, w), v in out.items()}, open(f"{data}/uptime_summary.json", "w"))
print("\nUPTIME_DONE")
