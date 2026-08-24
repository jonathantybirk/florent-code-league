# The 21-map pool, and why the synthetic corpora are now stale

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

`fcode starter` syncs **21** competition maps as of 2.3.3, up from 15. The
package itself no longer ships `data/maps/`, so the CLI is the only source.

The six additions -- `bridge`, `jackpot`, `showdown`, `string`, `sweden`,
`vase` -- are not more of the same. They are a different design style:

| | old 15 | the 6 new | all 21 |
|---|---|---|---|
| median area | 484 | **184** | 375 |
| ore per 100 tiles | 2.75 | **5.62** | 3.22 |
| median wall % | 5.0 | **21.2** | 7.1 |
| median aspect ratio | 1.00 (square) | **0.68** | 1.00 |

Half the size, twice the ore density, **four times the walls**, and rectangular
rather than square. `bridge` is 21x8.

## Consequence for our testing

`maps/generated/representative/` profiles the **old 15** almost exactly --
area 484, ore 2.75, wall 5.0, aspect 1.00 -- so it now under-represents the
current pool badly and contains nothing like the new style. It should be
re-profiled against all 21 before its numbers are quoted as generalisation
evidence again. `maps/generated/stress/` is unaffected, since it never claimed
to match a distribution.

## Does the new style change results?

Measured with the converted Vanguard, same bot, split by pool:

| opponent | old 15 | new 6 |
|---|---|---|
| `undertow` | 22-8 (73%) | 9-3 (75%) |
| `claude_challenger_1` | 30-0 (100%) | 10-2 (83%) |

So the tight, walled maps are meaningfully harder against at least one
opponent, and a bot tuned only on the old pool would not have noticed.

## Tooling status on 2.3.3

Re-verified rather than assumed:

- replay decoding (`scratch/replaylib.py`) still parses correctly -- entity
  markers, positions, HP deltas and Core damage all read back right;
- the map-rule checker passes all 21 official maps and all three synthetic
  corpora;
- the `ammo` column in `scratch/arena.py` measured stacks delivered *into*
  turrets, which is always zero now; replaced with shots fired.
