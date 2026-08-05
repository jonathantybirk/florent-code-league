# Skadi

`vidar` with two changes, both found by tracing a specific failure rather than
by sweeping:

1. **`ECON_MAX_TOTAL_BUILDERS` 12 -> 16** -- the lifetime Builder budget.
2. **`_ROLES[BLITZ]` (0 economy, 2 attackers) -> (1, 1)** -- the blitz opening
   now mines.

Nothing else differs from vidar: `core.py`, `builder.py`, `main.py`, `gunner.py`,
`sentinel.py`, `launcher.py` and `utils.py` are byte-identical.

## Measured

fcode 2.3.6, both seats, against bots taken from `x/luc` and `elias_dev`.
The engine is deterministic, so these numbers are exact rather than sampled --
the same configuration replays to the same result every time.

| panel | games | vidar | skadi |
|---|---|---|---|
| weak matchups (vigil, steward, prospect), 21 official maps | 126 | 0.754 | **0.762** |
| same three, 24 generated maps | 144 | 0.743 | **0.757** |
| full panel (odin, steward, prospect, vigil, heimdall, gobbleglitch), 21 maps | 252 | 0.802 | **0.806** |
| four opponents, the 5 BLITZ maps (core distance <= 6) | 40 | 0.700 | **0.725** |
| wide 12-bot panel, 21 maps | 504 | 0.796 | **0.798** |

**Better on every panel, worse on none.**

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

## The second change: the blitz had no economy at all

`doctrine.py` picks BLITZ when the Cores are within `BLITZ_MAX_DISTANCE = 6`, and
`_ROLES[BLITZ]` was `(0 economy, 2 attackers)` -- **nobody mines**. The reasoning
was that a Core six tiles away is decided before economy can matter.

The enemy gets a vote. Traced on four unrated ladder matches against Pantheon,
Pivot, sporks and team lazy, decoding all fifteen games: **every game in which we
finished with zero Harvesters had a core distance of exactly 6**, and we lost two
of the three. Against sporks on 10x10 and 16x12 we ended with **0 Harvesters
against their 7 and 8**, losing on rounds 124 and 115 -- they answered the rush,
survived, and then simply out-mined a bot that had nothing behind its attack.

The existing fallback cannot reach this. A later Builder does convert to mining
when `ECON_EXPAND_FLAG` or `ECONOMY_DEAD_FLAG` is set, but `INCOME_GRACE_ROUND`
(60) plus `INCOME_WINDOW` (60) means the first income verdict lands at round
**120** -- after both of those games had already ended. Speeding the watchdog up
was measured (grace/window 40/40 and 30/30) and changes nothing on these maps,
because the Builder side still has `economy_builders = 0`.

So the fix is at the role table: the blitz keeps an attacker and a guard and now
also keeps one miner. Measured on the five local maps with core distance <= 6
(showdown, sprint, gen/r05, gen/r11, gen/r19) against vigil, steward, prospect
and odin: **0.700 -> 0.725**, and off-pool overall **0.743 -> 0.757**. A blanket
"open the economy at round N" deadline was tried first and is worse at every
value (80 -> 0.625, 120 -> 0.675, 160/200 -> no change); abandoning the blitz
early throws away the games it wins.

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
