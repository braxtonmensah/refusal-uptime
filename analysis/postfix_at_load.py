"""silicyte-0048: guard presence after the one-process fix, stratified by concurrency.

Concurrency = transcript files (sessions and subagents) with a tool call in the same 10-minute
UTC bucket, the definition used by PREREG_REFUSAL_UPTIME and the technical note.
Two independent counts: (1) transcripts (fail-open PreToolUse records joined to calls, and walked
directly), (2) the dispatcher's own log, one row per call it actually ran.
"""
import collections, json, os, re, sys
from datetime import datetime, timezone, timedelta

HOME = os.path.expanduser("~/.claude")
SINCE = datetime(2026, 10, 23, 15, 38, tzinfo=timezone.utc)
# optional end of window, ISO UTC (e.g. 2026-10-25T18:25), so an earlier read can be reproduced exactly
END = datetime.fromisoformat(sys.argv[1]).replace(tzinfo=timezone.utc) if len(sys.argv) > 1 else None
ET_OFFSET = timedelta(hours=4)  # EDT until 2026-11-01
FAIL = ("hook_cancelled", "hook_non_blocking_error")


def ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


cfg = json.load(open(os.path.join(HOME, "settings.json"), encoding="utf-8"))
blocks = cfg["hooks"]["PreToolUse"]
disp = [b for b in blocks if any("guard_dispatch" in json.dumps(h) for h in b["hooks"])]
assert len(disp) == 1, disp
matcher = re.compile(r"^(?:%s)$" % disp[0]["matcher"])

calls = {}            # tid -> (name, t, path)
recs = []             # fail-open PreToolUse records
pre_records = collections.Counter()
files = 0
for d, _, fs in os.walk(os.path.join(HOME, "projects")):
    for fn in fs:
        if not fn.endswith(".jsonl"):
            continue
        p = os.path.join(d, fn)
        try:
            if datetime.fromtimestamp(os.path.getmtime(p), timezone.utc) < SINCE:
                continue
        except OSError:
            continue
        files += 1
        with open(p, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"tool_use"' not in line and '"hook_' not in line:
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                t = ts(o.get("timestamp"))
                if t is None or t < SINCE or (END and t >= END):
                    continue
                a = o.get("attachment")
                if isinstance(a, dict) and a.get("hookEvent") == "PreToolUse" and str(a.get("type", "")).startswith("hook_"):
                    pre_records[a["type"]] += 1
                    fo = (a["type"] == "hook_cancelled" and a.get("timedOut") is True) or a["type"] == "hook_non_blocking_error"
                    if a["type"] in FAIL:
                        recs.append({"type": a["type"], "fo": fo, "tid": a.get("toolUseID"),
                                     "tool": str(a.get("hookName", "")).split(":")[-1], "label": str(a.get("command", ""))[:120],
                                     "t": t, "ms": a.get("durationMs"), "path": p})
                    continue
                m = o.get("message")
                if isinstance(m, dict) and isinstance(m.get("content"), list):
                    for b in m["content"]:
                        if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id"):
                            calls[b["id"]] = (b.get("name", ""), t, p)

bucket = lambda t: int(t.timestamp() // 600)
active = collections.defaultdict(set)
for name, t, p in calls.values():
    active[bucket(t)].add(p)
conc = {k: len(v) for k, v in active.items()}


def bin_of(c):
    return "1" if c == 1 else "2-3" if c <= 3 else "4-6" if c <= 6 else "7-10" if c <= 10 else "11+"


BINS = ["1", "2-3", "4-6", "7-10", "11+"]
matched = {tid: v for tid, v in calls.items() if matcher.match(v[0])}
n_bin = collections.Counter(bin_of(conc[bucket(t)]) for (_, t, _) in matched.values())
fo_joined = {r["tid"] for r in recs if r["fo"]} & set(matched)
fo_direct = {r["tid"] for r in recs if r["fo"] and matcher.match(r["tool"]) and r["tid"] in calls}
if len(fo_joined) != len(fo_direct):
    sys.exit(f"REFUSING: joined {len(fo_joined)} != direct {len(fo_direct)}")
k_bin = collections.Counter(bin_of(conc[bucket(matched[tid][1])]) for tid in fo_joined)

# exact-level counts at the top
lvl = collections.Counter(conc[bucket(t)] for (_, t, _) in matched.values())

# independent count: the dispatcher's own log
rows = []
for line in open(os.path.join(HOME, "hooks", "state", "dispatch.jsonl"), encoding="utf-8"):
    try:
        r = json.loads(line)
    except ValueError:
        continue
    t = datetime.strptime(r["ts"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) + ET_OFFSET
    if t >= SINCE and not (END and t >= END):
        rows.append((t, r))
d_bin = collections.Counter()
d_ms = collections.defaultdict(list)
d_err = collections.Counter()
for t, r in rows:
    c = conc.get(bucket(t))
    b = bin_of(c) if c else "none"
    d_bin[b] += 1
    d_ms[b].append(r.get("ms") or 0.0)
    if r.get("err"):
        d_err[b] += 1


def wilson_hi(k, n, z=1.959964):
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    c = p + z * z / (2 * n)
    s = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (c + s) / den


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None


last = max(t for (_, t, _) in calls.values())
print(f"window {SINCE.isoformat()} .. {last.isoformat(timespec='minutes')} UTC; transcripts {files}; tool calls {len(calls)}; matched {len(matched)}")
print(f"PreToolUse hook records by type: {dict(pre_records)}")
print(f"fail-open PreToolUse records: {sum(r['fo'] for r in recs)} (joined to matched calls {len(fo_joined)}, direct {len(fo_direct)})")
for r in recs:
    print("   ", r["type"], r["tool"], r["t"].isoformat(timespec="seconds"), r["ms"], r["label"][:70], os.path.basename(r["path"])[:12])
print("\nbin    matched  fail-open  share   wilson95hi   dispatcher_rows  disp_p50ms  disp_p95ms  disp_max  disp_err")
for b in BINS:
    n, k = n_bin[b], k_bin[b]
    print(f"{b:<6} {n:>7} {k:>9}  {k / n if n else float('nan'):.4f}  {wilson_hi(k, n) or float('nan'):.4f}    {d_bin[b]:>8}"
          f"   {pct(d_ms[b], .5) or 0:>9.1f}  {pct(d_ms[b], .95) or 0:>9.1f}  {max(d_ms[b] or [0]):>8.1f}  {d_err[b]:>5}")
print(f"dispatcher rows in buckets with no transcript call: {d_bin['none']}")
print(f"total check: matched {sum(n_bin.values())} == {len(matched)}; dispatcher rows {sum(d_bin.values())} == {len(rows)}")
print("\nexact concurrency levels >= 9 (matched calls):", sorted((c, n) for c, n in lvl.items() if c >= 9))
print("max concurrency:", max(conc.values()))
top = [k for k, v in conc.items() if v >= 11]
print("buckets at 11+:", len(top), "first/last:", (datetime.fromtimestamp(min(top) * 600, timezone.utc).isoformat() if top else None),
      (datetime.fromtimestamp(max(top) * 600, timezone.utc).isoformat() if top else None))
n11, k11 = n_bin["11+"], k_bin["11+"]
verdict = "UNDERPOWERED" if n11 < 500 else ("PASS" if k11 / n11 <= 0.02 else "FAIL")
print(f"\nsilicyte-0048 q = {k11}/{n11} = {k11 / n11 if n11 else float('nan'):.5f}  VERDICT {verdict}")

# same-denominator comparison with the pre-fix gpu_before_cpu series (Bash + PowerShell only)
sh = {tid: v for tid, v in matched.items() if v[0] in ("Bash", "PowerShell")}
n_sh = collections.Counter(bin_of(conc[bucket(t)]) for (_, t, _) in sh.values())
k_sh = collections.Counter(bin_of(conc[bucket(sh[tid][1])]) for tid in fo_joined if tid in sh)
print("\nBash+PowerShell only (pre-fix gpu_before_cpu denominator):")
for b in BINS:
    n, k = n_sh[b], k_sh[b]
    print(f"  {b:<6} {k}/{n}  wilson95hi {wilson_hi(k, n) or float('nan'):.4f}")
print(f"  total {sum(k_sh.values())}/{sum(n_sh.values())}")

# silicyte-0049: the post-fix 11+ buckets one by one (bucket = 10-minute UTC window, same grid as the pre-fix analysis)
print("\npost-fix 11+ buckets (silicyte-0049): start ET, transcripts active, shell calls absent/total, all matched absent/total")
k_clean = k_q = 0
for b in sorted(k for k, v in conc.items() if v >= 11):
    sh_b = [tid for tid, v in sh.items() if bucket(v[1]) == b]
    m_b = [tid for tid, v in matched.items() if bucket(v[1]) == b]
    a_sh = sum(tid in fo_joined for tid in sh_b)
    a_m = sum(tid in fo_joined for tid in m_b)
    start_et = datetime.fromtimestamp(b * 600, timezone.utc) - ET_OFFSET
    print(f"  {start_et:%m-%d %H:%M} ET  active {conc[b]:>2}  shell {a_sh}/{len(sh_b)}  all {a_m}/{len(m_b)}")
    if len(sh_b) >= 20:
        k_q += 1
        k_clean += a_sh == 0
print(f"  buckets with >=20 shell calls: {k_q}; clean: {k_clean}")
