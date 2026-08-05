# Tournament harness

> **Run data before 2026-08-04 was measured before the Aug 4 turret patch (fcode
> ≤ 2.3.3), when turrets were stronger.** The 2.3.4 balance pass changed the
> Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was +10%), 7
> damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP (was 30)
> on a 2-round reload (was 3). Every `tournament/runs/` directory recorded before
> that date — matches, ratings, duplicate groups and the Nash support that falls
> out of them — describes a game that no longer exists. The harness itself is
> unaffected; the numbers it produced are not comparable across the patch, so
> don't rank a 2.3.4 bot against a pre-patch rating.

Round-robin bot tournaments with results in CSV, ranked by **mElo** and **Nash averaging** from
[Balduzzi et al., *Re-evaluating Evaluation* (NeurIPS 2018)](../articles/1806.02643v2.pdf).
Runs locally or as an LSF job array on DTU HPC.

## Why not just count wins

Win rate and Elo are **not invariant to redundant agents**. The paper's Example 1: in a
rock-paper-scissors field, adding one duplicate agent moves Elo from `(0, 0, 0)` to
`(-63, 63, 0, 0)`, "falsely suggesting agent B is superior". Nothing about the agents changed.

That is our exact situation — the roster contains seven `vg_v*` ancestors and eight `v233_*`
probes, all near-duplicates. Whichever bot happens to beat that cluster gets credit for it once per
copy. Nash averaging is provably invariant to this (Theorem 1, P1); the transitive part of mElo is
not. The harness computes both and `rate` shows where they disagree — that disagreement is the
interesting output, not a nuisance.

## Quick start

```sh
uv sync
uv run pytest tournament/                  # validates the maths against the paper first

uv run python -m tournament discover --ref x/jon --prefix bots/jon
uv run python -m tournament plan --tid smoke --bots vanguard,undertow,turtle --maps screen
uv run python -m tournament run  --tid smoke --jobs 8
uv run python -m tournament rate --tid smoke --matrix
```

`plan` also adds three short timing probes for every bot selected by `--bots` (or the whole roster
when `--bots` is omitted). They sample every unit-turn on `atoll`, `duel`, and `quarry`, flag a
measured turn at 9 ms as **close** and one over the ladder's 10 ms limit as **exceeded**, and never
enter the rating matrix:

```sh
uv run python -m tournament compliance --tid smoke
```

To refresh timing distributions without scheduling any rating matches, use
`plan --compliance-only`; this still runs the three instrumented probe maps for every selected bot.

The per-bot summary is durable in `compliance.csv`; it includes the observed per-turn minimum,
25th percentile, median, 75th percentile, and maximum. Individual probe distributions, sample
counts, timeouts, ordinary bot exceptions, host, and finish time are in
`compliance_matches.csv`. `rate` prints the summary alongside mElo and Nash results.
Timeouts participate in the nearest-rank empirical percentiles as censored `>12 ms` observations;
they are not silently dropped from the distribution.

On the cluster (see [../docs/hpc/](../docs/hpc/)):

```sh
SSH_ASKPASS_REQUIRE=never ssh dtu true      # once per 8h, opens the ControlMaster

uv run python -m tournament plan   --tid jon-full --maps official
uv run python -m tournament hpc push   --tid jon-full --bootstrap   # --bootstrap only the first time
uv run python -m tournament hpc submit --tid jon-full
uv run python -m tournament hpc watch  --tid jon-full               # fetches as results land
uv run python -m tournament rate       --tid jon-full
```

## Bots are pinned by name **and** commit

```toml
[[bot]]
name   = "vanguard"
commit = "9713344"
path   = "bots/jon/fair/vanguard"
tags   = ["jon", "fair"]
```

`bot_id` is `vanguard@9713344` and is the key in every CSV. Bots are extracted with
`git archive <commit>:<path>`, so nothing is ever checked out and bots on branches that are not
`main` — or that no longer exist on any branch — are all equally usable. A rating attached to a
bare name would be meaningless the moment someone edits the bot; `x/jon:scratch/arena.py` goes as
far as MD5-ing bot sources mid-run to detect exactly that. Pinning makes it impossible.

## Adding new bot versions: challenger mode

When a bot changes, you do not need to re-run the whole round robin — only the pairings whose
result could have changed. `--vs` plays the challengers against a roster (and each other) and
skips roster-vs-roster:

```sh
uv run python -m tournament plan --tid jon-new \
    --bots "tempest@da3fd8a,vanguard@da3fd8a,undertow@da3fd8a,..." \
    --vs   "$(all the bot_ids at the previous commit)" \
    --maps official

uv run python -m tournament hpc push --tid jon-new
uv run python -m tournament hpc submit --tid jon-new

# ratings need ONE win matrix, so pool the challenger run with the round robin it extends
uv run python -m tournament rate --tid jon-full --pool jon-new
```

Because entrants are pinned by commit, `vanguard@9713344` and `vanguard@da3fd8a` are **distinct
entrants that play each other**, so "did this change help?" is answered directly by their head to
head rather than by comparing two ratings from different tournaments.

Real numbers from the first such run: of 39 bots at the newer commit, only **8** had changed
Python — 3 edited, 1 new, 4 new version snapshots. The other 31 differed solely by an added
`BOT_VERSION.toml`, so their existing results stayed valid. That made the update 12,600 matches
instead of the 36,162 a naive 42-bot round robin would have cost, in **1 array instead of 24**.

Worth knowing when diffing bots yourself: hash only the `.py` files. Hashing whole directories
reported all 34 bots as "changed" purely because of that metadata file.

## Duplicate bots are tracked, not assumed away

The roster keeps producing bots that are the same player under two names, and it is never obvious
from the source tree. `rate` therefore runs behavioural duplicate detection every time, and there
is a standalone command:

```sh
uv run python -m tournament duplicates --tid jon-full --pool jon-new
uv run python -m tournament duplicates --tid jon-full --tolerance 0.05   # "seem to be identical"
```

Results on the real 42-bot field:

```
4 group(s) of bots that PLAY identically:
  adaptive_v1@9713344, siege_v2@9713344            same vs all 40 shared opponents; 21/42 h2h
  frontier@9713344, frontier_v2@9713344            same vs all 40 shared opponents; 21/42 h2h
  undertow@da3fd8a, undertow_df5e698@da3fd8a       same vs all 40 shared opponents; 21/42 h2h
  v233_h@9713344, vanguard@9713344,
    vanguard@da3fd8a, vanguard_1e88ae8@da3fd8a     same vs all 38 shared opponents; 21/42 h2h
```

**Why this matters.** Duplicates break Elo and the transitive part of mElo — the paper's Example 1
has one redundant copy move Elo from `(0,0,0)` to `(-63, 63, 0, 0)`. Nash averaging is invariant
and splits its equilibrium mass across the copies instead, which is why a `nash_prob` of exactly
`0.5000` on two bots is a *symptom* worth naming rather than a curiosity.

**Two notions, and they disagree.** Code duplicates (identical `.py`) are cheap and exact but miss
real twins: the four-way `vanguard` group above is only a *two*-way group by code hash. `v233_h`
differs by one line (`DEBUG = False` vs an env lookup) plus a comment, and `vanguard@da3fd8a`
differs by Jon's edits — none of which change what the bot does. Behaviour finds all four. Note
also that the code hash covers **only `.py` files**: an added `BOT_VERSION.toml` once made all 34
bots look changed.

### Pruning duplicates from a challenger field

Duplicates are not merged in the ratings — Nash averaging is invariant to them, and a group like
`vanguard@9713344, vanguard@da3fd8a` is *how you learn* a change did nothing. But playing a new bot
against four copies of the same bot is four times the compute for one bot's worth of information,
so `plan` can prune the field using duplicates found in earlier runs:

```sh
uv run python -m tournament plan --tid next --bots newbot@abc1234 \
    --vs "$roster" --dedupe-from jon-full,jon-new
```

```
pruned 6 duplicate bot(s) from the field:
  v233_h@9713344            -> covered by vanguard@da3fd8a
  vanguard@9713344          -> covered by vanguard@da3fd8a
  vanguard_1e88ae8@da3fd8a  -> covered by vanguard@da3fd8a
  ...
1 challengers vs 36 roster bots  ->  1470 matches   (1722 without pruning)
```

The survivor is chosen by newest commit, then a live path over an archived one, then shallower
path, then name. Depth alone cannot decide it: `bots/jon/fair/vanguard` and
`bots/jon/versions/vanguard_1e88ae8` are the same depth, hence `ARCHIVE_DIRS`.

**Bots named in `--bots` are never pruned**, even if they duplicate something in the roster —
running a new version against its own predecessor is usually the entire point.

**Both conditions are necessary.** A pair must match on every shared opponent *and* split their
own head-to-head evenly. The pair's own result has to be excluded from the first test — identical
bots beat each other exactly half the time — but excluding it alone would also flag two bots that
differ *only* in one beating the other, which are not redundant at all. The even head-to-head is
the paper's Definition 3, where the duplicate ties with its original. Two identical deterministic
bots here go 21/42, each winning every map as player A.

## Map sets

The official pool and Jon's synthetic corpora are kept separate on disk, and a map set just picks
which trees to glob:

| `--maps` | maps | games per pair | where |
|---|---|---|---|
| `official` (default) | 21 | 42 | `maps/*.map26` |
| `generated` | 82 | 164 | `maps/generated/**` |
| `all` | 103 | 206 | both |
| `screen` | 6 | 12 | the fast subset for iteration |
| `secret` | 10 | 20 | `tournament/custom_maps/*.map26` |
| `official_secret` | 31 | 62 | official + held-out |

Every pair plays every map in **both orders**, which is what makes first-player advantage cancel in
the aggregate. Generated-map labels are prefixed (`generated/stress/...`) so they can never collide
with an official map in the CSV.

### The held-out pool

`secret` is the evaluation pool: terrain nobody has developed against, used to tell generalisation
apart from fitting to the 21 official maps. It is deliberately awkward to reach by accident:

- The maps live in `tournament/custom_maps/`, **outside `maps/`**, so no `maps/` glob finds them,
  and the directory is gitignored (only its README is tracked). They exist on the evaluation
  machine and nowhere else. See `tournament/custom_maps/README.md` for the rules.
- Labels are prefixed `secret/<name>`, and a bare `--maps geode` **fails** rather than resolving
  into the pool. Mixing pools has to be spelled out as `--maps official_secret`.
- The standing automation still plays `official` only. Held-out runs are explicit:
  `plan --tid <id> --maps secret`, then `hpc push` / `hpc submit`.
- `ratings.csv`, `duplicates.csv` and the canonical field are computed from official matches only,
  so a held-out run never moves the published ladder. The held-out rows do travel in
  `matches-distinct.csv`, which is how the website offers them as a separately-rated map pool.
- The website publishes a held-out map's **name and size only** — never its terrain or core
  placement — and defaults to the standard pool.

## The rating pipeline

The rating view uses a square agent-vs-agent matrix. All maps and both Gold/Silver orders are
pooled into one smoothed win probability for each bot pair. This preserves every match as a win,
loss, or half-point draw; it does not reduce the whole pairwise series to one binary result.

```
match results  ->  P = (wins + 1/2)/(games + 1)      add-half, keeps logits finite
               ->  A = logit(P)                      antisymmetric: A + A^T = 0
               ->  r = div(A) = (1/n) A 1            TRANSITIVE component -- the ranking key
               ->  rot(A) = A - grad(r)              cyclic component
               ->  C from a Schur decomposition of rot(A)     mElo_2k
               ->  p* = argmax H(p) s.t. Ap <= 0, p in simplex   maxent Nash
               ->  n = A p*                          Nash average
```

**Ranking is by `melo_r`**, the transitive component. `ratings.csv` also carries `nash_prob`,
`nash_average`, and a `rank_delta` column showing how far the two methods disagree per bot.

The engine records both `winner` and `win_condition` for every finished match. Its last fallback,
`win_condition=coinflip`, is used only after core survival, delivered titanium, living harvesters,
and stored titanium are all tied. That random choice is not evidence of relative skill: the
pipeline scores it as a draw (`score_a=0.5`) in ratings, duplicate detection, reports, and website
views. New result files retain the raw random choice as `engine_winner`; historical CSVs are
corrected on read from their preserved `win_condition`.

Two deliberate departures from the paper, both because the paper is loose where it matters here:

- **Add-half smoothing.** The paper uses raw relative frequencies, but a 42-game sweep produces
  clean 42-0 results routinely and `logit(1) = inf`. `(wins + 1/2)/(games + 1)` stays interior
  *and* preserves `p_ij + p_ji = 1` exactly, so `A` remains exactly antisymmetric.
- **Schur instead of SGD for mElo_2k.** The paper's appendix E gives online gradient updates with
  `eta_r = 16` and a 16:1 rate ratio over `C`. In log-odds units that ratio leaves `C` unable to
  grow away from its initialisation — measured: it failed to beat plain Elo on rock-paper-scissors,
  which is the one case it must win. Section F.3 recommends the closed form instead ("first extract
  the transitive component and then perform the Schur decomposition on `A~ = rot(A)`"), which is
  exact and deterministic. The appendix-E rule is still implemented, as `melo_online_update`, for
  updating ratings incrementally as new matches arrive.

The tests in `test_rating.py` check against the paper's own worked examples rather than against our
output: rock-paper-scissors, the duplicate-agent invariance of Example 1, and both sides of
Example 2's discontinuity at `eps = 1/2`.

## The module boundary

**`run_match.py`, `local.py`, and anything they import must stay standard-library + `fcode` only.**

The engine runs each bot in a CPython sub-interpreter with `SHARED_GIL` and
`check_multi_interp_extensions=1` — inside the calling process. A numpy or torch import in that
process shares an allocator and a GIL with the bots; this repo has already hit segfaults and an
autograd "called while holding the GIL" failure that way. So:

- one match per OS process, never reused (`max_tasks_per_child=1` locally, one array element per
  match on LSF);
- `rating.py` imports numpy/scipy and is imported only by `rate`;
- `test_harness.py` asserts the boundary in a subprocess rather than trusting the convention.

## Files

| | |
|---|---|
| `registry.py`, `bots.toml` | the roster, pinned by name + commit |
| `discover.py` | scan a git ref for bot directories |
| `maps.py` | map-set selection |
| `plan.py` | stage bots + maps, build `schedule.jsonl` |
| `run_match.py` | **one match, one result file** — the array-job payload |
| `local.py` | process pool over the schedule |
| `merge.py` | result JSONs -> `matches.csv` |
| `compliance.py` | instrumented 10 ms probes + durable compliance reports |
| `rating.py` | mElo + Nash averaging |
| `report.py` | `ratings.csv` + the printed table |
| `hpc.py`, `hpc.toml`, `bootstrap.sh` | the DTU HPC driver |

A run directory is self-contained and rsyncs as a unit:

```
runs/<tid>/
  manifest.json    what was planned, and from which commits
  schedule.jsonl   one match per line; the line number IS the LSF array index
  stage/<bot_id>/  bot sources at their pinned commits
  maps/            only the maps this tournament uses
  results/         one <match_id>.json per finished match
  matches.csv      merged results
  ratings.csv      mElo + Nash
  compliance.csv          per-bot 10 ms status and timing percentiles
  compliance_matches.csv  per-probe timing distributions and evidence
```

Rating `match_id` is a hash of `(bot_a, bot_b, map, seed, tle)`; compliance ids additionally carry
their probe version. Re-planning therefore reproduces ids, merging is idempotent, and an
interrupted tournament resumes simply by re-running `hpc submit`, which skips whatever already
has a result.

## LSF array sizing and `chunk`

`MAX_JOB_ARRAY_SIZE = 1000` on this cluster — a larger array is rejected outright with
`Job array index too large. Job not submitted.` This is **not** mentioned in DTU's job-array
documentation, so `submit` queries `bparams -a` and splits the schedule across as many arrays as
needed. Arrays run concurrently against the same per-user slot limit, so splitting costs nothing
in throughput — but `bsub` takes ~90s to accept a 1000-element array, so submitting many of them
is slow in itself.

**Each array element plays `chunk` consecutive matches — 20 by default** (`chunk` in `hpc.toml`).
This is set from measurement: each element pays ~3s of module load, venv activation and
interpreter startup, and 24 arrays take ~35 minutes to `bsub`. For the 23,562-match Jon
tournament:

| `--chunk` | elements | arrays | submit time |
|---|---|---|---|
| 1 | 23,562 | 24 | ~35 min |
| **20** (default) | **1,179** | **2** | **<1 min** |

```sh
uv run python -m tournament hpc submit --tid jon-full             # chunk 20
uv run python -m tournament hpc submit --tid jon-full --chunk 1   # one job per match
```

Use `--chunk 1` when you want every match individually schedulable and individually retryable —
worth it if you expect bots to hang, since a hung match then burns one element's walltime rather
than taking 19 healthy matches down with it.

### Finished matches are never re-submitted

`submit` skips any match that already has a result, locally or on the cluster. `run_match` would
skip them anyway, but only *after* the job was scheduled and paid its ~3s of startup — pure waste
on a contended queue. So re-running `hpc submit --tid <tid>` after a partial run submits exactly
the gaps, and on a complete tournament it refuses:

```
error: nothing to submit: every match already has a result
```

Pass `--all` to force a full re-run (`run_match --force` is the per-match equivalent).

This is why array elements read their work from a **worklist file** of schedule indices rather
than computing a contiguous range: outstanding matches are scattered through the schedule after a
partial run, so `element i -> indices [(i-1)*chunk+1 .. i*chunk]` would re-run finished work.
Instead each element does `sed -n "first,last p" work_<stamp>.txt`, which chunks a gappy set
exactly as well as a dense one — and handles the ragged final element for free by yielding fewer
lines. Each submission writes its own timestamped worklist, so re-submitting never disturbs an
array that is still running.

### Walltime is a hard kill

`walltime` must cover a whole element — `chunk` x worst-case match. Measured over 14,465 real
matches on this roster:

| | mean | median | p90 | p99 | max |
|---|---|---|---|---|---|
| duration | 8.8s | 6.0s | 17.5s | 39s | **64s** |
| turns | 584 | **1000** | 1000 | 1000 | 1000 |

Most matches run the full 1000 rounds, so a match is seconds, not milliseconds — the full
23,562-match tournament is **~58 core-hours**. At chunk 20 an element is ~3 min typically and
21.3 min in the pathological case where all 20 of its matches are as slow as the slowest ever
seen, hence `walltime = 22`.

`submit` calls `check_walltime()` first and refuses if `chunk x 66s` exceeds it, so raising
`chunk` without raising `walltime` is an error rather than a silent source of killed jobs. If an
element is killed anyway, nothing is lost permanently — its matches simply have no result file,
and re-running `hpc submit` picks up exactly those.

### Cores

One core per element (`-n 1`), and more would be pointless. A single match cannot use more than
one core: the engine runs both bots in CPython sub-interpreters sharing one GIL inside one
process (measured CPU/wall efficiency ~84% of one core, max RSS 193 MB). And parallelising
*within* an element gains nothing either, because the binding constraint is the ~100-120 per-user
**slot** cap — 25 elements x 4 cores buys exactly the same concurrency as 100 elements x 1 core,
while being harder for LSF to backfill on a busy queue.

`hpc cancel --tid <tid>` bkills every array belonging to a tournament.

## Determinism

The engine is deterministic given a seed, so rating matches use `--tle 0` (the default) and local
and cluster results agree match-for-match. The automatically-added compliance probes are marked
`kind=compliance`, use the engine CPU clock and a 12 ms guard (so their own replay markers do not
create a timeout), and are written to separate CSVs. They are never pooled into ratings.

Timing probes are samples, not proofs: three short matches can establish an observed violation or
near-limit turn, but a pass means only that no issue was observed in the sampled unit-turns.

Bots that use unseeded `random` are also non-deterministic; the engine does not seed bot-side RNG.

## Local live-ladder automation

`tournament.automation` is the one-shot worker behind the public bot ladder. It is designed to be
called by the systemd user timer in `tournament/systemd/`, but the units are deliberately shipped
disabled: installing them starts real evaluation work and must be an explicit operator action.

On each invocation it:

1. fetches `origin/x/jon` and discovers directories containing `main.py`;
2. hashes the complete Python tree at the pushed commit and skips hashes already in
   `tournament/automation-state.json`;
3. groups byte-identical new directories and evaluates one live-path representative on DTU HPC;
4. plays every genuinely new implementation against the duplicate-free canonical field, plus
   every other new implementation, on all official maps in both orders;
5. runs the v4 10 ms compliance probes and records per-turn min/p25/median/p75/max;
6. detects behavioural duplicates from the completed full evidence, excludes new duplicates from
   the distinct matrix, and recalculates mElo and Nash;
7. generates the split data bundle for `/botrankings`, builds the portfolio, commits and pushes
   the changed data, then deploys the finished site directly to Cloudflare;
8. commits whatever run data the tick gained and pushes it to `origin/x/tournament`, so the match
   and rating CSVs are on the remote for everyone else to analyse.

Step 8 runs on every tick in a `finally`, over all of `tournament/runs/` rather than per finished
run: a run still mid-collection travels too, and results stranded by a crashed tick get picked up
rather than lost. It pushes only when this checkout is on `--data-branch` (default
`x/tournament`) and has no uncommitted changes outside `tournament/runs/`; otherwise it logs why
and the next tick retries. `.gitignore` keeps the commit to the durable files — manifest, matches,
ratings and compliance CSVs — while staged bots, per-match JSON and LSF logs stay local. If
somebody pushed to the branch during the cluster run, the data commit is rebased onto theirs and
retried, never forced. A failed push is reported but never fails the tick. `--no-push-data` turns
the step off.

The worker never falls back to local matches. If the eight-hour SSH master is unavailable it exits
with the exact `SSH_ASKPASS_REQUIRE=never ssh dtu true` login instruction; the next timer event
resumes after login.

The run id is derived from the pushed commit and unseen source hashes. Match ids are
content-addressed, so an interrupted invocation resumes its existing result directory. A non-
blocking file lock prevents timer overlap. Failed or incomplete matches stop publication rather
than entering the ratings as fake 50/50 evidence.

The initial canonical run is `jon-vanguard-818f3b4`. The runtime state and lock are intentionally
gitignored. To inspect discovery without playing matches, use:

```sh
uv run python -m tournament.automation \
    --canonical-run jon-vanguard-818f3b4 --dry-run --no-publish
```

### Where the CI actually runs, and what decides the watched branches

It runs on Lucas's workstation, not on a server: user timer `botrankings-evaluator.timer`, firing
`botrankings-evaluator.service` every two minutes, `WorkingDirectory` the sibling checkout
`~/projects/florent-code-league-ci`, which stays on `x/tournament` and fast-forwards itself via
`--self-update-branch`. The unit name contains neither "tournament" nor "automation", so grep for
`botrankings` when looking for it. Nothing runs on the cluster except the matches themselves.

**The installed unit passes explicit `--source` flags, and those fully replace `DEFAULT_SOURCES`.**
Editing `DEFAULT_SOURCES` in `automation.py` therefore has no effect on the live ladder — it is
only the fallback for a hand-run invocation. Adding a branch to the CI means editing
`tournament/systemd/botrankings-evaluator.service` *and* reinstalling it:

```sh
cp tournament/systemd/botrankings-evaluator.service ~/.config/systemd/user/
systemctl --user daemon-reload
```

Keep the two in sync; `systemctl --user cat botrankings-evaluator.service` shows what is really
running. A `--source` is `branch:prefix[:exclude,exclude]`, where the excludes are fnmatch patterns
against the repo-relative bot directory and `*` crosses `/`. A contributor who works at the top of
`bots/` instead of in a personal directory needs the excludes to name their non-entrants, including
the starter template that also lives on `main`.

Two facts worth knowing before concluding "the CI is broken": a tick that finds no unseen code
hashes writes `updated_at` and exits, so a fresh timestamp in `automation-state.json` is not
evidence that anything was evaluated; and `last_seen_refs` lists exactly the branches the *running*
unit watches, which makes it the fastest way to check whether a source edit was actually installed.

To install—but not start—the local units:

```sh
mkdir -p ~/.config/systemd/user
cp tournament/systemd/botrankings-evaluator.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
```

Launching the CI is a separate explicit action:

```sh
systemctl --user enable --now botrankings-evaluator.timer
```

Status and logs:

```sh
systemctl --user status botrankings-evaluator.timer
journalctl --user -u botrankings-evaluator.service -f
```

## The online ladder feed (`/botrankings/live`)

Everything above is the *offline* tournament: our bots against each other, on our maps, scored with
mElo and Nash. `tournament/live_feed.py` publishes a different thing entirely — the *online*
platform ladder, with real opponents and real Elo — to `lucasrgpedersen.com/botrankings/live`.

Run it by hand with `python -m tournament.live_feed --print`; add `--deploy` to publish. It keeps an
append-only cache at `tournament/live-cache.jsonl` (gitignored) and pages the match log backwards
only until it meets a match it already has, so a warm run costs one API page and about 7 seconds.

### How the platform's ladder actually works

Reverse-engineered from all 12255 rated matches between 1 August and 5 August. Both findings are
exact, not approximate, and `live_feed.py` depends on them:

- **The rating rule is plain Elo, K=32, with a series scored as games won out of 5.** So a 3–2 win
  counts 0.6, not 1.0. Predicting every observed `eloDelta` from the two pre-match ratings under
  this rule reproduces all 12255 of them with zero residual. Because the rule is exact, a bot's
  equilibrium rating is exactly its Elo-scale strength — the fixed point of the update is where
  expected score equals Elo-expected score, which happens only at true strength and is independent
  of who it gets paired against. That is why the projected Elo is a one-parameter maximum
  likelihood fit and not a ladder simulation.
- **Pairing is a global round every 10 minutes on a fixed clock.** Every rated match in the sample
  was created at minute ≡ 2 (mod 10), second 43, without exception. Each team with a ready
  submission plays exactly one series per tick — 662 ticks, no team ever twice in one tick — so a
  submission collects about 144 rated series a day and cannot choose its opponent.
- **Within a tick, teams are sorted by rating, cut into consecutive groups of about 8, and paired
  uniformly at random inside each group.** Rank distance between paired teams is hard-capped at 11
  and decays smoothly; a block size of 8 fits the observed distribution to a total-variation
  distance of 0.033, beating windowed matching and every other block size tried. The rare pairings
  out at distance 9–11 come from how the final short group is absorbed. This is the one inference
  here that is a best fit rather than a proof, so treat the group size as ~8, not as 8.

The practical consequence for evaluating a submission: it will only ever meet the handful of teams
nearest it in rating, so `vs pairing group` on the page is the number that predicts its results,
and `vs the whole active field` is context.

### Why it is a separate systemd unit

`botrankings-live.timer` runs every two minutes, independently of `botrankings-evaluator.timer`.
Folding the feed into the evaluator tick would have made it as late as the slowest HPC collection
of the day — that tick already runs for about two minutes against a two-minute timer. Split, the
two only interact at `deploy_assets`, which holds an exclusive `flock` on `.deploy.lock` in the
site repo so two overlapping `wrangler deploy` runs cannot race.

Losing that lock is not rare -- the feed holds it for roughly a third of every two-minute window --
and with the bundle untracked there is no longer a moved HEAD to make the next tick retry. So a
compile that loses the lock leaves `.deploy-pending` behind, and the next evaluator tick picks it
up before its own HEAD check. A feed deploy never clears that marker, because uploading `dist/`
untouched cannot satisfy a build somebody else still needs. Both `.deploy-pending` and
`.deploy.lock` must stay gitignored in the site repo: they are untracked files, and an
un-ignored one reads as a dirty tree, so the marker would freeze the very deploy it exists
to rescue.

**The failure this combination produced, worth recognising:** only `astro build` copies `public/`
into `dist/`, so a ranking refresh whose deploy was skipped leaves new data in `public/` that no
later feed deploy picks up — and the feed then republishes the stale `dist/` every two minutes,
logging "deployed to Cloudflare" each time. The site sat two runs behind for two hours with three
different datasets in three layers (served `auto-f83b13bbf84a`, `dist/` `auto-1d4e18e0fe7b`,
`public/` `auto-77cf6428cad6`) and nothing in the logs or the repo looked wrong. `deploy_assets`
now compares the two `index.json` manifests and compiles instead of shipping something older than
what is on disk. To check by hand:

```sh
curl -s https://lucasrgpedersen.com/botrankings/data/index.json | jq -r .run_id
jq -r .run_id ~/projects/portfolio/{public,dist}/botrankings/data/index.json
```

All three should agree. Note `field.bots` is the *distinct* count after duplicate and compliance
pruning, so it reads lower than the run manifest's bot count — 149 in the manifest is 139 published.

**And a deploy is blocked entirely while the site checkout is dirty**, including by your own
in-progress edits. That is deliberate — `astro build` compiles the working tree — but it silently
stops the ladder too, so commit or stash before walking away from the site repo.

```sh
cp tournament/systemd/botrankings-live.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now botrankings-live.timer
```

### The site's data bundle is not in git

`public/botrankings/data/` is gitignored in the portfolio repo. It reached 185 MB across 167 files
that are rewritten wholesale on every run, and committing it had grown `.git` to 202 MB — larger
than the data — in five days. Nothing depended on it being committed: production is served by
`wrangler deploy`, which uploads the working tree and never reads git.

That removed the side effect the deploy used to fire on. `_publish` committed the bundle, the
commit moved the site's HEAD, and `_deploy` triggered on HEAD moving. With no commit, HEAD never
moves, so **a data or feed refresh now calls `deploy_assets` explicitly**; `_deploy` is only for
source changes. If you ever restore the old commit-the-bundle behaviour, drop the explicit calls or
every tick will deploy twice.
