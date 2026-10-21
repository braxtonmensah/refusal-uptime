"""End-to-end tests on a synthetic transcript: counts, the window rule, the gate and the canary."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "..", "refusal_uptime.py")
WRAP = os.path.join(HERE, "..", "canary_wrap.py")


def call(tid, name, t, inp=None):
    return {"type": "assistant", "timestamp": t, "message": {"content": [
        {"type": "tool_use", "id": tid, "name": name, "input": inp or {"command": "ls"}}]}}


def cancelled(tid, label, t, timed_out=True):
    return {"type": "attachment", "timestamp": t, "attachment": {
        "type": "hook_cancelled", "hookName": "PreToolUse:Bash", "toolUseID": tid, "hookEvent": "PreToolUse",
        "command": label, "durationMs": 16000, "timedOut": timed_out}}


def result(tid, t, text):
    return {"type": "user", "timestamp": t, "message": {"content": [
        {"type": "tool_result", "tool_use_id": tid, "content": text}]}}


class ProbeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.settings = os.path.join(self.dir, "settings.json")
        with open(self.settings, "w") as fh:
            json.dump({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
                {"type": "command", "command": "python guard.py", "timeout": 10, "statusMessage": "Checking guard..."}]}]}}, fh)
        proj = os.path.join(self.dir, "projects", "p")
        os.makedirs(proj)
        rows = [call("toolu_0", "Bash", "2026-10-01T00:00:00Z")]          # before the guard's first record
        for i in range(1, 11):                                             # ten matched calls
            rows.append(call(f"toolu_{i}", "Bash", f"2026-10-01T01:{i:02d}:00Z"))
        rows.append(call("toolu_r", "Read", "2026-10-01T01:30:00Z"))       # not matched by "Bash"
        rows.append(cancelled("toolu_1", "Checking guard...", "2026-10-01T01:01:20Z"))
        rows.append(cancelled("toolu_5", "Checking guard...", "2026-10-01T01:05:20Z"))
        rows.append(cancelled("toolu_7", "Checking guard...", "2026-10-01T01:07:20Z", timed_out=False))  # user cancel
        rows.append(call("toolu_c1", "Bash", "2026-10-01T02:00:00Z", {"command": "echo REFUSAL_CANARY_7f3a"}))
        rows.append(result("toolu_c1", "2026-10-01T02:00:01Z", "PreToolUse:Bash hook error: canary refused"))
        rows.append(call("toolu_c2", "Bash", "2026-10-01T03:00:00Z", {"command": "echo REFUSAL_CANARY_7f3a"}))
        rows.append(result("toolu_c2", "2026-10-01T03:00:01Z", "REFUSAL_CANARY_7f3a"))
        with open(os.path.join(proj, "s.jsonl"), "w") as fh:
            fh.write("\n".join(json.dumps(r) for r in rows) + "\n")
        self.args = [sys.executable, PROBE, "--projects", os.path.join(self.dir, "projects"), "--settings", self.settings]

    def test_counts_and_window(self):
        out = json.loads(subprocess.run(self.args + ["--json"], capture_output=True, text=True, check=True).stdout)
        h = out["hooks"][0]
        # window opens at toolu_1's call time, so toolu_0 is excluded; 10 matched + 2 canary calls = 12
        self.assertEqual(h["calls"], 12)
        self.assertEqual(h["fail_open"], 2)              # toolu_1 and toolu_5; the user cancel does not count
        self.assertAlmostEqual(h["refusal_uptime"], 10 / 12)

    def test_gate_exit_code(self):
        self.assertEqual(subprocess.run(self.args + ["--min-uptime", "0.999"], capture_output=True).returncode, 2)
        self.assertEqual(subprocess.run(self.args + ["--min-uptime", "0.5"], capture_output=True).returncode, 0)

    def test_canary(self):
        out = subprocess.run(self.args + ["--canary"], capture_output=True, text=True, check=True).stdout
        self.assertIn("2 calls carried the marker; refused 1, ran unguarded 1", out)

    def test_wrapper(self):
        marker = json.dumps({"tool_input": {"command": "echo REFUSAL_CANARY_7f3a"}}).encode()
        plain = json.dumps({"tool_input": {"command": "ls"}}).encode()
        self.assertEqual(subprocess.run([sys.executable, WRAP], input=marker).returncode, 2)
        self.assertEqual(subprocess.run([sys.executable, WRAP], input=plain).returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
