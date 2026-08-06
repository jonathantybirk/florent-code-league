# benchmarks/tools

Small measurement scripts that answer questions a win rate cannot. Each one was
written to settle a specific argument; the numbers they produced are recorded in
`bots/luc/steward_hardened_reinforced/README.md`.

| script | question it answers |
|---|---|
| `check.sh BOT` | edit gate: undefined names, then one real match. Catches the `NameError`/`AttributeError` class of bug that a caught handler otherwise hides — a bot can score 0.000 across a whole panel and never look like it crashed |
| `crashhunt.sh BOT` | replays 84 matches with tracebacks enabled and reports every distinct crash site. A crashed Builder is swallowed by the handler and simply stops working, which no win rate shows |
| `bench.py LOG` | the standing set, from a stderr log with `DEBUG_BUILD`/`DEBUG_LAUNCH` on: Builder pacing, launcher accuracy and refusal rate, buildings placed in enemy firing lines |
| `score.py RUN BOT` | per-opponent score out of a `benchmarks.suite` run directory |
| `seatscore.py RUN BOT` | the same, split by seat. Team A acts first every round and wins every tie; the gap is ~+0.076 in close matchups and ~0 in easy ones, so it reads as a *symptom* of closeness rather than a lever |
| `ladder_report.py RUN BOT` | per-opponent record out of a tournament run, reporting both readings of "beat 80%": fraction of opponents beaten, and overall win rate |

Two habits these exist to enforce:

**Confirm on a second panel.** Five arms that looked like gains on one panel
reversed sign on another (`REPAIR_NETWORK` off, `BARRIER_INTO_THREAT` off,
`LATE_BUILDERS_MINE`, and two others). One panel is not a measurement.

**Check the bot is deterministic first.** A bot that calls
`get_cpu_time_elapsed()` decides differently depending on machine load —
measured at 11 different winners in 210 matches of identical code, which is
larger than most effects worth measuring. Bound optional searches by work, not
by a clock, or every table you produce is noise.
