# Analysis scripts behind the refusal-uptime numbers

These are the scripts that produced the field numbers in `NOTE.md` and the workshop paper. They are
standard-library Python 3.11+ and read data locally; nothing is sent anywhere. `refusal_uptime.py` at the
top level is the probe an operator runs on their own transcripts; the files here are the study's own
analyses.

| script | what it computes | input |
|---|---|---|
| `uptime.py` | pre-change absence per guard, windows A and B, by concurrency bin, by day | the four TSV extracts below |
| `aggcheck.py` | the two-count guard: every headline count is computed twice and the run refuses on disagreement | imported by `uptime.py` |
| `window.py` | pre-change window-level view at 11+ concurrency (registered silicyte-0049) | the TSV extracts |
| `episodes.py` | pre-change sustained episodes (5+ consecutive 10-minute buckets at 11+); not registered | via `window.py` |
| `postfix_at_load.py` | post-change presence by concurrency, from transcripts directly, with the dispatcher log as a second count (silicyte-0048) | `~/.claude/projects/**.jsonl`, `~/.claude/settings.json`, the dispatcher's own log |
| `postfix_episodes.py` | post-change sustained episodes against the pre-change series (registered silicyte-0055) | both of the above |

Concurrency, everywhere: the number of transcript files (sessions and subagents) with at least one tool
call of any kind in the same 10-minute UTC bucket. It is a proxy for load, not a measurement of it.

## The pre-change extracts, and a gap we state plainly

`uptime.py` and `window.py` read four tab-separated extracts made from the transcripts:

- `calls.tsv`: `transcript_file  tool_use_id  tool_name  timestamp_iso`
- `hookfail.tsv`: `transcript_file  <the raw JSON line of a hook attachment record>` (cancelled, error and
  blocking records)
- `results.tsv`, `results_hookerr.tsv`: `transcript_file  tool_use_id` for calls with a tool result, and for
  results that were a hook block

The shell step that produced these extracts on 2026-10-21 was not preserved. The format above is what the
scripts read; `postfix_at_load.py` shows the same definitions applied to transcripts directly. A rebuilt
extractor, checked against the original extracts, is still to do.

The transcripts themselves are not released: they hold unrelated work.
