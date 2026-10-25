"""Guard presence under load, on any host: per-call guard processes versus one process per call.

N synthetic agents share the host. Each agent loops: a 0.5 s CPU burst (its own work), then one tool call whose
guard checks run either as FIVE fresh interpreters started in parallel (form "per-call", the shape of five
PreToolUse command hooks matching one call) or as ONE fresh interpreter running the same five checks
(form "one-process"). The call's guard latency is the slowest of its processes. Latency is recorded up to a
30 s cap, so absence can be read afterwards at any budget: a guard with budget B is absent when latency > B.

Same guard replicas and loop as the Linux control (silicyte-0034), which found zero absence at 1 to 48 agents on
8 pinned Linux cores. This version runs on Windows and Linux runners so a stranger can rerun it.

usage: python sim.py <form> <seconds_per_level> <levels comma-separated> <out.jsonl>
"""
import json
import multiprocessing as mp
import os
import platform
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
CAP = 30.0
BUDGETS = (5.0, 10.0, 15.0)
TRANSCRIPT = os.path.join(HERE, "transcript.jsonl")
PER_CALL = [os.path.join(HERE, s) for s in
            ("guard_regex.py", "guard_transcript.py", "guard_regex.py", "guard_transcript.py", "guard_regex.py")]
ONE = [os.path.join(HERE, "guard_all.py")]


def make_transcript():
    if os.path.exists(TRANSCRIPT) and os.path.getsize(TRANSCRIPT) > 50_000_000:
        return
    row = {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "toolu_x", "name": "Bash",
           "input": {"command": "python train.py --epochs 3 " + "x" * 1500}}]}, "timestamp": "2026-10-21T12:00:00Z"}
    line = json.dumps(row) + "\n"
    with open(TRANSCRIPT, "w") as fh:
        for _ in range(50_000_000 // len(line) + 1):
            fh.write(line)


def burn(seconds):
    end = time.perf_counter() + seconds
    x = 0
    while time.perf_counter() < end:
        x += 1
    return x


def agent(scripts, deadline, q):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "python train.py --epochs 3"},
                          "transcript_path": TRANSCRIPT}).encode()
    while time.time() < deadline:
        burn(0.5)
        t0 = time.perf_counter()
        procs = []
        for s in scripts:
            p = subprocess.Popen([PY, "-I", s], stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            p.stdin.write(payload)
            p.stdin.close()
            procs.append(p)
        capped = False
        for p in procs:
            try:
                p.wait(timeout=max(0.0, CAP - (time.perf_counter() - t0)))
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
                capped = True
        q.put((time.perf_counter() - t0, capped))


def main():
    form, secs, levels, out = sys.argv[1], float(sys.argv[2]), [int(x) for x in sys.argv[3].split(",")], sys.argv[4]
    scripts = PER_CALL if form == "per-call" else ONE
    make_transcript()
    cpus = os.cpu_count()
    env = {"host": platform.node(), "os": platform.platform(), "python": platform.python_version(), "cpus": cpus,
           "form": form, "processes_per_call": len(scripts), "label": os.environ.get("RU_LABEL", "")}
    with open(out, "a") as fh:
        for n in levels:
            q = mp.Queue()
            deadline = time.time() + secs
            ps = [mp.Process(target=agent, args=(scripts, deadline, q)) for _ in range(n)]
            for p in ps:
                p.start()
            res = []
            while any(p.is_alive() for p in ps) or not q.empty():
                try:
                    res.append(q.get(timeout=1))
                except Exception:
                    pass
            for p in ps:
                p.join()
            lat = sorted(r[0] for r in res)
            if not lat:
                continue
            row = dict(env, agents=n, per_core=round(n / cpus, 3), calls=len(lat),
                       p50_s=round(statistics.median(lat), 3), p95_s=round(lat[int(0.95 * (len(lat) - 1))], 3),
                       max_s=round(lat[-1], 3), capped=sum(1 for r in res if r[1]))
            for b in BUDGETS:
                k = sum(1 for x in lat if x > b)
                row[f"absent_at_{int(b)}s"] = k
                row[f"rate_at_{int(b)}s"] = round(k / len(lat), 4)
            line = json.dumps(row)
            print(line, flush=True)
            fh.write(line + "\n")


if __name__ == "__main__":
    main()
