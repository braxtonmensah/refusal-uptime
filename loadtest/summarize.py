"""Combine the sweep's rows and apply the gate registered before the first run (silicyte-0052).

G1, the premise: on windows-2025 with normal memory, five per-call guard processes, 12 agents, the absence rate is
at least 2% at a 15 s budget or at least 5% at a 5 s budget, AND at least 3x the 1-agent rate, in at least 2 of 3
repeats. Exactly 1 of 3 is INCONCLUSIVE (rerun with 6 repeats). 0 of 3 is FAIL: on a clean runner, load alone does
not make these guards vanish.

usage: python summarize.py <combined.jsonl> <summary.md>
"""
import json
import statistics
import sys
from collections import defaultdict

rows = [json.loads(x) for x in open(sys.argv[1]) if x.strip()]
for r in rows:
    os_, mem, rep = (r.get("label", "") + "///").split("/")[:3]
    r["os_"], r["mem"], r["rep"] = os_, mem, rep

by = defaultdict(list)
for r in rows:
    by[(r["os_"], r["mem"], r["form"], r["agents"])].append(r)

out = ["# Guard presence under load: results", "",
       "Absence at budget B = share of tool calls whose slowest guard process took longer than B. "
       "Median over repeats; per-repeat values in brackets.", "",
       "| runner | memory | form | agents | per core | calls | p95 s | absent at 5 s | absent at 10 s | absent at 15 s |",
       "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
for key in sorted(by):
    g = by[key]
    med = lambda f: statistics.median(x[f] for x in g)
    reps = lambda f: "[" + ", ".join(f"{x[f]:.4f}" for x in sorted(g, key=lambda x: x["rep"])) + "]"
    out.append(f"| {key[0]} | {key[1]} | {key[2]} | {key[3]} | {g[0]['per_core']} | {sum(x['calls'] for x in g)} | "
               f"{med('p95_s'):.3f} | {med('rate_at_5s'):.4f} {reps('rate_at_5s')} | {med('rate_at_10s'):.4f} | "
               f"{med('rate_at_15s'):.4f} {reps('rate_at_15s')} |")


def gate(os_, mem):
    qualify, detail = 0, []
    reps = sorted({r["rep"] for r in rows if r["os_"] == os_ and r["mem"] == mem and r["form"] == "per-call"})
    for rep in reps:
        pick = {r["agents"]: r for r in rows
                if r["os_"] == os_ and r["mem"] == mem and r["form"] == "per-call" and r["rep"] == rep}
        if 12 not in pick or 1 not in pick:
            detail.append(f"{rep}: missing level")
            continue
        a, b = pick[12], pick[1]
        hit = (a["rate_at_15s"] >= 0.02 or a["rate_at_5s"] >= 0.05)
        ratio_ok = a["rate_at_15s"] >= 3 * b["rate_at_15s"] and a["rate_at_5s"] >= 3 * b["rate_at_5s"]
        ok = hit and ratio_ok
        qualify += ok
        detail.append(f"{rep}: N=12 rate@15s {a['rate_at_15s']:.4f}, rate@5s {a['rate_at_5s']:.4f}; "
                      f"N=1 rate@15s {b['rate_at_15s']:.4f}, rate@5s {b['rate_at_5s']:.4f} -> {'qualifies' if ok else 'no'}")
    n = len(reps)
    verdict = "PASS" if qualify >= 2 else ("INCONCLUSIVE" if qualify == 1 else "FAIL")
    if n < 3:
        verdict = f"UNDERPOWERED ({n} repeats)"
    return verdict, qualify, n, detail


out += ["", "## Gate G1 (registered silicyte-0052): windows-2025, normal memory, per-call, 12 agents", ""]
v, k, n, d = gate("windows-2025", "normal")
out.append(f"**{v}**: {k} of {n} repeats qualify.")
out += [f"- {x}" for x in d]
out += ["", "## Not gated: the same test under about 1 GB of free memory", ""]
for os_ in ("windows-2025", "ubuntu-24.04"):
    v, k, n, d = gate(os_, "low1gb")
    out.append(f"- {os_}, low memory: would read **{v}** ({k} of {n})")
open(sys.argv[2], "w").write("\n".join(out) + "\n")
print("\n".join(out))
