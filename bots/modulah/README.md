# modulah

A utility layer for Florent Code League bots, plus a reference bot that uses it.

The problem this is trying to fix is not that our bots are bad. It is that the
same calculation exists in eight places with eight small differences, so
improving it means finding all eight, and nobody ever does. Here there is one
copy of each idea in `lib/`, and bots are assembled from it.

```
lib/            the only place anyone edits
  geometry.py   footprints, turret rays, safe tile access
  comms.py      the 16-slot store as a typed schema
  econ.py       titanium arriving per round, walked backwards from the Core
  threat.py     core hp, trend, and worst-case incoming damage
vendor.py       copies lib/ into each bot (the engine needs flat, self-contained dirs)
selftest.py     offline checks for the packing layer
beacon/         reference consumer -- shows the shape, not a competitor
diag/           re-verifies every engine fact lib/ assumes, against the live engine
```

## Why vendoring rather than a shared package

The engine loads a bot as a flat directory and runs each unit in its own
subinterpreter: `import comms`, never `from ..lib import comms`. A submission
must be self-contained. So shared code has to be physically copied — which is
exactly how the divergence started.

The fix is to make copying mechanical and one-directional. `lib/` is the only
editable copy; vendored files carry a `# GENERATED` header; drift is detectable:

```bash
uv run python bots/modulah/vendor.py --all      # refresh every bot
uv run python bots/modulah/vendor.py --check    # fail if any copy is stale
```

Run `--check` before pushing. A stale vendored copy is a bug that only shows up
as the bot behaving like last week's code.

## Verified engine facts

Everything below was measured against **fcode 2.3.6**, either by disassembling
`fcode_engine.cpython-313-darwin.so` or by controlled matches. The official docs
contradict themselves on splitters, so they were not used as a source. `diag`
re-checks all of it — run it after every fcode bump.

**Conveyors move once per round, at the very end.** `distribute_resources` has
exactly one call site, inside `GameRunner::run`, after the loop that calls every
unit's `run()` and before `update_cooldowns`. So unit order has no economic
effect: every unit in a round sees the same balance. A Conveyor built during
round R is live in that same round's pass; a line cut during R does not move.

**A stack `h` hops from the Core is credited at round `T+h`.** Verified at
h=1 (feed tile held at R040, balance rose at R041).

**Store writes land at the next ROUND, not the next turn.** The Core (id 1, acts
first) wrote 1003 at r=3; a Builder later in r=3 read 0, and read 1003 at r=4.
This is why **one writer per slot is forced** — two units sharing a word both
read the same start-of-round snapshot and the second write destroys the first.
There is no atomic accumulate, so slots, not bits, are the scarce resource.

**Splitters pick among outputs that can currently accept.** A Splitter whose only
live output feeds the Core delivers identically to a plain Conveyor — 144 stacks
each over 575 rounds. So the weight is `1/k` over *accepting* outputs, not a flat
`1/3`. Blocked branches remove themselves: a Conveyor pointing at bare ground
holds its stack forever rather than dumping it, so once full it stops accepting.
Titanium never leaks.

**Turrets are line weapons, not area weapons.** Fixed-length rays along 8 facings:

| | cardinal | diagonal | max reach |
|---|---|---|---|
| Gunner | 3 tiles (`dist_sq 9`) | 2 tiles (`dist_sq 8`) | 9 |
| Sentinel | 5 tiles (`dist_sq 25`) | 4 tiles (`dist_sq 32`) | 32 |

`GUNNER_VISION_RADIUS_SQ = 13` is vision only — a Gunner sees further than it
shoots. A Sentinel at offset `(3,4)` is inside its own reach and can *never* hit
that tile, because `(3,4)` lies on no ray. `geometry.can_ray_reach` matches the
engine tile-for-tile (20 gunner / 36 sentinel tiles, verified by `diag`).

**Core vision is the union of radius-6 discs over the 2x2 footprint** — 140 tiles
on open ground, not the 113 of a single disc. Walls do not occlude it. Since
Sentinel's worst reach is 32 and vision is 36, **the Core sees everything able to
shoot it**. That margin is 4; `diag` fails loudly if a patch erodes it.

**Splitter tie-breaks are random.** `distribute_resources` calls
`rand_core::block::BlockRng::generate_and_set` immediately after `edge_priority`,
inside the selection loop. So a fork with several accepting outputs is a genuine
random draw, not a predictable rotation.

## Store schema

| slot | owner | contents |
|---|---|---|
| 0 | Core | arrival schedule, t+2..t+6, 3 bits each |
| 1 | Core | hp (2-hp bins), 4-round hp trend (signed), worst-case burst |
| 2-3 | Core | up to 4 enemy turrets: offset, type, facing |
| 4-15 | Builders | one word each: action, target, hp, heartbeat |

Every word carries a 4-bit heartbeat (`round & 0xF`) so readers can spot a slot
whose owner died — a Builder never releases its slot.

**Why the economy window is t+2..t+6.** Not t+1: a hop-1 stack is credited at
T+1 and the write only becomes readable at T+1, so every reader already has it in
`get_global_resources()`. Not t+7: hop `h` is at most `h` steps from the
footprint, so `dist_sq <= h²` against a limit of 36 — six hops is the last one
guaranteed visible for *any* chain shape.

**Read economy through `comms.arrivals_from_now()`**, never `unpack_econ()`
directly. A reader is always at least one round behind the writer, so bucket
index is not "rounds from now". Observed live: the Core computed `[1,0,0,0,0]`
while Builders read `[0,1,0,0,0]` — same stack, one hop further out. The helper
re-anchors to absolute rounds using the heartbeat and drops buckets that have
already landed.

## Decisions taken

Where the thread disagreed, this is what got built and why. All are cheap to
reverse.

- **Five economy buckets (15 bits), not a 2-bit class.** A coarse class loses the
  wait-one-round decision — "10 Ti next round" and "50 Ti in five" average to
  something useless. Callers wanting Lucas's coarse reading get it free from
  `econ.titanium_over(schedule, n)`.
- **The Core gets two slots, not one crammed word.** Slots are the constraint but
  we are not near the limit, and cramming forces quantisation choices that buy
  nothing. Bits inside a word have no competitor.
- **hp in 2-hp bins, not 4.** Damage comes in 2 / 7 / 18; `gcd` with 4 is 1, so
  core hp lands on every residue. 4-hp bins throw away real state at exactly the
  low-hp end where it decides whether you survive the round, and save one bit
  nothing else wanted.
- **No "damage this round" field.** `SENTINEL_FIRE_COOLDOWN` is 2, so that number
  reads 0 half the time while you are being killed. The 4-round mean is the
  smallest phase-invariant window.
- **`max_burst` counts turrets *positioned* to fire, not only those aimed.** A
  rotate is 10 Ti and one round. Aimed-only reads 0 right up until it doesn't.

## Testing

```bash
uv run python bots/modulah/selftest.py                          # packing, offline
uv run fcode run modulah/diag starter maps/eider.map26 --tle 0   # engine facts
uv run fcode run modulah/beacon starter maps/eider.map26 --tle 10
```

`diag` currently reports 8/8. `beacon` completes 1000 turns at the server's 10 ms
TLE on eider, archipelago and duel.

**`beacon` is not competitive and is not meant to be.** Its economy is one
Harvester and one chain per Builder; it loses to `starter` on titanium. It exists
to prove the information layer works end-to-end and to show the intended shape:
`main.py` dispatches, one brain module per unit type, every shared calculation
from `lib/`.

## Known gaps

- **`hop h -> T+h` is verified only at h=1.** Under a saturated trunk or at a
  merge, arrival order is decided by the engine's per-edge priority — an LRU-ish
  key plus a uniform random tie-break, both read out of the binary — whose state
  the API does not expose. Deep buckets on a congested network run optimistic.
  The sort direction of `edge_priority` is still undecoded; settling it would
  turn the hop rule from an assumption into a guarantee.
- **`threat.max_burst` has not been exercised against a live enemy turret.**
  `starter` never brought one within reach in 1000 rounds. The geometry it rests
  on is verified exactly; the `can_fire_from` blocking path is engine-provided
  but unobserved end-to-end. A purpose-built aggressive sparring bot, or a hand-
  made map with the cores close together, would close this.
- **No pathfinding, no map memory, no role assignment, no offensive placement.**
  Deliberate — those were next on the list, and they want the information layer
  underneath them first.
