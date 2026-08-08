# Snotra-h — rank by the distance you actually walk, everywhere it matters

`snotra@34b0ce8` with the same fix applied at a second site.

## The defect, and why it has siblings

`_pick` sorted deposits by **Chebyshev straight-line distance** and took the
first one that routed, while `travel` — the real pathfinding distance — was
computed a line later and never compared. Around a wall the two orders differ,
so the Builder walked to the deposit that merely *looked* nearest. `snotra`
fixed that by pricing four candidates and taking the true minimum.

That is a shape, not a one-off. `_harass` does the same thing: it sorts enemy
economy targets by `(priority, Chebyshev)` and then walks a real path to them.

This build re-prices the head of that list — only the head, and only within one
priority class, so the cheap ordering still decides *what* is worth hitting and
the real distance only decides which of the equally valuable ones is nearest.
Bounded at four candidates so the extra searches cannot cost a turn.

## What is *not* the mechanism

Worth stating plainly, because the parent shipped under the wrong explanation.
`snotra` was built on the theory that conveyors are expensive and the win came
from pricing them. A weight sweep says no: weights **0, 2, 3, 5 and 8 all score
exactly 26/42** against mimir. The belt weight does what it claims — conveyors
fall from 12.00 at weight 0 to 11.00 at weight 3 — and does not move a single
game. Widening the candidate window from 4 to 8 (`sn8`) also measured
**identical**, 0.500 head to head.

So the effect is narrow and worth stating exactly:

- looking at **more than one** candidate is the entire mechanism;
- **how many** more stops mattering past about four;
- **how they are weighted** does not matter at all, including not at all.

## Numbers

21 official maps, both seats, 42 games a cell.

Against the live lineage:

| vs | | |
|---|---|---|
| `snotra` (parent) | 23/42 | 0.548 |
| `mimir` | 26/42 | 0.619 |
| `hodr` | 26/42 | 0.619 |
| `vidar` | 29/42 | 0.690 |

Against a wider panel:

| vs | | |
|---|---|---|
| `gefjon` | 24/42 | 0.571 |
| `steward_hardened_reinforced` | 24/42 | 0.571 |
| `spar_sniper` (grind fixture) | 25/42 | 0.595 |
| `spar_mender` | 32/42 | 0.762 |
| `vidar_guard` | 33/42 | 0.786 |
| `odin` | 34/42 | 0.810 |
| **mean** | 172/252 | **0.683**, floor **0.571** |

It beats every bot in the zoo, and the floor of 0.571 is better than any figure
this lineage has recorded — the flagship's own README claims 0.548.

**Live**, after two of four queued rounds: **32/50 = 0.640** model-free on raw
game win rate, against `fulla` 0.560, `snotra` 0.560, `mimir` 0.550 and `hodr`
0.507. Fifty games is about two standard deviations above even, so it is the
best live number of the day and still not a settled one.

## Honest size

On the three opponents both it and `snotra` faced, it is 81/126 against
snotra's 80/126 — one game — and the head-to-head 0.548 is 0.6 sd. The wider
panel and the live number are what make it look better than its parent, not the
direct comparison.

CPU: worst turn 3,717 us against the 10,000 limit, zero over, and *better* than
snotra's 5,478 because the re-rank replaces walking with searching.
Deterministic across three runs.
