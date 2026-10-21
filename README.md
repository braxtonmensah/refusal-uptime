# refusal-uptime

Did your agent's guards actually run?

Claude Code runs each `PreToolUse` hook as a separate process with a timeout. Unless the hook sets
`onFailure: "block"` (v2.1.295 and later), a timeout or error lets the tool call go ahead, and the
agent's tool result looks the same as if the guard had allowed it. The timeout is recorded, but
nothing reports it as a share of the calls the guard should have checked. This tool reads your own
transcripts and tells you, per hook, how often it was absent on the calls it exists to check.

```bash
python refusal_uptime.py
```

```bash
python refusal_uptime.py --min-uptime 0.999
```

The second form exits with code 2 if any hook is below 99.9%, so it can gate a cron job or CI.

- Standard library only, Python 3.9+. Reads `~/.claude/settings.json` and `~/.claude/projects/`.
- Sends nothing anywhere.
- A hook counts as **absent** on a call when its record is `hook_cancelled` with `timedOut: true`,
  or `hook_non_blocking_error`. The window for each hook starts at its first record, so calls made
  before you installed it are not charged to it.
- Every count is computed twice by independent paths, and the tool refuses to print a number when
  the two disagree.

## What it does not tell you

Whether your guard is *good*. A guard that runs on every call and allows everything scores 100%.
This measures presence, the precondition for every other guarantee.

Fail-open on timeout is Claude Code's documented default (see the hooks reference at
code.claude.com/docs/en/hooks). It is a design trade-off that keeps agents fast, not a
vulnerability. The point is to measure what it costs you. Measurements from one fleet, and their
limits, are in [NOTE.md](NOTE.md).
