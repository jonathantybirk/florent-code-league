# Pantheon / "Khaos" — Cambridge Battlecode winner postmortem

*Read 2026-08-05, against fcode 2.3.4. Source: [Pantheon_postmortem.pdf](https://game.battlecode.cam/postmortems/Pantheon_postmortem.pdf),
by Derek Wang, Yufan Wang, Alex Thummalapalli, Ioannis Pantidis.*

This is the artifact that [../legacy/published-team-accounts.md](../legacy/published-team-accounts.md)
and [../legacy/sources.md](../legacy/sources.md) both recorded as **"no public Pantheon
technical paper or full postmortem was located."** It exists, and it is the first-place
account of the game our engine is derived from. Those two "not located" notes are now stale.

It is also *not* a foreign competition. Cambridge Battlecode is the same game family as
Florent: Core, Builder Bots, Conveyors, Splitters, Harvesters, Gunners, Sentinels,
Launchers, Barriers, symmetric maps, Core-destruction or tiebreak win. So it transfers far
better than the MIT/Java material we had catalogued — but **not wholly**, because Florent
is a simplified and partly re-specified variant. The divergence table below is the load-bearing
part of this document; taking their conclusions without it will produce wrong bots.

## Engine divergence: Cambridge (their game) vs Florent 2.3.4 (ours)

| Area | Cambridge / Khaos | Florent 2.3.4 | Consequence for us |
|---|---|---|---|
| Resources | Titanium + raw/refined axionite; Foundries convert | **Titanium only**; no Foundry | Their axionite conversion policy, foundry targeting, and the axionite-first tiebreak are all dead code for us |
| Turret ammo | Physically fed by conveyor from a non-facing side; unfed turret is useless | **Global ammo pool**, `convert_ammo()` at the Core, 1:1 from titanium; turrets "hold no ammo, never need feeding" | **Biggest single divergence.** Their whole feed-propagation bitmask, turret-feed chains, self-destruct-if-unfed logic, and "sentinels consume more ammo than a harvester provides" placement rule are all irrelevant here. Turret *placement* is radically freer in our game |
| Turret cost | Per-type titanium cost | Same, **plus +20% cost-scale per turret built** | Our tax is economic, not logistical. Matches Lucas's measured result that every +20% turret is a tax on the win |
| Comms | Sandboxed; markers only, one u32/turn, XOR-obfuscated; bots place markers to share symmetry + 21-bit terrain samples | **Global Communication Store**: 16 shared int slots, free read/write | Their entire marker subsystem — bit-packing, 5×5 bucket broadcasts, marker disruption by enemy road spam — is obsolete. We get strictly better comms for free |
| Movement | Adjacent tile incl. **diagonals**; Chebyshev geometry throughout | **Cardinal only** (N/E/S/W); `move(diagonal)` raises | Every Chebyshev flood, `expand_chebyshev`, diagonal-preference and zigzag-for-vision heuristic must be re-derived on a 4-neighbour/Manhattan graph |
| Builder actions | Adjacent incl. diagonal; **can attack the building on its own tile** | **Orthogonal only**; **cannot act on its own tile** | Their "walk onto the enemy conveyor and shoot it" line does not work as written; we must stand cardinally beside the target |
| Move/act coupling | Independent | A successful move **or** action blocks the other for the round | Build-then-walk-on costs two rounds here. Their placement tempo assumptions are optimistic for us |
| Roads | Required — bots cannot walk on empty tiles without one. Road spam is a real map-control tool | **No roads**; movement over any open tile is free | Their road-spam map-control state, and "enemy roads blocked the extension", have no analogue. Removes a whole denial mechanic |
| Other buildings | Bridges, Breaches, armoured conveyors | None of these exist | Bridge-cost routing (cost 6 edge) and Breach handling drop out |
| Map size | 20×20 to 50×50 | **8×8 to 30×30** | Bitmask big-ints are *cheaper* for us (≤900 bits vs 2500). Chokepoint geometry is a smaller problem |
| Round limit | 2000 | **1000** | Half the game. Their round-750 axionite gate and round-1500 conversion cutoff scale to nothing here; late-game plans must be roughly halved |
| Tiebreak | Axionite collected → titanium → harvesters → … | Titanium collected → harvesters → titanium stored → coin flip | Harvester count is our #2 tiebreak; theirs was #3 |
| Unit cap | not discussed | **50 living units incl. Core and turrets** | Turrets compete with Builders for the cap — an extra reason mass turrets are bad |
| CPU budget | 2000 µs per unit-turn | **10 ms per unit-turn** (+5% banked buffer) | We have ~5× their budget. Their incremental chokepoint job is comfortably affordable here |
| Turn order | entities act in increasing id order | units act **in spawn order** | Their sentinel one-shot coordination trick transfers — see below |

## What transfers, ranked by how much I would bet on it

### 1. Memoryless architecture with scored states (their headline claim)

They rewrote to a bot that **recomputes everything every turn** and keeps no state machine.
Each Builder scores seven states and runs the highest scorer. They attribute their win to it:
"we believe our memoryless approach was one of the main factors in our bot being very dynamic
and adaptable. It also allowed for a lot of complex behavior to emerge without hardcoding
strategies, which made our bot **less prone to overfitting**."

Their state ceilings, scored in descending ceiling order with early break:

| State | Ceiling | Role |
|---|---|---|
| attack | 9 | build sentinel / gunner |
| heal | 8 | repair / chase invaders |
| route | 7.75 | route resources back |
| secure | 7.5 | surround an ore tile |
| harvest | 4 | build a harvester |
| disrupt | 2 | barrier enemy-side ore |
| explore | 1 | explore unseen tiles |

The ceiling trick is nice and free: sort states by max possible score, and stop evaluating once
`best_score >= state.MAX_SCORE`. Note `route` can exceed `heal` (7.75 > 7) only when the claim
is "important" — enemy bots within 5 of it, or it is feeding an enemy turret.

This is the single most portable idea in the document, and it is the opposite of how our
Casemate/Vanguard line is built.

### 2. Launcher play — probably our largest untapped edge

Launchers exist in our engine, unchanged in spirit, and their launcher logic is the most
inventive part of the postmortem.

- **Chokepoint launcher**: throw the enemy Builder back to *a tile it recently occupied*, from
  tracked per-bot position history, forcing it to retrace its path. "Throwing the builder
  backward turns one launcher action into several turns of lost walking time."
- **Region-minimizing throw** otherwise: for every legal destination, flood the region the bot
  could navigate from there using enemy-POV passability with unseen tiles treated as impassable;
  throw to the destination minimising reachable region size, tiebreak on greatest wall-BFS
  distance from your conveyors.
- A launcher's 3×3 is treated as **impassable for enemy pathing** in their own BFS, since an
  enemy entering it gets flung. Launcher + barrier can form a wall that only their bots pass.
- Launchers are classified **once, on placement** (chokepoint / offensive / defensive).

Our x/jon line has been treating ferries as a movement aid and mostly measuring them as harmful
(`Drop harmful Casemate ferry`, `Keep ferries off sentinel-specialist maps`). Pantheon's use is
almost entirely **denial of enemy movement**, not friendly transport. That is a different
hypothesis than the one we rejected.

### 3. Ore securing with guard conveyors

Before placing a Harvester, place inward-facing conveyors on the ore tile's cardinal neighbours.
They carry nothing (an inward-facing conveyor is not a valid output of the ore tile) but they
**deny the enemy the adjacent tiles a turret would need**, and they have far more HP than a road.
They keep a `guard_conveyor` mask so the routing graph ignores them.

Directly implementable for us; cardinal-only build actually suits it.

### 4. Turret target priority ladder

Their shared gunner/sentinel target priority, in order:

1. Enemy foundries feeding an enemy turret and none of mine *(N/A here)*
2. Enemy harvesters feeding >1 enemy turret and none of mine *(feeding is N/A; the "enemy harvester" target still stands)*
3. Enemy turrets that can hit one of my turrets, plus their feed chain
4. As (3), any enemy turret
5. Enemy builder bots
6. Enemy infrastructure cardinally adjacent to any harvester on either team
7. Any enemy entity

Tiebreaks: highest-HP entity we can **one-shot** → entity furthest from enemy builders (so it
takes longer to walk over and heal) → highest weight → lowest HP. And: never shoot a building an
ally builder is standing on, since the builder eats the hit.

The "furthest from enemy builders" tiebreak is a heal-race insight we do not model at all.

### 5. Sentinel one-shot coordination — transfers via spawn order

Sentinels **hold fire** if they see an ally sentinel just shot a target both can see, then fire
on the same turn the health drops again, killing it before enemy builders can heal. Only the
**higher-id** sentinel does this, because entities act in increasing id order, so the higher-id
one can react within the same turn and the lower-id one cannot.

Our engine acts in **spawn order**, which gives the identical guarantee: a later-built turret can
react to an earlier-built one within the same round. This is implementable today.

### 6. Adversarial territory patterns

- **Ore hopping**: use your own harvesters as staging points for attack turrets on the frontier;
  shoot the defences around the enemy's nearby harvesters, then take the harvester. Consistent
  frontier advance that also grows economy. Depends on ore being spread out.
- **Seeding**: attack an enemy conveyor until the gap fits a "seed" turret, which then clears
  space around itself for more of your infrastructure. Countered by an enemy builder simply
  out-healing you — so they only do it when they locally outnumber (2 allies within sq-dist 25
  vs 1 enemy), or an allied sentinel is in sight, or the target's 3×3 is sealed.
- **Attack routing** (added the day before the final deadline, and credited with a large win-rate
  jump): extend the conveyor network *toward* the enemy instead of back to your Core, triggered
  when your BFS distance to the enemy Core ≤ 1.5× your distance to your own. "Aggressive attack
  routing was usually a net win. Even when the route never reached the enemy core, the damage it
  caused to enemy infrastructure and area control was usually enough to justify the loss."
  If the route can be extended into a **gunner**, do that instead of a sentinel.

Note ore hopping and seeding both get *easier* for us: no feed chain is required to make a
frontier turret work, only global ammo. Our constraint is the +20% cost scale instead.

### 7. Coordination without a state machine — Voronoi claim partition

To stop independent builders contesting the same task: run competing simultaneous flood-fills
from *this* bot versus *all other friendly bots*, and keep only the candidate tiles this bot
reaches first. That is the whole anti-collision mechanism — no claims, no negotiation, no markers.
With our 16-slot global store we could do it more directly, but the floodfill needs no comms at all.

### 8. Small things worth stealing outright

- **Stuck detection**: if `2 + (id mod 8)` turns pass without progress, step randomly. The
  `id mod 8` term deliberately desynchronises the unstick across bots.
- **Initial spawn plan**: first four Builders spawned toward directions chosen to maximise the
  product of pairwise angular separations, restricted to rays that are either out of vision or
  contain titanium; spawn nearest-to-centre first because the centre is contested.
- **Spawn policy**: if no ally is near a visible enemy, spawn toward it (defensive reflex);
  otherwise gate on titanium `> baseline + scaling` where baseline is 400 if allies ≥ 12 else 200.
- **TTL caches**: remember target tiles that recently failed and skip them for 100 rounds.
- **Explore by frontier ring sampling**: floodfill from self *and known friendly bot positions*,
  keep a 6-deep ring buffer, sample a random tile from the ring ~5 steps back. Seeding from
  teammates biases each bot away from where others already are.
- **Heal priority tiers**: Core → turrets → armoured conveyors/harvesters/foundries → conveyors →
  barriers/bridges/splitters → roads, considering all *very* damaged buildings before less damaged ones.
- **Gunner rotation gate**: require ≥60 global titanium before rotating, so a gunner cannot burn
  the economy by oscillating.

## Techniques that need translation work

**Bitmask map representation.** Tile `(x,y)` is bit `n = x + y*W` of a Python big int; ~30 derived
masks (entity type, facing, visibility, resource flow, danger, placement legality) composed with
C-level bitwise ops. Geometric translation by `<<1`, `>>1`, `<<W`, `>>W`. Non-boolean values live
in plain lists indexed by `n`. Everything memoized on a `_struct_version` counter bumped on any
structural change. This is straightforwardly better than array iteration and our maps are smaller
than theirs — but every Chebyshev expansion becomes a 4-neighbour expansion for us.

**Bit-sliced score planes.** For each facing and turret type, keep 9 bitmask "planes" where bit `i`
of tile `n`'s score is `(planes[i] >> n) & 1`. Adding a constant to every tile in a mask is
`O(#planes)` whole-board AND/XOR ops **regardless of how many tiles are in the mask**, with carries
rippled upward; thresholding the whole board against a scalar is one MSB-first pass. They state
this is "what makes exhaustive placement evaluation fit within our per-turn budget." Genuinely
clever, and with our 10 ms budget we may not need it — but it is the right tool if turret placement
scoring ever becomes our bottleneck.

**Bitmasked Dial's algorithm** for pathing: a circular array of frontier bitmasks as a bucket queue,
run **in reverse from the target**, so no path reconstruction is needed — just step to the lowest
distance-to-target neighbour. Movement edge costs: normal 1, destroy ally barrier 15, step into soft
threat 20, both 35. Routing edge costs: conveyor 1, bridge 6, plus **+4 on loaded conveyor tiles** to
bias toward building new lines rather than overloading existing ones. Threat masks are split into
**soft** (sentinel coverage — enter at higher cost) and **hard** (gunner/breach — never enter).

**Max-flow approximation by jam detection.** If four loaded conveyors are seen in a row, the line is
considered "unroutable" and excluded from route planning, so new harvesters do not get attached to a
saturated trunk. This is a cheap proxy for capacity that we should care about — our own
`opening-economy-revision.md` already found conveyor-trunk capacity to be the dominant constraint,
which is independent confirmation from the winning team.

## Techniques that do not transfer

- The entire marker/comms subsystem (we have a global store).
- Turret feed propagation, feed-chain protection, unfed-turret self-destruct (global ammo).
- Axionite conversion policy and foundry logic (no axionite).
- Road spam as map control (no roads).
- Their **chokepoint detection stack** is the largest single section of the paper — a vendored
  and rewritten Foronoi sweep-line Voronoi over rasterised free-space boundary samples, a
  BWTA-style medial axis, radius-monotonic leaf pruning, region nodes at junctions and local
  radius maxima, union-find merging of chokes that are too wide relative to their regions, and an
  incremental resumable job that spends a slice of each turn. They admit "this is why our builder
  bots time out every turn." On 8×8–30×30 maps with 10 ms budgets and no roads, this is almost
  certainly over-engineered for Florent — a plain articulation-point / min-cut search on the
  passability graph would get most of the value. **The idea** (find tiles where one barrier or
  launcher changes connectivity, and block them) transfers; the machinery should not be copied.

Worth flagging: the postmortem says the final bot and tooling "can be found in our GitHub
repository" but gives no URL, and a search did not locate a public Pantheon/Khaos repo. Treat the
code as unavailable unless someone finds it.
