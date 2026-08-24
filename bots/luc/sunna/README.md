# Sunna — two miners, because the live ladder puts its ore four tiles out

`nott` with `_ROLES` at `(2, 1)` — a second economy Builder in the opening —
plus the derived ring index so the mender still sits after the miners.

## The finding this rests on

A second miner is not generally good or bad. Its value is a **dose-response in
how far the nearest ore sits from the Core**, measured on four independent map
sets:

| map set | nearest visible ore | second miner |
|---|---|---|
| `maps/orerich` (150) | 2 tiles | **-1.2 sd** (as `saga`) |
| wider long set (48) | ~2.5 | -0.3 sd |
| `maps/livelike` (39) | 3 tiles | +0.7 sd (McNemar z = +0.84) |
| `maps/longgame` (15) | 4 tiles | **+2.2 sd** (McNemar z = **+2.89**) |

Monotonic, and the mechanism moves with it: on the far end Harvesters go
1.23 -> 1.77 and the win rate 0.725 -> 0.808 over **240 strictly paired cells
against eight opponents**.

**The live ladder sits at the far end.** Decoded from 24 live map sides: the
nearest ore a Core can see is a median of **4.0 tiles**, and **92% of sides
have it beyond 2 tiles** — against 42% on `maps/orerich`. So the regime where
this change is worth +2.2 sd is the regime the ladder actually plays in.

That also means `maps/orerich` is unrepresentative on an axis I had not
checked. It matches live on ore *density* (46.1 per 1000 against 47.0), area,
wall fraction and Core separation — and misses on ore *placement relative to
the Core*, which is the axis this mechanism turns on. Every economy result
measured on it was measured in the wrong regime.

## Why it has to be in the opening

Three adaptive versions were tried and all failed: `LATE_BUILDERS_MINE` on,
with `ECON_BUILDER_ROUND` at 120, 60 and 40. On `maps/longgame` they score
0.673, 0.673 and 0.680 against this build's 0.767, and the reason is visible in
the metrics — `lbm40` spawns **5.83 Builders against this build's 4.60 and
still gets fewer Harvesters** (1.45 against 1.85). A Builder that arrives on
round 40 has less game left to mine and pays more cost scale for the privilege.
The second miner is worth having from round 1 or not at all.

A round-0 detector was also tried (`var`, a `FAR_ORE` doctrine bit) so the
change could be taken only where it pays. No threshold separates the regimes —
the best fires on 57% of long-game sides and 21% of `orerich` sides — so `var`
captured +0.2 sd where this build gets +1.8. Taking it unconditionally is the
better trade **given that live maps are 92% in the regime that wants it**.

## Numbers on the live-placement set

39 maps, four opponents, 312 strictly paired cells: 0.673 -> **0.699**
(+0.7 sd), Harvesters 2.68 -> 3.24.

## WITHDRAWN — it does not replicate off the set it was found on

Queued and then withdrawn within the hour. Tested on `maps/livelike2` — 69
freshly generated maps whose nearest visible ore is a median **4.0 tiles,
matching live exactly** — over 552 strictly paired cells against four
opponents:

| build | rate | vs `snotra_h` |
|---|---|---|
| `nott` | 0.721 | +0.011 (+0.4 sd) |
| `snotra_h` | 0.710 | — |
| **`sunna`** | **0.710** | **0.000 (McNemar z = 0.00)** |

Exactly level, and -0.4 sd against `nott`. Game length is not the hidden
moderator either: split inside that set it reads +0.1, -1.0 and +0.3 sd for
games under 100, 100-200 and 200+ rounds.

So the +2.2 sd holds only on `maps/longgame`, and **that set was selected
post-hoc** — the top 15 of 150 maps by median game length, chosen from the same
games that then produced the result. That is the classic shape of a spurious
finding, and the dose-response below is better read as a coincidence of three
points than as a mechanism: it does not survive on any independently
constructed set (0.0 sd on `livelike2`, -0.3 on the wider 48-map set, -1.2 on
`maps/orerich`).

The lesson is the useful part: **a map set selected from results cannot then be
used to measure them.** `maps/livelike` and `maps/livelike2` are constructed
from live terrain statistics alone and are safe; `maps/longgame` is not, and is
only fit for asking what happens in long games, never for deciding what to ship.

## Original argument, kept for the record

## Honest risk

The strongest cell (+2.2 sd) is fifteen maps chosen for producing long games;
the live-placement set is only +0.7 sd, and `maps/orerich` is negative. If live
maps behave like `livelike` rather than `longgame`, this is a small gain rather
than a large one. The dose-response and the live placement measurement are what
justify queueing it; the ladder settles it.
