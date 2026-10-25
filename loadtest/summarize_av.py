"""Antivirus arm: Defender real-time protection on vs off, same run, same runner image. Applies the gate registered
before the first run (silicyte-0053).

G2: windows-2025, normal memory, five per-call guard processes, 12 agents, real-time protection ON (as verified by the
job itself). A repeat qualifies when absence is at least 2% at a 15 s budget or at least 5% at 5 s, AND at least 3x
the RTP-OFF rate of the same repeat number at the same level. PASS iff at least 2 of 3 repeats qualify. A repeat whose
job could not turn protection on is VOID; fewer than 2 valid repeats makes the gate VOID.

Labels look like: windows-2025/normal/r1/rtp-on/eff-True
usage: python summarize_av.py <combined.jsonl> <summary.md>
"""
import json
import statistics
import sys
from collections import defaultdict

rows = [json.loads(x) for x in open(sys.argv[1]) if x.strip()]
for r in rows:
    parts = (r.get("label", "") + "/////").split("/")
    r["os_"], r["mem"], r["rep"], r["av"], r["eff"] = parts[:5]

by = defaultdict(list)
for r in rows:
    by[(r["mem"], r["av"], r["form"], r["agents"])].append(r)

out = ["# Guard presence under load: antivirus arm (windows-2025)", "",
       "Absence at budget B = share of tool calls whose slowest guard process took longer than B. Median over repeats; "
       "per-repeat values in brackets. `eff` = real-time protection as read back by the job after setting it.", "",
       "| memory | Defender RTP | form | agents | calls | p95 s [per repeat] | absent at 5 s | absent at 15 s | eff |",
       "|---|---|---|---:|---:|---|---:|---:|---|"]
for key in sorted(by):
    g = sorted(by[key], key=lambda x: x["rep"])
    med = lambda f: statistics.median(x[f] for x in g)
    reps = lambda f, fmt: "[" + ", ".join(format(x[f], fmt) for x in g) + "]"
    out.append(f"| {key[0]} | {key[1]} | {key[2]} | {key[3]} | {sum(x['calls'] for x in g)} | "
               f"{med('p95_s'):.3f} {reps('p95_s', '.3f')} | {med('rate_at_5s'):.4f} {reps('rate_at_5s', '.4f')} | "
               f"{med('rate_at_15s'):.4f} {reps('rate_at_15s', '.4f')} | {','.join(sorted({x['eff'] for x in g}))} |")

# p95 ratio on/off per level, per-call form, normal memory
out += ["", "## p95 ratio, RTP on / RTP off (per-call form)", "", "| memory | agents | p95 on | p95 off | ratio |",
        "|---|---:|---:|---:|---:|"]
for mem in ("normal", "low1gb"):
    for n in sorted({r["agents"] for r in rows}):
        on = by.get((mem, "rtp-on", "per-call", n), [])
        off = by.get((mem, "rtp-off", "per-call", n), [])
        if on and off:
            a, b = statistics.median(x["p95_s"] for x in on), statistics.median(x["p95_s"] for x in off)
            out.append(f"| {mem} | {n} | {a:.3f} | {b:.3f} | {a / b:.2f} |" if b else f"| {mem} | {n} | {a:.3f} | {b:.3f} | n/a |")


def gate(mem):
    qualify, valid, detail = 0, 0, []
    for rep in ("r1", "r2", "r3"):
        on = [r for r in rows if r["mem"] == mem and r["av"] == "rtp-on" and r["form"] == "per-call"
              and r["rep"] == rep and r["agents"] == 12]
        off = [r for r in rows if r["mem"] == mem and r["av"] == "rtp-off" and r["form"] == "per-call"
               and r["rep"] == rep and r["agents"] == 12]
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


out += ["", "## Gate G2 (registered silicyte-0053): normal memory, per-call, 12 agents, RTP on vs off", ""]
v, k, n, d = gate("normal")
out.append(f"**{v}**: {k} of {n} valid repeats qualify.")
out += [f"- {x}" for x in d]
v2, k2, n2, d2 = gate("low1gb")
out += ["", "## Not gated: the same comparison under about 1 GB of free memory", "",
        f"Would read **{v2}** ({k2} of {n2} valid repeats)."]
out += [f"- {x}" for x in d2]
open(sys.argv[2], "w").write("\n".join(out) + "\n")
print("\n".join(out))
