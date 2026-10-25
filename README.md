# loadtest results

One folder per workflow run. `LATEST.md` is the newest sweep, `LATEST_AV.md` the newest antivirus arm.

Run 40241969229 (2026-10-25): all 12 sweep jobs succeeded; its summarize step failed on a shell bug (a missing hog.txt in normal-memory jobs ended the step), so this folder was combined from the run's own artifacts with the same summarize.py, unchanged. Gate G1 (silicyte-0052): FAIL, 0 of 3.
