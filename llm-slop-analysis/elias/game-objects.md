# Every object in the game, and its exploitable surface

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

Dumped from the `fcode 2.3.3` engine, not from prose. `GameConstants` values are authoritative; behaviour
claims cite the register in `ground-truth.md`.

## Entities — the complete list

| Entity | Cost | HP | Key numbers | Scale tax |
|---|---|---|---|---|
| **Core** | — | 500 | 2×2 footprint, vision r²=36, **action r²=8**, spawn ring r²=2 (12 tiles) | — |
| **Builder Bot** | 30 | 40 | vision r²=20, attack 2 dmg / 2 Ti, heal +4 / 1 Ti, self-destruct **0 damage** | +20 pp |
| **Gunner** | 10 | 40 | r²=13, 10 dmg, 2 ammo, fires **every round**, rotate costs 10 Ti | +10 pp |
| **Sentinel** | 30 | 30 | r²=32, 18 dmg, 10 ammo, fire cooldown **3** | +20 pp |
| **Launcher** | 20 | 30 | r²=26, cooldown 1, **no ammo**, throws builders | +10 pp |
| **Conveyor** | 3 | 20 | moves one 10-Ti stack per round | +1 pp |
| **Splitter** | 6 | 20 | three outputs, least-recently-used | +1 pp |
| **Harvester** | 20 | 30 | 10 Ti / 4 rounds, round-robin to **all** adjacent buildings, **blocks movement** | +5 pp |
| **Barrier** | 3 | 30 | blocks movement **and** line of sight | +1 pp |

Terrain: `EMPTY`, `WALL`, `ORE_TITANIUM`. Resource: `TITANIUM` only. Directions: 8 + `CENTRE`.
Global: 500 starting Ti, 50-unit cap, 1000 turns, 16 store slots, stack size 10, passive 10 Ti / 4 rounds.

## The exploitable surface — asymmetries and edges

Each of these is a place where the rules are *not* symmetric, which is where exploits live.

### Confirmed odd, already used or measured

1. **Launcher pickup is team-blind** (G49). An adjacent *enemy* builder is throwable — 81 legal targets
   measured. We use this offensively as displacement. **Defensive use is untested and obvious: park a
   Launcher on our own approach and throw attackers backwards.** They walk 1 tile/round; the throw is ~5
   tiles and arcs over walls. One Launcher could rewind an entire siege repeatedly for 0 ammo.
2. **Launchers chain within one round** (G47) — two moved a builder 12 tiles in a single round.
3. **The throw arcs over walls and Core footprints** (G48). Legal targets are the whole disc r²≤26 minus
   non-passable tiles. Terrain does not protect anyone from being displaced.
4. **All turret APIs are team-blind** (G10) and a friendly in the ray jams a turret *permanently* (G11).
   A 3 Ti conveyor in an enemy Gunner's lane neutralises a 10 Ti turret indefinitely.
5. **Harvesters block movement** (G42) despite the docs. A 20 Ti building is also a wall.
6. **Ammo is global** (G52) — turrets need no supply line, only line of fire.
7. **Builders cannot damage builders** — the attack hits **buildings only**. No melee exists.

### Untested asymmetries worth probing

8. **`CORE_ACTION_RADIUS_SQ = 8`.** The Core has an action radius, and we have never used it for anything.
   What actions can it take at range 8? This constant exists for a reason.
9. **Self-destruct deals 0 damage** but removes the unit instantly. Against the **50-unit cap** that is a
   release valve; it also removes a body that is jamming our own turret's ray.
10. **Splitters are the only 3-output building** and pick least-recently-used. Deterministic round-robin is
    predictable — an opponent's splitter output can be timed.
11. **Rotating a Gunner costs 10 Ti — the same as building a new one**, but adds no cost scale. Late game,
    when scale is 200%+, rotating is half the price of a new turret.
12. **The Core's spawn ring is exactly 12 tiles.** Fill them and the opponent cannot spawn at all. They are
    a *building* target, not a unit target — barriers work.
13. **Cost scale is one global number across all types.** Every cheap building an opponent makes us build
    taxes our expensive ones. Baiting spend is a real attack.
14. **Conveyors accept from three sides and output to one.** A conveyor pointed *into* our belt injects
    into our network — the docs claim resources can be pushed onto an opposing team's network.
15. **`titanium_collected` counts only stacks landing on a Core tile.** Denying the *final* conveyor of a
    chain zeroes the entire upstream chain (G02) — the cheapest possible economic attack.
16. **Barriers block line of sight**, so they blind vision as well as stopping movement.
17. **Sentinel fire cooldown is 3 but damage is 18** — 6 dmg/round for 3.3 Ti/round versus the Gunner's
    10 dmg/round for 2 Ti/round. The Sentinel is strictly worse per titanium **except** at r²=32 versus
    r²=13. It is a range weapon, not a damage weapon, and we have never built one.
