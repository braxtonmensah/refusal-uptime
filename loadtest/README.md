# Guard presence under load, rerunnable

The note in this repo measured one Windows laptop: a guard hook was absent on 0.2% of calls with one agent active
and 53.1% with eleven or more. A Linux control with these same guard replicas showed no absence up to 48 agents.
This folder asks the open question on machines anyone can rent for free: on a clean Windows or Linux runner, does
load alone push guard latency past its budget, and does low free memory (about 1 GB, as on the laptop) change that?

- `sim.py`: N synthetic agents; each loops a 0.5 s CPU burst, then one tool call whose guard checks run either as
  five fresh interpreters (form `per-call`, the shape of five command hooks matching one call) or one interpreter
  running the same five checks (form `one-process`). Latency is recorded uncut up to 30 s, so absence can be read
  at any budget afterwards.
- `guard_regex.py`, `guard_transcript.py`, `guard_all.py`: the guard replicas, standard library only.
- `hog.py`: holds memory until about 1 GB is available, for the low-memory arm.
- `summarize.py`: combines the runs and applies the gate written down before the first run (ledger id
  silicyte-0052): on windows-2025, normal memory, per-call form, 12 agents, absence at least 2% at a 15 s budget
  or 5% at 5 s, and at least 3 times the 1-agent rate, in at least 2 of 3 repeats.

The workflow `.github/workflows/loadtest.yml` runs 12 jobs (Windows and Ubuntu, normal and low memory, 3 repeats)
and commits the combined rows and `summary.md` to the `loadtest-results` branch. To rerun it yourself, fork the
repo and start the workflow from the Actions tab; public-repo runners are free.

Limits: synthetic agents, not real coding-agent sessions; hosted runners have 4 vCPUs, the laptop had 8 logical
CPUs; the replicas are Python scripts like the measured guards, heavier than a compiled guard.
