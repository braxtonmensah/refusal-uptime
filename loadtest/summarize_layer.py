"""Shell-layer arm: every guard process launched as bash.exe -c "<python> -I <guard>", which is how Claude Code runs a
command-string hook on Windows with Git Bash when no shell is set; Defender real-time protection on vs off, same run.
Applies the gate registered before the first run (silicyte-0054).

G3: windows-2025, normal memory, five per-call guard processes through bash.exe, 12 agents, real-time protection ON
(as verified by the job itself). A repeat qualifies when absence is at least 2% at a 15 s budget or at least 5% at
5 s, AND at least 3x the RTP-OFF rate of the same repeat number at the same level. PASS iff at least 2 of 3 repeats
qualify. A repeat whose job could not turn protection on is VOID; fewer than 2 valid repeats makes the gate VOID.

Labels look like: windows-2025/normal/r1/rtp-on/eff-True/bash
usage: python summarize_layer.py <combined.jsonl> <summary.md>
"""
import json
import statistics
import sys
from collections import defaultdict

rows = [json.loads(x) for x in open(sys.argv[1]) if x.strip()]
for r in rows:
    parts = (r.get("label", "") + "//////").split("/")
    r["os_"], r["mem"], r["rep"], r["av"], r["eff"] = parts[:5]

by = defaultdict(list)
for r in rows:
    by[(r["av"], r["form"], r["agents"])].append(r)

out = ["# Guard presence under load: shell layer, bash.exe -c (windows-2025)", "",
       "Each guard process is started through Git Bash, as the measured laptop's hooks were before 2026-10-23. "
       "Absence at budget B = share of tool calls whose slowest guard process took longer than B. Median over repeats; "
       "per-repeat values in brackets. `eff` = real-time protection as read back by the job.", "",
       "| Defender RTP | form | agents | calls | p95 s [per repeat] | absent at 5 s | absent at 10 s | absent at 15 s | eff |",
       "|---|---|---:|---:|---|---:|---:|---:|---|"]
for key in sorted(by):
    g = sorted(by[key], key=lambda x: x["rep"])
    med = lambda f: statistics.median(x[f] for x in g)
    reps = lambda f, fmt: "[" + ", ".join(format(x[f], fmt) for x in g) + "]"
    out.append(f"| {key[0]} | {key[1]} | {key[2]} | {sum(x['calls'] for x in g)} | "
               f"{med('p95_s'):.3f} {reps('p95_s', '.3f')} | {med('rate_at_5s'):.4f} {reps('rate_at_5s', '.4f')} | "
               f"{med('rate_at_10s'):.4f} | {med('rate_at_15s'):.4f} {reps('rate_at_15s', '.4f')} | "
               f"{','.join(sorted({x['eff'] for x in g}))} |")


def gate():
    qualify, valid, detail = 0, 0, []
    for rep in ("r1", "r2", "r3"):
        on = [r for r in rows if r["av"] == "rtp-on" and r["form"] == "per-call" and r["rep"] == rep and r["agents"] == 12]
        off = [r for r in rows if r["av"] == "rtp-off" and r["form"] == "per-call" and r["rep"] == rep and r["agents"] == 12]
        if not on or not off:
            detail.append(f"{rep}: missing")
            continue
        a, b = on[0], off[0]
        if a["eff"] != "eff-True":
            detail.append(f"{rep}: VOID (protection read back as {a['eff']})")
            continue
        valid += 1
        hit = a["rate_at_15s"] >= 0.02 or a["rate_at_5s"] >= 0.05
        ratio = a["rate_at_15s"] >= 3 * b["rate_at_15s"] and a["rate_at_5s"] >= 3 * b["rate_at_5s"]
        ok = hit and ratio
        qualify += ok
        detail.append(f"{rep}: ON rate@15s {a['rate_at_15s']:.4f} rate@5s {a['rate_at_5s']:.4f} p95 {a['p95_s']:.3f}; "
                      f"OFF rate@15s {b['rate_at_15s']:.4f} rate@5s {b['rate_at_5s']:.4f} p95 {b['p95_s']:.3f} "
                      f"-> {'qualifies' if ok else 'no'}")
    if valid < 2:
        return f"VOID ({valid} valid repeats)", qualify, valid, detail
    return ("PASS" if qualify >= 2 else "FAIL"), qualify, valid, detail


out += ["", "## Gate G3 (registered silicyte-0054): bash layer, normal memory, per-call, 12 agents, RTP on vs off", ""]
v, k, n, d = gate()
out.append(f"**{v}**: {k} of {n} valid repeats qualify.")
out += [f"- {x}" for x in d]
open(sys.argv[2], "w").write("\n".join(out) + "\n")
print("\n".join(out))
