"""Replica of a regex PreToolUse guard (the shape of gpu_before_cpu.py): fresh interpreter, stdlib
imports, a few dozen compiled patterns run over the command, allow."""
import json
import re
import sys
from datetime import datetime

payload = json.loads(sys.stdin.read() or "{}")
cmd = payload.get("tool_input", {}).get("command", "")
PATTERNS = [re.compile(r"\b%s\b.*(%s)" % (a, b)) for a in ("python", "py", "node", "Rscript", "julia", "java")
            for b in ("train", "fit", "torch", "numpy", "pandas", "sklearn", "jax", "xgboost", "lightgbm", "cuda")]
hits = sum(1 for p in PATTERNS if p.search(cmd))
_ = datetime.now().isoformat()
sys.exit(0)
