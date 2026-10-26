"""silicyte-0049: window-level view of compute-guard absence at 11+ concurrency, before the fix.

Answers the clustering objection to the post-fix "0 of 1,184": calls inside one 10-minute bucket are
not independent, so compare buckets, not calls. Loaders and definitions are uptime.py's: all tool
calls from calls.tsv, gpu_before_cpu records from hookfail.tsv, window A from the call guarded by the
guard's first record, concurrency = transcript files with ANY tool call in the same 10-minute bucket.

usage: python window.py <data_dir>
"""
import collections
import json
import sys
from datetime import datetime
from math import comb

data = sys.argv[1]
SHELL = {"Bash", "PowerShell"}
IDENT = "Checking GPU-before-CPU"


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


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

fo, gtids = set(), []
for line in open(f"{data}/hookfail.tsv", encoding="utf-8", errors="replace"):
    _, _, js = line.rstrip("\n").partition("\t")
    try:
        a = json.loads(js).get("attachment", {})
    except ValueError:
        continue
    if a.get("hookEvent") != "PreToolUse" or not str(a.get("command", "") or "").startswith(IDENT):
        continue
    gtids.append(a.get("toolUseID"))
    if (a.get("type") == "hook_cancelled" and a.get("timedOut") is True) or a.get("type") == "hook_non_blocking_error":
        fo.add(a.get("toolUseID"))
startA = min(calls[t][2] for t in gtids if t in calls)


def bucket(t):
    return t.replace(minute=t.minute - t.minute % 10, second=0, microsecond=0)


active = collections.defaultdict(set)
for f, name, t in calls.values():
    active[bucket(t)].add(f)

rows = [(tid, t) for tid, (f, name, t) in calls.items() if name in SHELL and t >= startA]
tot = len(rows)
absent = sum(tid in fo for tid, _ in rows)
hi = [(tid, t) for tid, t in rows if len(active[bucket(t)]) >= 11]
print(f"window A from {startA:%Y-%m-%d %H:%M} UTC; shell calls {tot}, absent {absent} (expect 30,929 of 103,850)")
print(f"11+ (all-tool concurrency): absent {sum(t in fo for t, _ in hi)} of {len(hi)} (expect 28,569 of 53,831)")

# independent second path for the 11+ total: walk buckets, not calls
per = collections.defaultdict(lambda: [0, 0])
for tid, t in rows:
    b = bucket(t)
    per[b][1] += 1
    per[b][0] += tid in fo
hi_b = {b: v for b, v in per.items() if len(active[b]) >= 11}
print(f"  second path, summed over {len(hi_b)} buckets at 11+: {sum(v[0] for v in hi_b.values())} of "
      f"{sum(v[1] for v in hi_b.values())}")


def summarize(label, sel):
    q_n = len(sel)
    z = sum(1 for v in sel.values() if v[0] == 0)
    shares = sorted(v[0] / v[1] for v in sel.values())
    med = shares[len(shares) // 2] if shares else None
    under1 = sum(1 for s in shares if s < 0.01)
    print(f"{label}: {q_n} buckets with >=20 shell calls; zero-absence buckets {z} (q = {z / q_n if q_n else float('nan'):.4f}); "
          f"under 1% absent {under1}; median share {med:.3f}" if q_n else f"{label}: no buckets")
    return q_n, z


qual = {b: v for b, v in hi_b.items() if v[1] >= 20}
N, Z = summarize("PRIMARY 11+", qual)
N2, Z2 = summarize("like-for-like 11-20", {b: v for b, v in qual.items() if len(active[b]) <= 20})
N3, Z3 = summarize("7-10 (reference)", {b: v for b, v in per.items() if 7 <= len(active[b]) <= 10 and v[1] >= 20})
by_day = collections.Counter(b.strftime("%m-%d") for b in qual)
print("qualifying 11+ buckets by UTC day:", dict(sorted(by_day.items())))
for k in range(1, 9):
    q = Z / N
    hyper = comb(Z, k) / comb(N, k) if N >= k else float("nan")
    print(f"  k={k}: q^k = {q ** k:.3e}; draw-without-replacement P(all {k} clean) = {hyper:.3e}")
print("JSON " + json.dumps({"N": N, "Z": Z, "q": Z / N, "N_11_20": N2, "Z_11_20": Z2, "N_7_10": N3, "Z_7_10": Z3}))
