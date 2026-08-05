# Skadi

`vidar` with one constant changed: **`ECON_MAX_TOTAL_BUILDERS` 12 -> 16.**

That is the entire diff. It is a small change and it produces a small gain, but
the gain is real, reproducible and never negative, and it was found by tracing a
specific failure rather than by sweeping.

## Measured

fcode 2.3.6, both seats, against bots taken from `x/luc` and `elias_dev`.
The engine is deterministic, so these numbers are exact rather than sampled --
the same configuration replays to the same result every time.

| panel | games | vidar | skadi |
|---|---|---|---|
| weak matchups (vigil, steward, prospect), 21 official maps | 126 | 0.754 | **0.762** |
| same three, 24 generated maps | 144 | 0.743 | 0.743 |
| full panel (odin, steward, prospect, vigil, heimdall, gobbleglitch), 21 maps | 252 | 0.802 | **0.806** |

Better on the pool, level off-pool, better overall. **522 games, never worse.**

Reproduce:

```sh
uv run python tools/bench.py jon/skadi --panel bench/vigil,bench/steward,bench/prospect --maps 21 --jobs 8
uv run python tools/generate_maps.py --out maps/gen --count 24 --seed 7   # off-pool set
```

## Why this constant

`ECON_MAX_TOTAL_BUILDERS` is not a headcount. It is a **lifetime** budget: the
Core counts every Builder it has ever spawned in `builders_spawned`, and once
that reaches the cap it stops replacing them for the rest of the match, however
many are alive and however much titanium is banked.

The cap exists for a good reason -- a replacement is +20% on every price the team
pays for the rest of the game, so an attrition war fought by respawning is a war
you lose slowly. That reasoning is about **combat losses**. It is wrong about the
other way this bot loses Builders.

Traced with `tools/replay_forensics.py --deaths` on `bridge` against vigil:

```
r48   TEAM_A builderBot  id=5    {} total=0
r53   TEAM_A builderBot  id=3    {} total=0
r140  TEAM_A builderBot  id=138  {} total=0
... nine more, every one with total=0
```

**Eleven of our twelve Builders died having taken zero damage.** None of them was
killed; every one was a `WRITE_OFF_STUCK_BUILDERS` stand-down, which
self-destructs a Builder that has failed to path so the Core can re-roll it onto
a spawn tile that is not walled in. That is a sound mechanic -- but each re-roll
spends one of the twelve lifetime slots. Twelve stand-downs later the Core
stopped spawning entirely, and the game ended at round 1000 with **no Harvesters
at all** and the titanium-collected tiebreak lost.

Unopposed on the same map this bot has four Harvesters by round 15, so the
economy planner is not the problem. The lifetime budget was being consumed by
re-rolls rather than by casualties.

Sixteen is where the gain saturates: 12 -> 16 is +1 game on the pool and level
off-pool; 20, 40 and 80 are all no better than 16 on the pool, and 40 measured
**worse** off-pool (0.729) because at that point the extra bodies really are
paying +20% each for nothing.

## What was tried and rejected getting here

Roughly thirty other changes were measured across three rounds and every one was
worse or inert; they are recorded in
[`llm-slop-analysis/jon/reference/beating-vidar-negative-result.md`](../../../llm-slop-analysis/jon/reference/beating-vidar-negative-result.md)
so nobody repeats them. The short version:

* Every turret constant is already at its optimum -- guard Sentinels 2, siege
  battery 2, `AMMO_TARGET` 120, harvester cap 4. Moving any of them costs games.
* Gunner guards instead of Sentinel guards: -4.0pp on the pool, -5.5pp off it.
  The ladder's leaders play Gunner-first and it does not transfer to this bot.
* `CLAIM_SLOTS` looked like a hard economy ceiling (two live ore reservations
  against six dead relay slots). Expanding it to five produces **byte-identical
  replays** -- the claim table was never full.
* Sentinel targeting refinements (hunt the mender when the siege stalls, prefer
  kills, prefer untended targets) are all exactly inert: on this panel the
  Sentinel value comes from the guard role, not the siege role.

## The unexploited edge, for whoever picks this up next

Units act in ascending global entity id **across both teams**, and ids are handed
out in spawn order -- the first team's Core is id 1, the second team's is id 2.
So the first-spawning team wins every tie for the whole match: the race to a
tile, the first shot in a turret duel, the heal that lands before the shot.

Measured over 144 off-pool games, this lineage scores **0.792 as Team A and
0.694 as Team B** -- a 9.8pp gap that has nothing to do with the opponent. The
seat is knowable at round 0 from `ct.get_team()`, and nothing in our lineage
reads it. Three seat-conditional responses were tried (more guard, refuse the
siege, press the advantage) and all were neutral or worse, so the lever is
confirmed and the response is still open.
