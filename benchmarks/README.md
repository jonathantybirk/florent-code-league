# benchmarks/

Mechanic-level measurement for Florent Code League bots: not "who wins" but
"which part is good". Findings live in [ANALYSIS.md](ANALYSIS.md).

Why this exists: a head-to-head ladder ranks whole strategies, so a bot can
climb while a specific mechanic — harvesting, routing, breaching, defending —
silently regresses below where an earlier bot already had it. These suites
isolate each mechanic against fixed opposition so a regression cannot hide
behind a win rate.

## Modules

| file | does |
|---|---|
| `replay.py` | decodes `.replay26` protobuf into per-round entity events (spawns, moves, HP deltas). No dependency on the engine at read time |
| `metrics.py` | mechanic metrics per team from a decoded replay: first-harvester round, harvesters alive at checkpoints, builder stall lengths, Core damage timeline |
| `run_one.py` | plays exactly one match in its own process and writes one JSON |
| `suite.py` | schedules and runs suites or duels; materialises pinned bots from any branch with `git archive` |
| `report.py` | aggregates a run into per-suite tables and an h2h matrix |
| `ablate.py` | builds single-change variants of a bot and scores each against a panel |
| `export.py` | flattens a run directory into one committable CSV |

One match runs per OS process. The engine hosts both bots in sub-interpreters
inside the calling process (see `tournament/run_match.py`), so reuse is unsafe
and `run_one.py` stays standard-library + `fcode` only.

## Suites

- **econ** — vs an idle probe. Pure expansion and routing with zero opposition:
  how fast harvesters go up, how much titanium is actually *delivered*, and
  how quickly an undefended Core dies.
- **stress** — vs `probes/denier`, which barriers your ore, shoots your belts
  and parks bodies on your spawn ring but never attacks your Core. Any loss
  here is a mechanics failure, not a strategic one.
- **breach** — vs fortress bots (`casemate`, `turtle`).
- **defense** — vs rush bots (`mistral_fast`, `prospect_rushonly`).
- **h2h** — round-robin among lineage tips, both seats, closed and open maps.

Probe entry points are named `entry.py`, never `main.py`, so tournament
discovery (which treats any directory containing `main.py` as a bot) never
registers them as rated entrants.

## Running

```sh
uv run python -m benchmarks.suite --run-dir benchmarks/runs/<name>
uv run python -m benchmarks.report --run-dir benchmarks/runs/<name>

# one candidate against a panel, both seats, whole map pool
uv run python -m benchmarks.suite --run-dir benchmarks/runs/<name> \
    --duel ragnarok --opponents vigil,vanguard --maps all

# every single-change variant of ragnarok, scored against the panel
uv run python -m benchmarks.ablate --run-dir benchmarks/runs/<name>

uv run python -m benchmarks.export --run-dir benchmarks/runs/<name>
```

Re-running a run directory skips matches that already have a result, so an
interrupted run resumes. Matches use seed 1 and `--tle 0`, which the harness
notes is exactly deterministic; the wall-clock watchdog at `--tle 10` is not,
so it is never used for measurement.

`benchmarks/runs/` is gitignored — it holds raw per-match JSON and staged
copies of bots. Those copies contain `main.py`, and must never end up under
`bots/`, where discovery would register a duplicate bot name and abort a whole
tournament. Committed evidence goes to `benchmarks/data/*.csv`.
