"""silicyte-0055: post-fix sustained-episode re-read (PREREG_POSTFIX_EPISODES_2026-10-25.md). Runs on Quartz, never on the laptop.

Runs postfix_at_load.py unchanged (same concurrency, matcher and fail-open definitions) on a copied ~/.claude, then
builds 11+ episodes post-fix, and pre-fix from window.py's data, with one definition for both.
Episode = maximal run of consecutive 10-minute UTC buckets at 11+; sustained = >= 5 buckets and >= 20 shell calls.
Revised before the read after an independent audit (workflow wf_86d3f646-3cd): FAIL takes precedence over UNDERPOWERED,
the headline Fisher p uses the registered 0 of 21, the pre-fix data must reproduce window_0049.out and episodes_0049.out,
and non-shell dispatcher absences, dispatcher-row integrity and window-end truncation are shown per episode.

usage (from the folder holding this script, postfix_at_load.py and window.py):
  HOME=<dir holding the copied .claude> python postfix_episodes.py <END iso UTC> <pre-fix data dir>
"""
import collections
import contextlib
import io
import os
import runpy
import sys
from datetime import datetime, timezone
from math import comb

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
end, data = sys.argv[1], os.path.abspath(sys.argv[2])
end_bucket = int(datetime.fromisoformat(end).replace(tzinfo=timezone.utc).timestamp() // 600)

buf = io.StringIO()
sys.argv = ["postfix_at_load.py", end]
with contextlib.redirect_stdout(buf):
    g = runpy.run_path(os.path.join(HERE, "postfix_at_load.py"))
open(os.path.join(HERE, "postfix_at_load_reread.out"), "w", encoding="utf-8").write(buf.getvalue())
conc, sh, fo, bucket, calls, recs = g["conc"], g["sh"], g["fo_joined"], g["bucket"], g["calls"], g["recs"]
matched, ET = g["matched"], g["ET_OFFSET"]
d_rows = collections.Counter(bucket(t) for t, _ in g["rows"])
m_cnt = collections.Counter(bucket(v[1]) for v in matched.values())


def episodes(keys):
    eps, cur = [], []
    for b in sorted(keys):
        if cur and b - cur[-1] != 1:
            eps.append(cur)
            cur = []
        cur.append(b)
    if cur:
        eps.append(cur)
    return eps


def at_et(b):
    return (datetime.fromtimestamp(b * 600, timezone.utc) - ET).strftime("%m-%d %H:%M")


def fisher(n_pre, q_pre, n_post, q_post):
    """One-sided: P(post clean count >= q_post | margins), right tail of the hypergeometric."""
    if not n_post:
        return float("nan")
    N, K = n_pre + n_post, q_pre + q_post
    return sum(comb(K, k) * comb(N - K, n_post - k) for k in range(q_post, min(K, n_post) + 1)) / comb(N, n_post)


# ---- post-fix
per = collections.defaultdict(lambda: [0, 0])
for tid, (name, t, p) in sh.items():
    per[bucket(t)][1] += 1
    per[bucket(t)][0] += tid in fo
all_n = collections.Counter(bucket(t) for (_, t, _) in calls.values())
post = []
for e in episodes([b for b, c in conc.items() if c >= 11]):
    es = set(e)
    n, a = sum(per[b][1] for b in e), sum(per[b][0] for b in e)
    post.append({"_b": es, "start": at_et(e[0]), "end": at_et(e[-1]), "buckets": len(e), "peak": max(conc[b] for b in e),
                 "shell_n": n, "shell_absent": a, "sustained": len(e) >= 5 and n >= 20,
                 "all_absent": sum(1 for tid in fo if bucket(matched[tid][1]) in es),
                 "matched": sum(m_cnt[b] for b in e), "disp_rows": sum(d_rows[b] for b in e),
                 "end_truncated": e[-1] == end_bucket - 1,
                 "calls_per_transcript": sum(all_n[b] for b in e) / sum(conc[b] for b in e)})
print("--- postfix_at_load.py output (silicyte-0048 definitions; its VERDICT line is NOT the 0055 gate) ---")
print(buf.getvalue())
print("\nPOST-FIX 11+ episodes: start..last bucket ET, buckets, peak, shell absent/calls, all matched absent, "
      "dispatcher rows/matched calls, calls per transcript-bucket")
for x in post:
    print(f"  {x['start']} .. {x['end']}  {x['buckets']:>3} buckets  peak {x['peak']:>2}  shell {x['shell_absent']}/{x['shell_n']}"
          f"  all-absent {x['all_absent']}  disp/matched {x['disp_rows']}/{x['matched']}  {x['calls_per_transcript']:.1f}"
          f"  {'SUSTAINED' if x['sustained'] else ''}{'  END-TRUNCATED' if x['end_truncated'] else ''}")
sus = [x for x in post if x["sustained"]]
n_post, q_post = len(sus), sum(x["shell_absent"] == 0 for x in sus)
print("post sustained median calls per transcript-bucket:",
      f"{sorted(x['calls_per_transcript'] for x in sus)[len(sus) // 2]:.1f}" if sus else "none")

# exact levels above 20, shell calls
lv_sh = collections.Counter()
lv_ab = collections.Counter()
for tid, (name, t, p) in sh.items():
    c = conc[bucket(t)]
    k = "21-29" if 21 <= c <= 29 else "30+" if c >= 30 else None
    if k:
        lv_sh[k] += 1
        lv_ab[k] += tid in fo
print("\nshell calls above 20 active (post-fix): " + ", ".join(f"{k}: {lv_ab[k]}/{lv_sh[k]}" for k in ("21-29", "30+")))
print("max post-fix concurrency:", max(conc.values()))

# ---- pre-fix, from window.py's state (same data and loaders as silicyte-0049); must reproduce the published series
wbuf = io.StringIO()
sys.argv = ["window.py", data]
with contextlib.redirect_stdout(wbuf):
    w = runpy.run_path(os.path.join(HERE, "window.py"))
wtxt = wbuf.getvalue()
print("\n--- window.py (pre-fix) ---\n" + wtxt)
if "shell calls 103850, absent 30929" not in wtxt or "absent 28569 of 53831" not in wtxt:
    sys.exit("REFUSING: data dir does not reproduce window_0049.out")
wper, wact, wcalls, startA = w["per"], w["active"], w["calls"], w["startA"]
idx = lambda b: int(b.timestamp() // 600)
wall = collections.Counter(idx(w["bucket"](t)) for (_, _, t) in wcalls.values())
wper_i = {idx(b): v for b, v in wper.items()}
wact_i = {idx(b): len(v) for b, v in wact.items()}
a0 = idx(w["bucket"](startA))


def pre_eps(keys):
    out = []
    for e in episodes(keys):
        n, a = sum(wper_i.get(b, [0, 0])[1] for b in e), sum(wper_i.get(b, [0, 0])[0] for b in e)
        out.append({"buckets": len(e), "shell_n": n, "shell_absent": a, "sustained": len(e) >= 5 and n >= 20,
                    "calls_per_transcript": sum(wall[b] for b in e) / sum(wact_i[b] for b in e)})
    return out


pub = pre_eps([b for b in wper_i if wact_i[b] >= 11])                     # as published: buckets with shell calls
pub5 = [x for x in pub if x["buckets"] >= 5]
if (len(pub5), sum(x["shell_absent"] == 0 for x in pub5)) != (21, 0):
    sys.exit("REFUSING: pre-fix episodes do not reproduce episodes_0049.out (21 sustained, 0 clean)")
same = pre_eps([b for b, c in wact_i.items() if c >= 11 and b >= a0])    # this read's definition, applied pre-fix
for label, ps in (("pre-fix, published definition (0049, >=5 buckets)", pub5),
                  ("pre-fix, this read's definition", [x for x in same if x["sustained"]])):
    print(f"{label}: sustained {len(ps)}, clean {sum(x['shell_absent'] == 0 for x in ps)}; median calls per "
          f"transcript-bucket {sorted(x['calls_per_transcript'] for x in ps)[len(ps) // 2]:.1f}" if ps else f"{label}: none")
s_pre = [x for x in same if x["sustained"]]
n_pre, q_pre = len(s_pre), sum(x["shell_absent"] == 0 for x in s_pre)

p_prereg = fisher(21, 0, n_post, q_post)
p_same = fisher(n_pre, q_pre, n_post, q_post)
if q_post < n_post:
    verdict = "FAIL" + (" (n<3, also underpowered)" if n_post < 3 else "")
elif n_post < 3:
    verdict = "UNDERPOWERED"
else:
    verdict = "PASS"

fos = [r for r in recs if r["fo"]]
print(f"\nfail-open PreToolUse records in window: {len(fos)} (other hook_cancelled/errors, not fail-open: {len(recs) - len(fos)})")
for r in fos:
    c = calls.get(r["tid"])
    b = bucket(c[1]) if c else None
    ep = next((x["start"] for x in post if b in x["_b"]), "-")
    print("   ", r["type"], r["tool"], (r["t"] - ET).strftime("%m-%d %H:%M:%S ET"), r["ms"], r["label"][:30],
          "| call at", at_et(b) if b is not None else "?", "| conc", conc.get(b), "| episode", ep,
          "| shell" if r["tid"] in sh else "| not-shell")
print(f"\nRESULT n_post = {n_post}, q_post = {q_post}; Fisher one-sided p vs the registered 0 of 21 = {p_prereg:.2e}"
      f" (vs this read's pre-fix definition {q_pre} of {n_pre}: {p_same:.2e}); VERDICT {verdict}")
