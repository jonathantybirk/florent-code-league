# How ladder pairing actually works, and what that means for rating simulation

Written 2026-08-23 while adding `arms.simulated_rating`. Everything here is
measured against the league census, not assumed.

## Why this was needed

`ArmStats.elo` answers *how strong is this bot* — a maximum-likelihood Elo over
the opponents a build actually faced. The ladder answers a laggier question. A
**displayed** rating is a random walk that only drifts toward true strength over
hundreds of games, so a genuinely stronger bot can sit below the incumbent's
displayed rating for days after promotion. `best_challenger` promotes on
estimated strength; it has no way to see that lag.

Simulating the walk needs a model of *who we get paired against*. This document
is about getting that model right.

## Data

`tools/league_census/matches.jsonl` at commit `9790980` — 125,454 matches,
2026-08-01T07:02Z to 2026-08-22T20:21Z. (The log starts Aug 1; the platform keeps
nothing older, so nothing before that exists to check.)

| | count |
|---|---|
| all matches | 125,454 |
| rated (`triggeredBy: ladder`) | 71,989 |
| unrated | 53,465 |
| usable pairs after dropping 62 rows with a null `ratingBefore` | 71,739 |

Ranks are reconstructed per match from `ratingABefore` / `ratingBBefore`, so
every figure below reflects the standings *at the time of the match*, not today's.

**Only rated matches count.** The 53,465 unrated matches are test games ordered by
teams, and 162 of our own 200 most recent matches are the farm's own challenges.
Those describe our targeting policy, not the scheduler: they run out to rank
distance 23, where the scheduler never exceeds 12. Including them would have
taught the simulation our own habits.

## Finding 1 — pairing is a global perfect matching, not per-team draws

Rated matches arrive in bursts: **2,314 rounds**, a median of 34 matches over a
median pool of 68 teams (86 today). Within every round, across all 143,978 team-slots,
**no team is ever paired twice**.

So the scheduler builds one matching over the active pool each round.
`P(opponent | me)` is a *marginal of that matching* and never a parameter of it.
This is the single most important structural fact, and it is why several things
below cannot be modelled as independent per-team choices.

The spread — mean |rank distance| 2.93, max 12 — rules out adjacent Swiss
pairing, which would put nearly all mass at distance 1. It is the randomized
proximity-matching family.

## Finding 2 — the published kernel is correct

`live.json`'s `model.pairing_kernel` matches the census closely over all 71,739
pairs:

| rank distance | league-wide % | published kernel % |
|---:|---:|---:|
| 1 | 25.85 | 24.20 |
| 2 | 22.42 | 20.09 |
| 3 | 18.66 | 18.29 |
| 4 | 14.10 | 14.18 |
| 5 | 9.56 | 10.91 |
| 6 | 5.39 | 6.54 |
| 7 | 2.58 | 3.64 |
| 8 | 0.98 | 1.38 |
| 9 | 0.32 | 0.57 |
| 10 | 0.11 | 0.20 |
| 11 | 0.02 | 0.01 |

An earlier χ² on our own 38 rated matches also failed to reject, but at n=38 that
was underpowered and proved little. At n=71,739 it is settled.

## Finding 3 — direction is not 50/50, and it is not a parameter

The first model sampled |distance| from the kernel and then chose up or down
50/50. That is wrong near the top of the table, and right in the interior:

| slot | paired upward % |
|---:|---:|
| 0 | 0.0 |
| 1 | 18.8 |
| 2 | 33.7 |
| 3 | 45.5 |
| 4 | 55.2 |
| 5 | 57.4 |
| 6 | 57.3 |
| 8 | 52.7 |
| 10 | 48.8 |
| 10–60 combined | **50.7** |

Slot 0 has nobody above it, the deficit propagates downward, and it washes out by
slot ~10. Nothing in the scheduler decides this — it falls out of the matching
being global. A generative matcher (greedy exponential proximity, best-fit
β=0.45) reproduced neither the tail nor the slot-1/2 behaviour, so **the model
does not simulate the mechanism**. It samples the measured conditional instead.

## Finding 4 — everyone plays every round; slot is still not ladder rank

There is no opting out and no per-round absence. Pool size grows monotonically as
teams join and never shrinks:

| date | median pool |
|---|---:|
| Aug 1 | 22 |
| Aug 6 | 56 |
| Aug 12 | 74 |
| Aug 20–22 | 86 |

Across all **303 rounds since Aug 20 there is exactly one pool composition** — the
same 86 teams, every round, us included. A team enters the pool once it has
completed a match and stays forever.

*Slot* — position within the round pool — is nonetheless **not** ladder rank,
because the ladder carries teams that have never completed a match and therefore
have never been paired with anyone. On the snapshot in `fixtures/`, the ladder
lists 100 teams while only 58 have `matchesPlayed > 0`, and the census sees 57 of
those pairing that day. `matchesPlayed > 0` is the membership test.

Two corrections this forced, both to earlier drafts of this document:

1. An earlier version modelled per-team "participation rates" of 0.139–0.999 and
   sampled the pool from them. That was an artifact of averaging over the whole
   census: a team that joined on Aug 15 shows a low rate purely from not existing
   before then. Removed — the pool is the whole active field, and slot follows
   deterministically from the walk's current rating.
2. Everything in this document that says "we are at slot 5" is computed from
   `fixtures/`, which is an **Aug 6 snapshot** (rating 1865, 57 active teams). On
   Aug 22 we were at rating 1642, **slot 33 of 86**. The fixtures are for tests;
   a live run reads the current feed.

## What was built

`pairing_slots.json` (12 KB, regenerable from the census) holds
`P(opponent slot − my slot | my slot)` for slots 0–85, built from the **1,255
rounds whose pool was at least 68 teams** (Aug 8–22, 48,557 pairs) so the geometry
resembles today's rather than the half-sized ladder of early August. Every slot
has at least 320 observations.

`arms.simulated_rating(live, key, ladder_rows)` runs `sim_count` careers of
`sim_length` rounds. Per career it draws a win rate **once** per opponent from a
Beta posterior over our per-game record against that opponent's *current* build,
then holds it fixed. Returns `(mean, sd, se_of_mean)`.

**Why the draw is per career, not per game.** Per-game binomial noise is not
epistemic — it averages out, so an interval built from it shrinks toward zero as
`sim_count` rises and ends up describing the compute budget rather than the bot.
Holding the rates fixed within a career makes the spread mean "how well do we know
these matchups". `se_of_mean` is reported only as a convergence diagnostic: if it
is not small next to `sd`, raise `sim_count`.

**Unknown matchups are rerolled, not guessed.** If the pairing table hands back an
opponent we have no current-build record against, another draw is taken. Seeding
such matchups from the Elo expectation for the rating gap — an earlier design —
anchors the walk to the rating it started at, which is precisely the thing the
simulation exists to be able to disagree with.

**Stale opponent builds are dropped, not discounted.** A record against a version
an opponent no longer fields is not weak evidence about their new build; it is
evidence about a bot that no longer exists.

**No defaults anywhere.** Missing `k_factor`, `series_games`, team id, rating, an
empty active field, or a build with no usable records all raise. A plausible
number computed from a guessed k-factor silently models a ladder we are not on.

## Validation

- **Rating update.** `k_factor` is exactly 32, and `rating += k*(wins−expected)/
  series_len` reproduces the feed's own `delta` to the digit on all 38 of our
  rated matches in `live.json`.
- **Perfect matching.** 0 duplicate teams in 143,978 round-slots.
- **Fixed pool.** 1 distinct composition across 303 consecutive recent rounds.
- **Table stability.** Splitting the census in half by time, the per-slot
  conditional has total-variation distance 0.04–0.17 between halves, against a
  sampling-noise floor of roughly 0.09 at n≈1,150 per half.
- **Discrimination.** Builds separate (1757–1909 on the fixture snapshot) and the
  interval tightens with opponent coverage.

## One definition, two consumers

Delta elo is computed in exactly one place, `arms.simulated_rating`, and read by two
things: the farm, which promotes on it, and the live feed, which publishes it to the
site. The feed imports the function rather than vendoring it.

That is a deliberate correction. The first version reimplemented a one-round delta
inside `live_feed.py` on that module's own kernel and its `MATCHUP_PRIOR_GAMES`
smoothing, and the two drifted far enough apart to disagree on sign: the site showed
`v70` at -0.5 while the farm promoted it at +1.66. A column that contradicts the
promotion it exists to explain is worse than no column.

For the same reason `simulated_rating` seeds its default RNG from the build key
(`zlib.crc32`) rather than the clock. Two separate processes compute this number and
they must agree to the digit. `hash()` is unusable here: Python randomises string
hashing per process.

The feed's loader checks each candidate ladderfarm checkout for the symbols it needs
instead of trusting path order, because a machine can carry both a working copy and the
deploy target `sync.sh` writes, and the older one silently lacks them. A missing or
stale sibling costs the column, never the feed.

## Limitations

1. **The field is frozen.** Every opponent's rating is held at its current value
   for all `sim_length` rounds while ours moves. The whole ladder drifts at once
   in reality. This is the largest remaining assumption.
2. **Rerolling biases the simulated field toward teams we have played.** A build
   with 10 known opponents faces those 10 repeatedly rather than the true mix.
   This is deliberate — the alternative anchors the result to the starting rating
   — but it means the interval understates uncertainty for thinly-tested builds,
   and the reroll rate is worth watching.
3. **History cannot validate the current field.** Our slot when we were last at a
   given rating describes the standings of that week, not today's.
4. **Rounds ≠ wall-clock.** `sim_length` counts rounds; converting needs
   `scheduler_period_minutes`.
5. **Census floor.** Nothing before 2026-08-01 exists.

## Reproducing

```
git show 9790980:tools/league_census/matches.jsonl > matches.jsonl
```

Then rebuild `pairing_slots.json` by grouping rated matches on `createdAt`
truncated to the second, keeping rounds with a pool of at least 68 teams, ranking
each round's participants by `ratingBefore`, and counting signed slot offsets per
slot.
