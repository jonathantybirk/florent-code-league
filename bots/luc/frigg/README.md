# Frigg — shoot the mender at the range a Sentinel can actually reach

`hlin@a72a7dc` with `BUILDER_PRIORITY_RADIUS_SQ` 20 → 32.

**Not queued.** Level with its parent locally, for a reason the local panel
cannot fix. It is here ready to queue once `lofn`/`hlin` report live.

## The defect

`sentinel.py` rule 1 gives a Builder Bot priority over everything, and its own
comment says why: *"shooting a Core past a mender is 10 ammunition a shot spent
to lose slowly, and shooting the mender ends it."*

The rule is gated on `BUILDER_PRIORITY_RADIUS_SQ = 20`. A Sentinel reaches
**r²=32**, and a siege Sentinel is deliberately emplaced at the far end of that
range, where the Core's defenders cannot answer it. So the mender standing on
the Core sits at ~32 — **outside** the priority radius — and the Sentinel skips
rule 1 and shoots the Core.

## The evidence

Decoded live replays, our 0-5 loss to Pivot (rank 7). Two of the five games:

| | damage we took | damage we dealt | turns | result |
|---|---|---|---|---|
| game 1 | **0** | 2828 | 1000 | lost on titanium 20 vs 10,045 |
| game 2 | **0** | 4123 | 1000 | lost on titanium 14 vs 6,986 |

A Core has 500 HP. Dealing 2828 to it without a kill, with our own Core never
scratched, is the mender arithmetic playing out exactly as the comment
describes — in the one situation the constant was too small to cover.

## Numbers

Four opponents, three map sets, 516 games:

| vs | combined | |
|---|---|---|
| `hlin` (parent) | 78/156 = **0.500 ±0.078** | 0.0 sd |
| `lofn` | 82/156 = 0.526 | +0.6 sd |
| `vili` | 33/51 = 0.647 | +2.2 sd |
| `spar_mender` | 124/153 = 0.810 | (`hlin` scores 0.816) |

**Exactly level.** Siege Sentinels are built about 0.2 times a game internally,
so a rule about what they shoot almost never executes. The panel cannot price
this change; the ladder can, because Pivot posts a mender on its Core in every
game and our Sentinel is currently choosing to shoot past it.
