# Nott — stop locking a quarter of the opening bank into ammunition

`snotra_h@6951e03` with `AMMO_TARGET` 120 -> 60 and `COMBAT_AMMO_FLOOR` 80 ->
30. Two constants, one file (`core.py`, not `constants.py`).

## The observation

Decoded from live ladder games, titanium converted to ammunition by round 30:

| | us | them |
|---|---|---|
| vs 0033 | **162** | 35 |
| vs Besvikomat | **147** | 54 |
| vs Coreflood | **179** | 81 |
| vs O(1) | **195** | 28 |
| vs Big O | 176 | 140 |

Two to seven times what our opponents convert. The cause is
`AMMO_TARGET = 120` firing on **round 0**, before a single turret exists: 120
of a 500-Ti opening bank, locked into a resource only turrets can spend, during
the phase where titanium compounds fastest.

## Numbers

150 ore-realistic maps (`maps/orerich`), both seats, 300 games a cell, baseline
in the same run.

| opponent | `snotra_h` | `nott` | |
|---|---|---|---|
| `vanguard` | 0.7033 | **0.7100** | +0.007 (+0.2 sd) |
| `undertow` | 0.6767 | **0.7133** | +0.037 (+1.0 sd) |
| `spar_sentinel` | 0.4933 | **0.5033** | +0.010 (+0.2 sd) |
| **pooled, 900 games** | 0.6244 | **0.6422** | **+0.018 (+0.78 sd)** |

Small on this base. What makes it worth queueing is that it replicates on a
second, unrelated base — `vidarr@bbfaa9c`, 716 lines and a different lineage:

| opponent | `vidarr` | `vidarr` + same change |
|---|---|---|
| `vanguard` | 0.6100 | **0.6833** (+1.9 sd) |
| `undertow` | 0.6533 | **0.6633** (+0.3 sd) |
| `spar_sentinel` | 0.4333 | **0.4767** (+1.1 sd) |
| **pooled** | 0.5656 | **0.6078** (+1.82 sd) |

**Across both bases: 1071/1800 -> 1125/1800, +0.030 (+1.85 sd), and 6 of 6
cells favour the change (sign test p = 0.016).** After a session in which
roughly twenty mechanisms measured null or negative, six for six in the same
direction is the first result that replicates.

The mechanism is visible in the metrics: the first Gunner goes up around round
23 instead of 26 against `vanguard` and 31.5 instead of 32 against `undertow`,
because the titanium is there when a turret is wanted rather than sitting in
the ammunition pool waiting for one.

## Caveats worth keeping

- The effect is **+3 points**, not a transformation, and on this base alone it
  is +0.78 sd — under the usual bar. The two-base replication is what carries
  it.
- `vanguard` is a newly validated instrument (iteration 168): it is the
  best-balanced external opponent at 0.575 and its ranking of our builds agrees
  with the live raw records, which no earlier fixture did.
- One pooling trap avoided: `snotra_h`'s `vanguard` baseline exists in two runs
  (600 games) against `nott`'s 300, and pooling those unequal samples across
  opponents of very different difficulty produced a spurious **-0.1 sd**. Every
  number above uses matched 300-game cells.
