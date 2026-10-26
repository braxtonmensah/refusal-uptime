"""NOT pre-registered robustness for silicyte-0049: episode-level view. An episode is a maximal run of
consecutive 10-minute buckets at 11+ (all-tool concurrency). Imported from window.py's state."""
import runpy, sys, collections
from datetime import timedelta
sys.argv = ["window.py", sys.argv[1]]
import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    g = runpy.run_path("window.py")
per, active = g["per"], g["active"]
hi = sorted(b for b in per if len(active[b]) >= 11)
eps, cur = [], []
for b in hi:
    if cur and b - cur[-1] != timedelta(minutes=10):
        eps.append(cur); cur = []
    cur.append(b)
if cur: eps.append(cur)
def summ(label, keep):
    sel = [e for e in eps if keep(e)]
    clean = [e for e in sel if sum(per[b][0] for b in e) == 0]
    n_calls = [sum(per[b][1] for b in e) for e in sel]
    print(f"{label}: {len(sel)} episodes, clean {len(clean)} ({len(clean)/len(sel) if sel else float('nan'):.3f}); "
          f"median shell calls per episode {sorted(n_calls)[len(n_calls)//2] if n_calls else None}")
    return len(sel), len(clean)
n_all, c_all = summ("all 11+ episodes with >=20 shell calls", lambda e: sum(per[b][1] for b in e) >= 20)
n5, c5 = summ("episodes of >=5 consecutive buckets", lambda e: len(e) >= 5)
n1, c1 = summ("single-bucket episodes with >=20 shell calls", lambda e: len(e) == 1 and per[e[0]][1] >= 20)
n_max20, c_max20 = summ("episodes of >=5 buckets whose peak is 12-20", lambda e: len(e) >= 5 and max(len(active[b]) for b in e) <= 20)
p = (c5 / n5) * (c1 / n1) if n5 and n1 else float("nan")
print(f"post-fix had 1 episode of 5 buckets (peak 20) and 1 single bucket (12): P(both clean | pre-fix rates) = "
      f"{c5}/{n5} x {c1}/{n1} = {p:.4f}")
