# spar_sentinel — the live meta, as a fixture

**Not a candidate.** This is a sparring partner. Do not queue it on the farm.

## Why it exists

Every bot in the internal zoo answers with Gunners: `vili` builds 3.40 a game
and 0.14 Sentinels. The live ladder does the opposite — economy-funded Sentinel
mass — and our four worst live matchups all play it. So the internal panel could
not see the thing that was beating us, and a build could look level internally
while losing 3-to-1 on the ladder.

This is `vili`'s economy with every turret seat bought as a Sentinel whenever
titanium allows (six `ct.build_gunner` call sites redirected). It builds **2.38
Sentinels to 0.73 Gunners**.

## It reproduces the live result

21 official maps, both seats, 42 games a cell.

| our bot | vs spar_sentinel | its live number |
|---|---|---|
| `steward_hardened_reinforced` (live flagship) | **0.262** | Pivot 0.25, O(1) 0.31, 0033 0.37, I Stone 0.41 |
| `mimir` | 0.262 | |
| `spar_sniper` | 0.262 | |
| `bifrost` | 0.381 | |
| `hoenir` | 0.405 | |
| `vili` | **0.667** | not yet played live |

The flagship's 0.262 against this fixture sits inside the range of its four
worst live matchups. That is the point of the fixture: the panel now contains
the style the ladder actually runs.

## What it immediately showed

`vili` is worth far more than its panel mean said. Against the zoo it beats
`steward_hardened_reinforced` 0.690; against the live meta the two are 0.667
and 0.262 — a 40pp gap on the only matchup that is costing us rank.

The gap is concentrated in the cost-scale ordering fixes: 0.262 (flagship) →
0.381 (`bifrost`, ferry slot) → 0.405 (`hoenir`, turrets held) → 0.667 (`vili`,
Launcher ring held). Holding the ring is worth 26pp against Sentinel mass and
was worth 5pp against the zoo, which is why the panel undersold it.

## Caveat

It is `vili` wearing a different turret, not a real opponent's code. It shares
our pathing, our doctrine and our opening, so it tests *our answer to Sentinel
mass* and not *their whole bot*. Treat a number against it as a style signal,
not as a prediction of a specific team.
