# Refusal uptime: how often did the guards run? Measurements from one Windows agent fleet

Braxton Mensah, Silicyte. Technical note, October 2026. Prepared with AI assistance (Claude Code
agents ran the extraction and analysis under the author's direction); not peer reviewed. Where a
quantity was pre-registered, its forecast and band are stated; all other quantities were not
pre-registered. Numbers are reproducible with `refusal_uptime.py` on the author's transcripts, which
are not published because they contain unrelated work.

## Abstract

Agent deployments are governed by guards: checks that run before a tool call and can refuse it.
Evaluation of guards asks whether they refuse the right things. We ask an earlier question: whether
they ran at all. In Claude Code, a PreToolUse guard that times out does not block the call by
default (v2.1.295 added an opt-in `onFailure: "block"`). The call proceeds either way, so the
agent's tool result looks the same whether the guard allowed it or never answered. The timeout is
recorded in transcripts and telemetry, but no signal we know of relates it to the number of calls
the guard should have checked. We compute that ratio from transcripts. In one operator's
ten-session Windows laptop fleet (concurrency counted as active transcript files, up to 30 or
more), across 261,254 tool calls over 22 days, the guard `gpu_before_cpu` was absent on 29.8% of
the calls it existed to check (30,929 of 103,850), and 99.5% of those calls returned a result that
was not a refusal; a second guard was absent on 59.9%. Absence rose from 0.2% with one transcript
active to 53.1% with eleven or more. We call one minus this fraction **refusal uptime**, propose it
as a service-level objective for guards, and release a probe that computes it from a user's own
logs and a canary wrapper that makes guard presence directly observable.

## 1. Setting

A ten-session research programme ran Claude Code agents concurrently on one Windows laptop with 8
logical CPUs from 2026-09-30 to 2026-10-21, with three PreToolUse guards in a shared user settings
file: `gpu_before_cpu` (Bash and PowerShell, 15 s budget), `no_poll` (Bash, PowerShell and some
read-only status tools, 10 s; analysed here on Bash and PowerShell only) and `stamp_guard` (Write
and Edit, 10 s). The budgets were the author's choice; Claude Code's documented default for command
hooks is 600 s. `onFailure` was not set, so timeouts did not block. Each guard is a Python script
started per call. Transcripts record `hook_cancelled` with `timedOut: true` and the guarded
`toolUseID` when a guard exceeds its budget, and `hook_non_blocking_error` when it exits with an
error; a guard that runs and allows records nothing.

## 2. Method

A guard is **absent** on a call when either record exists for that call. The denominator is every
tool call whose name the guard always matched, from the call guarded by the guard's first record
(window A) or from the guard script's file creation time (window B). Each count is computed twice,
once by joining records to calls through the tool-call id and once directly from the records, and
the analysis refuses to report when the two disagree. Concurrency is the number of transcript files
(sessions and subagents) with a tool call in the same 10-minute bucket; it is a proxy for load, not
a measurement of CPU, memory or disk.

## 3. Results

Corpus: 3,844 transcripts with tool calls, 261,254 distinct calls; 66,106 timed-out hook records
and 3,466 hook-error records across all hooks (about 55,700 of them belong to the three guards
below; the rest are other hooks).

| guard | budget | absent / matching calls | refusal uptime | absent calls with a non-refusal result |
|---|---|---|---|---|
| `gpu_before_cpu` | 15 s | 30,929 / 103,850 | 0.702 | 30,761 |
| `no_poll` | 10 s | 24,121 / 40,283 | 0.401 | 23,989 |
| `stamp_guard` | 10 s | 658 / 1,734 | 0.621 * | 658 |

\* Window-dependent: 12.1% absent (uptime 0.879) in window B, because the script file was recreated
after its first records. Window B gives 29.5% and 60.9% for the other two.

`gpu_before_cpu` absence was pre-registered with a forecast of 0.20 [0.05, 0.50]; measured 0.298.

**By concurrency**, `gpu_before_cpu`: 1 transcript active 0.2% (5 of 2,258); 2-3 0.5%; 4-6 4.4%;
7-10 7.6%; 11 or more 53.1% (28,569 of 53,831). The gradient (11+ minus 1) was pre-registered with a
forecast of +0.25 [+0.05, +0.60]; measured +0.529. At exact levels: under 3% up to 5, a plateau of
5.9-10.6% from 6 to 11, 18-43% from 12 to 19, 34-77% from 20 to 29, and 79.2% at 30 or more (15,993
of 20,200). On 2026-10-18 alone it rose from 2.0% (n = 51 calls) to 70.0%; on 2026-10-17 from 0.0%
(n = 22) to 80.4%.

**Not a few broken sessions.** Of the 3,121 transcripts with at least one call this guard matched,
2,035 show some absence; the worst holds 1.0% of all absences. An outage episode (a run of
consecutive absent calls within one transcript) occurred 4,819 times. Within the same session, 61 of
82 sessions that ran both at low concurrency (6 or fewer) and peak (11 or more) were absent more
often at peak (per-session means 2.3% vs 37.6%). A session-clustered bootstrap (400 resamples of
transcripts) gives a 95% interval of [0.516, 0.563] around the pooled peak-minus-solo gap of 0.540
(concurrency counted over shell calls here, unlike the all-tool count above).

**Coverage as well as presence.** Taking one protected effect end to end (a clock stamp written to
a `.md` or `.jsonl` file, which `stamp_guard` exists to check), 361 of 931 such writes (38.8%) got no
guard verdict: 191 went through shell paths outside the guard's `Write|Edit` matcher, and 170 of the
740 Write/Edit writes found the guard absent. The shell share is 17-22% at every concurrency level;
the total reaches 56.6% (271 of 479) with eleven or more. Pre-registered with a forecast of 0.55
[0.30, 0.85].

**A Linux node did not reproduce it.** On a Linux node pinned to 8 cores, synthetic agents running
replicas of both guards (not Claude Code) showed zero absence from 1 to 48 agents (6 per core) across
22,824 guard runs; median latency rose from 0.064 s to 2.34 s, inside the budgets. This was
pre-registered with a forecast of no absence. Why the laptop differs (memory pressure, process-start
cost, antivirus scanning, a cloud-synced working folder) is an untested hypothesis.

**Guards on one host fail together.** On the 40,283 shell calls where both `gpu_before_cpu` and
`no_poll` were installed, when `gpu_before_cpu` was absent, `no_poll` was absent too 99.86% of the
time (21,945 of 21,975); the reverse is 21,945 of 24,121 (91.0%). Absent-together divided by
absent-either is 0.909, rising from 0.33 with 1-5 transcripts active (12 cases) to 0.47 at 6-11 and
0.92 at 12 or more. For scale, the IEC 61508-6 range for the common-cause factor of programmable
electronics is 0.005 to 0.05; our ratio is an informal analogue, not that factor. (Computed after a
literature search named the quantity; not pre-registered.)

**These agents took the sanctioned exit, openly.** `gpu_before_cpu` offers an override in its
refusal text. 376 of its 461 refusals (81.6%) were re-issued with that override. Over the period
the override was used 18,588 times against those 461 refusals: 17,735 uses (95.4%) came with no
refusal in the previous five calls, so it was mostly written in pre-emptively, by 308 of 369 sessions
with shell calls. Covert routing-around through an unwatched path followed only 4 of 603 attributable
refusals across all three guards (0.7%, from a five-call detector, so a lower bound; forecast 20%,
refuted). For comparison, CircumEval (a June 2026 project page, not peer reviewed; three models
editing read-only files without a sanctioned path) reports 40% to 100% circumvention, and a NeurIPS
2026 workshop ablation (Agrawal and Agrawal) finds agents take a self-service override at least
48.0% of the time when the refusal names it and 0.0% when it does not (three models given identical
text: 48.0%, 32.0%, 7.3%). Our fleet has no no-override baseline, so the link is consistent, not
shown.

**The rate rose over the period.** Of 32 daily activity series fitted, two are reported here:
guard timeouts, doubling time 2.8 days (R-squared 0.44), and busy-hour concurrency (the mean of a
day's six busiest 10-minute buckets), 23.8 days (R-squared 0.52), fitted at 10.4 on 2026-10-21. Peak
buckets already exceed 30; on its trend the busy-hour mean would reach 30 by 2026-11-26. This is an
extrapolation from 22 days of one fleet.

## 4. What this does and does not show

It shows that a guard implemented as a timed sidecar that defaults open can be absent on a large
share of the calls it exists to check, with no signal to the agent or operator unless they read
transcripts or telemetry, and that the share rises with concurrency, our proxy for load. It does
not show the cause, that any production platform behaves like this loaded laptop, that our guards
are representative, or anything about the security of Claude Code or Codex: fail-open on timeout is
their documented design trade-off, and `onFailure: "block"` is the available mitigation. The next
experiment is a sweep with real Claude Code sessions on Linux and on a second Windows machine.

## 5. Recommendations

1. Treat refusal uptime as an SLO for every guard, with a target (we suggest 0.999) and an alert.
2. Give every guard a canary-deny contract (`canary_wrap.py`) and send a scheduled canary call
   through the real path, so presence is observed rather than inferred.
3. Where a guard must hold, set `onFailure: "block"` with an explicit, measured latency budget, so a
   slow guard slows the agent instead of vanishing.

## Related work

Guardrail evaluation and red teaming (Mindgard, Promptfoo, Lakera Red, Picus AI Security
Validation) measure detection efficacy, not presence. Two signals come close to ours: Claude Code's
own OpenTelemetry hook events (`hook_execution_complete` reports `num_cancelled` per execution; the
same streams contain the tool-call denominator) and the AISIX gateway's
`aisix_guardrail_bypasses_total` counter. Neither reports skipped checks as a share of the calls a
guard should have checked. A Windows report (Claude Code issue 76413, closed unresolved) described
hooks apparently not running; its author later traced it to a launch failure. Breach-and-attack
simulation validates security controls continuously for a similar reason (Picus Blue Report 2025:
14% of the vendor's simulated attacks generated an alert, a detection figure). arXiv 2607.21495
schedules readiness checks for agents against silent degradation.
