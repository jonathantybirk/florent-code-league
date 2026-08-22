# Sentinel rush

One Builder walks to the enemy Core and stands up four Sentinels firing into it. No economy, no
defence, no second unit, no fallback targets. Everything is spent on arriving early and killing fast.

## The budget

All of it measured in-engine on **fcode 2.3.9**, not read off the docs. Probes are in
`bots/probes/` -- `rushmath` (damage, reload, line semantics), `corefoot` (Core footprint),
`losfire` (firing through a blocker), `firefrom` (planning out of vision), `st_range` / `st_ver`
(the comms store).

| | Ti | note |
|---|---|---|
| starting titanium | **500** | measured; not documented anywhere |
| spawn one Builder | 30 | scale 1.00 -> 1.20 |
| Sentinel 1-4 | 36 + 42 + 47 + 53 = **178** | +20% of base per turret, and costs truncate |
| ammunition | **280** | 28 shots of 10, for 504 damage against 500 HP |
| **total** | **488** | **margin +12 before a single point of income** |

Passive income is 10 Ti / 4 rounds and the walk is 9-44 rounds, so the margin on arrival is
actually **+62 to +137 Ti** -- six to thirteen spare shots. The plan fits, but only just, and only
because the walk pays for it.

**Ammunition is the binding cost, not damage.** 280 Ti of it is needed no matter how many turrets
fire, because it scales with the Core's 500 HP rather than with our DPS. Extra Sentinels buy speed,
never reach. This is also why the Sentinel never fires at anything except the Core: a shot spent on
a conveyor is a shot the Core does not take.

### Why exactly four

A Sentinel deals 18 damage every 2 rounds -- 9 HP/round each. The enemy Core's 2x2 footprint has
eight orthogonal neighbours, and a Builder heals 4 HP for 1 Ti, so the most any opponent can mend
from a full ring of menders is **32 HP/round**.

| turrets | build cost | damage/round | rounds to kill | through a full heal ring |
|---|---|---|---|---|
| 2 | 78 | 18.0 | 27.8 | outhealed |
| 3 | 125 | 27.0 | 18.5 | outhealed |
| **4** | **178** | **36.0** | **13.9** | **kills** |
| 5 | 237 | 45.0 | 11.1 | kills, but 59 Ti the short maps do not have |

Four is the smallest ring that kills through a maximal heal ring. Three is not.

## Measured mechanics

| fact | value |
|---|---|
| Sentinel damage / ammo / reload | 18 / 10 / fires every **2** rounds |
| shot hits | **only the named tile** -- a barrier at range 3 behind the target took no damage |
| walls, barriers and units in the line | **do not block** -- `can_fire` succeeds through a barrier |
| Sentinel facing | fixed at build time; **diagonals are legal** |
| `can_fire_from` | answers for positions and targets **outside vision** |
| Core | **2x2**, reported by its north-west corner |
| store slot | u32, ceiling 4294967295; over-range raises `OverflowError`, **not** `GameError` |

## How it works

At orientation the Builder computes **every** tile from which a Sentinel could hit the Core, with
the facing that does it -- pure geometry, no API calls: `T = n + k*D` within r^2 <= 32, so k <= 5
straight and k <= 4 diagonal, across all 8 facings and all 4 Core tiles. That is 25-75 spots on a
typical map.

Then the loop is just **build on any adjacent free spot, else BFS one step toward the nearest tile
that has one**. Turrets are impassable, so each placement nudges the Builder to a different
neighbour next round -- the retreat pattern falls out instead of being scripted. Sentinels do not
block each other's fire. Being shot needs no special case: placement is attempted every round, so
a Builder under fire plants a turret where it stands.

The enemy Core is **derived at round 0**, never scouted: mirror our own Core with `W-2-x` / `H-2-y`
on whichever axes the map's symmetry flips. Verified 57/57 -- all 15 live maps plus all 42 entries
of the retired pool's table. Terrain reflects about `W-1` while the Core pair reflects about `W-2`,
because the Core is 2x2 and named by its north-west corner. The **Core publishes** the answer to
the comms store, because it is the only unit that always knows where our own Core is.

## Bugs worth remembering

1. **Sixteen searches a round.** Scoring each candidate approach with its own flood cost 13.7 ms on
   ladder hardware against a 10 ms limit, and an over-budget turn is interrupted outright. One
   sweep now answers everything by lookup: 2.2 ms worst case, measured.
2. **Replanning every round livelocks.** Unseen tiles are assumed open, so an unexplored detour
   always prices cheaper than the proven route. On longhouse the goal never changed and the Builder
   moved every single round, yet took 74 rounds to place a turret 38 steps away, touring the whole
   map. Fixed by holding the route until genuinely obstructed, charging `UNKNOWN_COST` for tiles
   never seen, and mirroring observed terrain across the map's symmetry.
3. **The turrets aimed at empty ground.** A Sentinel derived the enemy Core from *its own* position
   when our Core was out of vision -- which it always is, since the turret stands next to the
   *enemy* Core. It aimed at a mirror of itself, `can_fire` failed every round, and the ring quietly
   ground down whatever else was in range. Against `idle` this still won, because the Core was the
   only building in the pattern and the old fallback found it anyway -- the bug was invisible until
   a sparring partner with barriers turned up.
4. **A committed lane was the wrong abstraction.** Four specific tiles meant one enemy building on
   the first of them stopped the rush: on holmgang the Builder reached its stand tile on round 16
   and sat there for the remaining 984 rounds, punching the obstruction while its own action
   cooldown blocked the build it was waiting to make. Replaced by "any adjacent firing spot".
5. **Avoidance that refused to move.** Enemy-Builder tiles and their neighbours were *impassable* in
   the router, so an opponent whose Builders milled around its own base masked out the whole
   approach and the walk stalled. Every single loss to the starter bot was a 1000-round timeout with
   our Builder alive and the ring never built. Threatened tiles now cost `THREAT_COST` extra
   instead. Avoid means "prefer another way", never "refuse to move".
6. **Walkable and buildable are different questions.** A conveyor is walkable, so it was correctly
   absent from `blocked` -- but it is still a building, so `can_build_sentinel` refuses it. The
   Builder read a conveyor tile as a free firing spot, failed to build every round, and concluded
   the nearest free spot was the one it was already standing next to. Against a bot that lays belts
   across the map that is most of the approach. Now two sets: `blocked` (cannot walk) and `occupied`
   (cannot build).
7. **The repair reserve ate the kill.** Holding 40 Ti back for mending left 252 ammo -- 25 shots,
   450 damage, against 500 HP. It is now held back only once enough ammunition to finish the Core
   is already banked.

## Results

Both seats, all 15 pool maps, 30 games a cell.

| opponent | wins | kill round (min / median / max) |
|---|---|---|
| `idle` | **30/30** | 23 / 40 / 62 |
| `turtle` (walls its Core in) | **30/30** | 23 / 40 / 62 |
| `luc1` | **30/30** | 23 / 40 / 62 |
| `starter_fixed` | **26/30** | 31 / 45 / 981 |
| 10 retired maps, **not** in `terrain.py` | 18/20 | -- |

`starter_fixed` went 13 -> 23 -> 26 across the lane removal, the threat-cost change and the
conveyor fix.

## `terrain.py` -- read before submitting

`terrain.py` bundles the wall layout of the 15-map pool, so the Builder plans a true shortest path
from round 0 instead of spending thirty rounds learning that both ways round a wall look equally
good. It is worth a lot: longhouse went 87 -> 54 rounds, worst case across the pool 87 -> 67.

**This repo's own `atlas.py` calls bundled terrain "deliberately excluded from fair bots."** That is
the team's standard, not a rule the engine enforces -- the pool is a public download, and the call
to keep it was made explicitly. Set `USE_BUNDLED_TERRAIN = False` to fall back to observation; the
bot still works (18/20 above is that code path), just slower.

Note what killed `atlas.py`: it was a hardcoded table keyed on the *retired* pool, so `identify()`
returns `None` on all 15 live maps. `terrain.py` degrades to the explorer on an unknown map rather
than breaking, but it needs regenerating whenever the pool rotates:

```sh
python tools/gen_terrain.py     # regenerates bots/elias/rush/terrain.py from maps/
```

## Known limits

- **An opponent with an economy can out-heal us.** Healing is 4 HP per Ti; a Sentinel deals 1.8 HP
  per Ti, so we are 2.2x more efficient *per titanium* -- but our only income is the 2.5 Ti/round
  passive, and theirs is harvesters. Traced on skald: the ring drove the Core to **108 HP**, ran the
  ammunition dry on round 30, and the Core healed back to **492**. One or two harvesters at home
  would roughly double sustained ammunition and likely flip these games; that is outside the "one
  worker, nothing else" brief, so it is offered rather than built.
- **Our Core is naked.** Every point goes into the attack, so a faster counter-rush simply wins.
- **Small maps.** On retired `bridge` (21x8) there is no room to stand off the Core and the match
  times out. Nothing in the current pool is that short -- the smallest is holmgang at 12x12 -- but a
  pool rotation could reintroduce it.
- Beats weak and mid-tier bots decisively; the strong ones are a genuine race.
