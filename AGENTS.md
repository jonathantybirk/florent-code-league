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
uv run pytest tournament/          # 126 tests; validates the maths and harness
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

`plan` automatically appends three short, non-rating 10 ms compliance probes for every bot named
in `--bots`. Their durable per-bot and per-match outputs are `compliance.csv` and
`compliance_matches.csv`; inspect them directly or run
`uv run python -m tournament compliance --tid my-run`. A pass is a sample, not a proof that every
possible turn is fast. `rate` prints the compliance summary and excludes these matches from its
win matrix.

`--dedupe-from` drops roster bots already proven to play identically to another — currently 6 of
42, so 1470 matches instead of 1722. Bots you name in `--bots` are never pruned.

**Do not generate new evidence for a known duplicate.** Keep all duplicate matches already present
in the historical CSVs, but every new challenger or round-robin plan must use `--dedupe-from` with
all relevant completed runs and schedule only one representative of each known duplicate group.
Pooling old results supplies the evidence already collected; replaying the same opponents against
another copy adds no information. The only exception is the initial evaluation needed to determine
whether a genuinely new bot is a duplicate. Once duplication is established, exclude that copy
from every later schedule.

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

Use every relevant completed run as duplicate evidence. Omit `--dedupe-from` only when no prior
results exist from which behavioural duplicates could be known.

```sh
uv run python -m tournament plan --tid big --maps official \
    --dedupe-from jon-full,jon-new                            # omit --bots for everyone
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

`rate` uses an **agent-vs-agent** matrix. For each bot pair it pools the scores from every map and
both Gold/Silver orders into one smoothed win probability, then forms `A = logit(P)`,
`melo_r = div(A)`, and `nash_average = A p*`. Pooling does not turn the series into one binary
win/loss: every match remains one win, loss, or half-point draw in the probability estimate.

| signal | meaning |
|---|---|
| `nash_prob > 0` | a **core agent** — in the unexploitable set. `nash_average` is 0 for these. |
| large `rank_delta` | the two methods disagree about this bot. Investigate; this is the interesting column. |
| identical `melo_r` for two bots | almost always duplicates. `rate` names them automatically. |
| `!! PARTIAL DATA` | unplayed pairs enter `A` as 0, which reads as "evenly matched", not "unknown". Provisional only. |
| `intransitivity` | 0 = a clean pecking order, 1 = pure rock-paper-scissors. |

**A worked example of why you must read both.** In the 42-bot view,
`tempest@da3fd8a` ranked **11th by mElo** but was the **sole Nash core agent** — it beats all 41
other bots head to head. `melo_r` is a mean of pairwise log-odds, so bots that crush the
weak `vg_*` ancestors near-100% score enormous logits and outrank a bot that beats everyone by
narrow margins. mElo asks "how dominant on average"; Nash asks "can you be exploited".

**Duplicates distort `melo_r` but not Nash.** Every copy remains a separate entrant in the raw
historical evidence on purpose — Nash averaging is invariant to them (verified: collapsing 42 to
36 entrants leaves the support unchanged), and a duplicate group is *how you learn* a change did
nothing. Collapsing them shifts every strong bot's `melo_r` by about +0.2 log-odds and reorders 13
of 36 bots. This explains retained results; it does not permit scheduling new duplicate matches.

**Historical raw evidence keeps duplicates; new schedules and overviews never do.** Keeping every
already-evaluated entrant in `matches.csv`, `ratings.csv`, and duplicate-audit output is deliberate,
but do not include more than one member of a duplicate group in any new schedule or user-facing
ranking, comparison, winner list, or overview. Detect behavioural duplicates on the complete pooled
result set first, choose one representative from each group, and then plan, analyse, or summarize
only that deduplicated entrant set. For a map-specific overview, deduplicate on the complete pooled
multi-map results *before* slicing by map; two distinct bots merely tying or behaving alike on one
map does not make them duplicates. Preserve distinct nonduplicate versions as separate bots rather
than hiding them under a shared family label.

**A final engine coinflip is a draw.** Every result records `win_condition`. When it is `coinflip`,
all gameplay tiebreakers were equal and the engine selected A or B randomly, so every consumer
(ratings, duplicate detection, reports, and website views) must score the match as `0.5` for both
bots. Preserve the raw selection as `engine_winner` for auditability; never let it become a win or
loss merely because historical `winner`/`score_a` columns contain the engine's random choice.

# The automated evaluator

Everything above is the manual path. In normal operation a systemd user timer runs it for you.

```sh
systemctl --user status  botrankings-evaluator.timer     # is it on?
journalctl --user -u botrankings-evaluator.service -f    # what is it doing?
systemctl --user stop    botrankings-evaluator.timer     # pause (safe mid-run)
systemctl --user start   botrankings-evaluator.timer     # resume
```

It runs from a **separate git worktree** at `~/projects/florent-code-league-ci` on `x/tournament`,
so the main checkout is free to switch branches without breaking it. Every two minutes it:

1. **Self-updates** — fast-forwards onto `origin/x/tournament`, but adopts the new commit only if
   `pytest tournament/` passes on it, otherwise resets back. A broken evaluator does not merely
   fail; it submits cluster jobs and publishes to a live website.
2. **Collects** any submitted run — fetch, merge, and if complete, rate and publish. It never
   blocks on the cluster: submission and collection are separate visits.
3. **Discovers** new bots on `x/jon`, `x/luc` and `elias_dev`, and submits them.
4. **Deploys** the site when its committed HEAD has moved.

## What counts as already evaluated

Derived from `runs/*/matches.csv` on every tick, never cached. A bot counts as rated when its
`.py` content hash appears in the match data, regardless of which branch, run, or person produced
it. There is no ledger file to get out of date, and no bootstrap step to get wrong. If a bot has
played but its source cannot be resolved or hashed, the tick **fails loudly** rather than
re-evaluating it forever.

Work already scheduled in a run that has not finished is treated as in flight, so a tick firing
mid-evaluation never schedules the same bot twice. Run ids are keyed on the implementations under
test and nothing else — an unrelated branch moving must not change the id, because the run
directory is where partial results live.

## Rules it enforces that you should not work around

- **A rating is only meaningful against the field it was computed over.** The site ships four
  independently rated fields (fair/all x compliant/including-over-time). Never filter a larger
  field's ratings client-side to fake a smaller one.
- **It refuses to publish a matrix with unplayed pairs**, naming them. An unplayed pair enters
  `A` as 0, which is indistinguishable from a measured draw.
- **It refuses to build the site from a dirty tree.** `npm run build` compiles the working tree,
  so building while someone edits the site deploys their unfinished work. Ranking data is still
  committed and pushed; only the deploy waits.

## Fairness is read from the code, not the directory

`tournament/fairness.py` flags a bot unfair when it imports a bundled map atlas. Path convention
alone was wrong for eleven entrants: Elias' `cand/` snapshots and every `tempest_reinforcements`
carry the same offline atlas as bots their own authors filed under `unfair/`. A path tag still
wins when present, and detection only ever *adds* flags.

## Timing compliance

`--tle 0` rating matches cannot measure turn time, so timing is a separate `kind=compliance`
probe that never enters a win matrix. **Compliance is per-map**: across the probes run so far a
bot's worst map is a median 1.6x its best and up to 5.1x, and three bots exceeded the 10 ms limit
on one map while passing others — `casemate_oracle` runs 3.4 ms on duel and 12.6 ms on quarry.
Version 5 therefore probes **all 21 official maps**; versions 1-4 sampled three and their passes
mean only "not measured where it is slow".

Results merge by `(version, mtime)` per bot, so a newer version supersedes an older one and the
two are never averaged. Re-probe the whole roster after a version bump:

```sh
uv run python -m tournament plan --tid compliance-vN-all --compliance-only \
    --bots "$(uv run python -c "
from tournament.automation import canonical_field
print(','.join(sorted(s.bot_id for s in canonical_field()[0])))")" --maps official
uv run python -m tournament hpc push --tid compliance-vN-all
uv run python -m tournament hpc submit --tid compliance-vN-all
```

## Connectivity

DTU's `login1` refuses IPv4 SSH from off-campus and demands key + passphrase + password on
`login2`, so in practice the cluster is reachable only over **IPv6 or the DTU VPN**. A
`dtu-ssh-master.service` user unit holds the multiplexed connection open and retries every 30 s,
so an outage self-heals. When it is down the evaluator exits 2 each tick and prints the remedy;
nothing is lost, because finished results wait on the cluster and match ids are content-addressed.

`ssh -O check dtu` reports only that the local control socket exists — **not** that the network
path works. Do not treat it as proof the cluster is reachable, and never `ssh -O exit` a working
master without first confirming a fresh connection can be made.

## Traps

Each of these cost real debugging time.

**Never import numpy, scipy or torch into `tournament/run_match.py` or `tournament/local.py`, or
anything they import.** The engine runs both bots in CPython sub-interpreters that share a GIL
*inside the calling process*; a scientific-stack import there means segfaults. One match per OS
process, always. `test_harness.py` asserts this in a subprocess — if it fails, you broke it.

**Use `--tle 0` (the default) for every rating match.** The automatically-added timing probes are
separate `kind=compliance` rows and never enter the win matrix; do not rate an ad-hoc run made with
`--tle 10`.

**Do not compare ratings across separate tournaments.** Ratings are only meaningful within one
evidence matrix. Use `--pool`.

**Do not add bots to a finished tournament's directory.** Plan a new challenger run and pool it.

**Cluster specifics** (all in [`docs/hpc/`](docs/hpc/)): every tournament file, venv, log, and
result lives under the assigned `/work3/s234842` scratch directory; never point `remote_root` back
at zhome. `MAX_JOB_ARRAY_SIZE` is 1000 and DTU does not document it; `module` and `bsub` do not
exist in a non-interactive ssh shell; `gbar.sh` reads an unset `$DT` and dies under `set -u`; the
`hpc` queue caps you at ~100-120 concurrent slots regardless of array throttles. Array elements
are balanced batches of at least 300 matches, sized from the fastest observed production batch to
last at least 20.5 minutes. `submit` refuses a smaller tail; automation finishes it locally.

**Match cost, for planning:** mean 8.8s, median 6.0s, p99 39s, max 63.9s over 36,162 real matches.
Most matches run the full 1000 rounds. Do not assume matches are cheap.

## Where things live

| | |
|---|---|
| `tournament/bots.toml` | the roster, pinned by name + commit |
| `tournament/runs/<tid>/matches.csv` | every match played |
| `tournament/runs/<tid>/ratings.csv` | mElo + Nash per bot |
| `tournament/runs/<tid>/duplicates.csv` | bots that play identically |
| `tournament/runs/<tid>/compliance.csv` | per-bot 10 ms timing status |
| `tournament/runs/<tid>/compliance_matches.csv` | raw per-probe timing evidence |
| `tournament/automation.py` | the evaluator loop: discover, submit, collect, publish |
| `tournament/fairness.py` | unfair detection from bot source |
| `tournament/site_data.py` | the four rated fields the website consumes |
| `tournament/systemd/` | the timer and service units |
| `tournament/README.md` | design rationale, and the departures from the paper |
| `articles/1806.02643v2.pdf` | Balduzzi et al., the source for mElo and Nash averaging |

Staged bots, per-match JSONs, schedules and LSF logs are gitignored — reproducible from the CSVs
plus the registry.
