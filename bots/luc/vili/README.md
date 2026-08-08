# Vili — don't buy the multiplier before the thing it taxes, part two

`hoenir@1e5de25` with the same ordering rule applied at the second site.

## The rule

Every structure you build raises `get_scale_percent`, which raises the price of
*everything you build afterwards*, permanently. Measured: scale reaches 243 by
round 30 on a normal opening, and a Harvester that cost 20 Ti at the start costs
48 Ti after it. So the opening is not a list of things to build — it is an
ordering problem, and the things that make money have to come before the things
that only cost.

`hoenir` applied that to turrets: hold the first Gunner until two Harvesters are
running, unless the Core is already under alarm. Worth 0.633 against `bifrost`'s
0.610.

The Launcher ring is the same trade and was left untouched. Each Launcher is +10
on the multiplier, the ring is laid in the opening, and it is laid *before* the
Harvesters whose price it raises. This build gates `_run_launcher_ring` on the
identical test — `_turret_tax_is_affordable`, which releases on two Harvesters,
on round 60, or immediately if the Core alarm bit is set.

## Numbers

21 official maps, both seats, 42 games a cell.

| vs | | | harvesters |
|---|---|---|---|
| `hoenir` (parent) | 23/42 | 0.548 | 1.64 |
| `bifrost` | 26/42 | 0.619 | 1.69 |
| `steward_hardened_reinforced` | 29/42 | 0.690 | 2.05 |
| `mimir` | 30/42 | 0.714 | 2.02 |
| `spar_sniper` (grind fixture) | 30/42 | 0.714 | 2.02 |
| **mean** | 138/210 | **0.657** | floor **0.548** |

Best mean and best floor this lineage has recorded — `hoenir` is 0.633/0.524.

The mechanism shows up in the metric it predicts: Harvesters built rises to
1.64–2.05 from `hoenir`'s 1.38–1.90. It does not break the 2.3-Harvester ceiling
that has held all session against a map ceiling near 6, so the ceiling has some
other cause; this only stops one thing from making it worse.

## Honest size

The head-to-head against its own parent is 0.548, about 0.6 sd on 42 games —
suggestive, not settled. What makes it worth shipping is that the whole panel
moves together and the mechanism was predicted before it was measured, on the
same principle that already paid once.

CPU: worst turn 2,693 us against the 10,000 limit, zero over. Deterministic
across three runs.
