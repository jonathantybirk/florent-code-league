# AGENTS.md

Conventions, then how to evaluate a bot. If you are here to answer "is this bot any good?", the
whole answer is in [How to evaluate a bot](#how-to-evaluate-a-bot).

## Repo conventions

- `docs/` is **sourced material only** — `docs/official/` is verbatim Florent Code League
  documentation, `docs/hpc/` is scraped from hpc.dtu.dk. Never add your own analysis there. Without
  that split, one model's guess quietly becomes the next model's "documentation".
- Authored `.md` belongs in this file or a `README.md`. (On `x/jon` everything else goes in
  `llm-slop-analysis/<person>/`.)
- Everything runs through `uv run`. Python is pinned to 3.13.
- Bots live under `bots/`; each person owns their folder.

---

# How to evaluate a bot

Never judge a bot by a handful of matches. `x/jon:scratch/ladder.py` says it best: matches are
deterministic, so a 30-game head-to-head "is a single sample of a chaotic system: a one-line change
can swing it by four games without being better."

Use the harness in [`tournament/`](tournament/). It plays every pair on every map in both orders,
persists every match to CSV, and ranks with mElo and Nash averaging. Design rationale is in
[`tournament/README.md`](tournament/README.md); this section is the operating manual.

## Before anything else

```sh
uv sync
uv run pytest tournament/          # 84 tests; validates the maths against the paper
```

If you will touch the cluster, open the SSH master once (it lasts 8h):

```sh
SSH_ASKPASS_REQUIRE=never ssh dtu true
```

`SSH_ASKPASS_REQUIRE=never` is not optional when `DISPLAY` is set — without it, ssh tries to launch
a GUI askpass helper and fails silently three times instead of prompting.

## Recipe 1 — evaluate a new or changed bot

**1. Register it.** Every entrant is pinned by name *and* commit; `bot_id` is `name@shortsha`. Add
to `tournament/bots.toml`, or discover a whole tree:

```sh
uv run python -m tournament discover --ref x/jon --prefix bots/jon --append
```

Commit the bot first — `git archive <commit>:<path>` is how it gets staged, so uncommitted work
cannot be evaluated. This is deliberate: a rating attached to a mutable name is meaningless.

**2. Work out what actually changed.** Do not re-run the whole roster for nothing:

```sh
uv run python -m tournament duplicates --tid jon-full --pool jon-new
```

To compare two commits of the same bot, **hash only the `.py` files**. Hashing whole directories
once reported all 34 bots as changed because of an added `BOT_VERSION.toml`.

**3. Plan a challenger run** — the new bots against the roster, skipping roster-vs-roster whose
results cannot have changed:

```sh
uv run python -m tournament plan --tid my-run \
    --bots newbot@abc1234 \
    --vs "$(uv run python -c "
from tournament import registry; print(','.join(s.bot_id for s in registry.load()))")" \
    --dedupe-from jon-full,jon-new \
    --maps official
```

`--dedupe-from` drops roster bots already proven to play identically to another — currently 6 of
42, so 1470 matches instead of 1722. Bots you name in `--bots` are never pruned.

**4. Run it.**

```sh
# locally, for a small field
uv run python -m tournament run --tid my-run --jobs 8

# or on the cluster
uv run python -m tournament hpc push   --tid my-run      # add --bootstrap the first time ever
uv run python -m tournament hpc submit --tid my-run
uv run python -m tournament hpc watch  --tid my-run      # fetches results as they land
```

**5. Rate, pooling with the tournament you extended** — ratings need one win matrix:

```sh
uv run python -m tournament rate --tid jon-full --pool jon-new,my-run --matrix
```

## Recipe 2 — a full round robin from scratch

```sh
uv run python -m tournament plan --tid big --maps official   # omit --bots for everyone
uv run python -m tournament hpc push --tid big
uv run python -m tournament hpc submit --tid big
uv run python -m tournament hpc watch --tid big
uv run python -m tournament rate --tid big
```

34 bots x 21 maps x 2 orders = 23,562 matches, ~58 core-hours, roughly an hour of wall time on a
busy queue.

## Recipe 3 — something went wrong

Re-run the same submit. **Matches that already have a result are skipped by default**, so it
submits exactly the gaps:

```sh
uv run python -m tournament hpc submit --tid my-run     # only the missing matches
uv run python -m tournament hpc logs   --tid my-run     # tail recent stderr
uv run python -m tournament hpc cancel --tid my-run     # bkill every array
```

`--all` forces a full re-run. A killed or crashed match loses nothing permanently: it simply has no
result file.

## Reading the output

`rate` ranks by **`melo_r`**, the transitive component of mElo (`r = div(A)`, `A = logit(P)`), and
prints Nash averaging beside it. Read both.

| signal | meaning |
|---|---|
| `nash_prob > 0` | a **core agent** — in the unexploitable set. `nash_average` is 0 for these. |
| large `rank_delta` | the two methods disagree about this bot. Investigate; this is the interesting column. |
| identical `melo_r` for two bots | almost always duplicates. `rate` names them automatically. |
| `!! PARTIAL DATA` | unplayed pairs enter `A` as 0, which reads as "evenly matched", not "unknown". Provisional only. |
| `intransitivity` | 0 = a clean pecking order, 1 = pure rock-paper-scissors. |

**A worked example of why you must read both.** In the 42-bot run, `tempest@da3fd8a` ranked **11th
by mElo** but was the **sole Nash core agent** — it beats all 41 other bots head to head. `melo_r`
is a mean of log-odds, so bots that crush the weak `vg_*` ancestors near-100% score enormous logits
and outrank a bot that beats everyone by narrow margins. mElo asks "how dominant on average"; Nash
asks "can you be exploited". Reporting only the mElo rank would have buried the strongest bot.

**Duplicates distort `melo_r` but not Nash.** Every copy is a separate entrant on purpose — Nash
averaging is invariant to them (verified: collapsing 42 to 36 entrants leaves the support
unchanged), and a duplicate group is *how you learn* a change did nothing. Collapsing them shifts
every strong bot's `melo_r` by about +0.2 log-odds and reorders 13 of 36 bots.

## Traps

Each of these cost real debugging time.

**Never import numpy, scipy or torch into `tournament/run_match.py` or `tournament/local.py`, or
anything they import.** The engine runs both bots in CPython sub-interpreters that share a GIL
*inside the calling process*; a scientific-stack import there means segfaults. One match per OS
process, always. `test_harness.py` asserts this in a subprocess — if it fails, you broke it.

**Use `--tle 0` (the default) for anything you will rate.** The turn-timeout watchdog is
wall-clock, so `--tle 10` makes results depend on machine load. Use it only for a separate
ladder-compliance check.

**Do not compare `melo_r` across separate tournaments.** Ratings are only meaningful within one win
matrix. Use `--pool`.

**Do not add bots to a finished tournament's directory.** Plan a new challenger run and pool it.

**Cluster specifics** (all in [`docs/hpc/`](docs/hpc/)): `MAX_JOB_ARRAY_SIZE` is 1000 and DTU does
not document it; `module` and `bsub` do not exist in a non-interactive ssh shell; `gbar.sh` reads an
unset `$DT` and dies under `set -u`; `bsub` blocks at roughly 4000 pending jobs; the `hpc` queue
caps you at ~100-120 concurrent slots regardless of array throttles. If you change `chunk` in
`hpc.toml`, keep `chunk x 66s <= walltime x 60` — `submit` refuses otherwise, because walltime is a
hard kill and an over-long element would be killed mid-run.

**Match cost, for planning:** mean 8.8s, median 6.0s, p99 39s, max 63.9s over 36,162 real matches.
Most matches run the full 1000 rounds. Do not assume matches are cheap.

## Where things live

| | |
|---|---|
| `tournament/bots.toml` | the roster, pinned by name + commit |
| `tournament/runs/<tid>/matches.csv` | every match played |
| `tournament/runs/<tid>/ratings.csv` | mElo + Nash per bot |
| `tournament/runs/<tid>/duplicates.csv` | bots that play identically |
| `tournament/README.md` | design rationale, and the departures from the paper |
| `articles/1806.02643v2.pdf` | Balduzzi et al., the source for mElo and Nash averaging |

Staged bots, per-match JSONs, schedules and LSF logs are gitignored — reproducible from the CSVs
plus the registry.
