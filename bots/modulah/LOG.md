# modulah log

## Where things stand

`lib/` is a verified utility layer — the first shared library in the repo.
`diag` re-checks every engine fact it rests on (8/8 against 2.3.6).

Bots are **not yet competitive**. Measured, 6 maps, both seats:

| build | vs steward/vidar/odin | vs starter | killed at round |
|---|---|---|---|
| beacon | 0/12 | — | 181–312 |
| aegis  | **0/18** | 3/6 | **72–92** |

aegis out-collects steward and odin (1798 vs 501/583 mean titanium) and dies
*faster* than beacon did. The top three kill our Core around round 72–92,
which is a rush landing before any defence exists. Economy is not the gap.

**The deployed online bot is untouched** — `v34
(steward_hardened_reinforced f1f2bda)`, rank #10/108 at 1791, managed by the
farm. Nothing from this branch has been submitted, and nothing should be until
it beats the flagship locally.

## The next thing to fix

Dying at round 72 means the first Gunner arrives far too late. Order of work:

1. **Opening defence.** A turret sited before the rush arrives, not after
   `max_burst` reports one. `placement.best_defensive_site` already answers
   *where* — the gap is that nobody calls it until a threat is visible.
2. **Pathing.** `_step` is greedy and bounces: a Builder was traced
   oscillating (7,7)↔(7,8) laying conveyor back and forth. Steward uses a BFS
   distance map; this needs the same.
3. **Doctrine.** Steward branches RUSH/FORTIFY/BLITZ on Core-to-Core Chebyshev
   distance ≤ 6, measured over 138,785 matches. aegis has no opening at all.

## Engine facts established (all measured, not from docs)

The docs contradict themselves on Splitters; these came from experiment and
from disassembling `fcode_engine.*.so` (Rust, stripped, `battlecode-platform`).

- Conveyors move **once per round, after every unit has acted**
  (`distribute_resources` sits between the unit loop and `update_cooldowns` in
  `GameRunner::run`). Unit order has no economic effect.
- A stack `h` hops out is credited at `T+h`. Verified at h=1 only; congestion
  and merges are arbitrated by `edge_priority` (per-edge LRU plus a uniform
  random tie-break) whose state the API does not expose.
- A Splitter with one accepting output delivers **identically to a Conveyor**
  (144 stacks each over 575 rounds). The 1/3 weight is wrong; it is 1/k over
  outputs that can currently accept.
- A Conveyor pointing at bare ground **holds its stack forever** rather than
  dumping it, so a backed-up branch silently leaves a Splitter's rotation.
- Store writes land at the **next round**, invisible to later-id units in the
  same round. One writer per slot is therefore forced.
- Turrets are **line weapons**: Gunner 3 tiles cardinal / 2 diagonal
  (`dist_sq` 9 / 8), Sentinel 5 / 4 (25 / **32**). Core vision is 36, so the
  Core sees everything that can shoot it — margin 4.
- Core vision is the **union** of radius-6 discs over the 2×2 footprint (140
  tiles, not 113). Walls do not occlude.

## Store schema

| slot | contents |
|---|---|
| 0 | econ: stacks arriving t+2..t+6, 3 bits each |
| 1 | threat: hp (2-hp bins), 4-round dhp (signed), max_burst |
| 2–3 | up to 4 enemy turrets: offset, type, facing |
| 4–15 | one per Builder: action, target, hp, heartbeat |

Read econ with `comms.arrivals_from_now()`, never `unpack_econ()` — the reader
is always a round behind the writer, and the raw buckets are indexed from the
write.
