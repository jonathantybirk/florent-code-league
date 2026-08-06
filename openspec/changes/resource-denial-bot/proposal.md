## Why

The engine rebalanced under us. `fcode` went 2.3.3 → 2.3.6 mid-competition and inverted the combat
maths: the Gunner lost 60% of its HP, 30% of its damage, doubled in price and doubled its cost-scale
tax, while the Sentinel gained HP, lost a reload round, and now out-damages it. Every number the
current bot was tuned against was measured on an engine that no longer exists, and a 64-candidate
Sequential-Halving campaign has already returned **+0** on the constants that remain — the
hand-tuned policy has no headroom left at that granularity.

At the same time the shipped bot loses **2–40** to a teammate's `heimdall`, not because it is weaker
overall (both score ~36/42 against `vanguard`) but because its entire win condition is one geometric
event — a turret on the enemy Core ring — and one 10 Ti guard turret denies it. It has no second way
to win, and with `ATTACKERS = 3` it has no economy to fall back on.

Rather than patch a 2800-line policy whose 22-of-36 live constants are already provably optimal for
a dead engine, this change rebuilds from the arithmetic of 2.3.6, targeting a **different win
condition**: deny the opponent titanium and workers rather than race to their Core.

## What Changes

- **BREAKING**: a new bot built from first principles, not derived from `bot/main.py`. The existing
  bot stays untouched as the control to beat.
- **Win by resource denial, not Core destruction.** The tiebreak ladder is
  `titanium_collected → live harvesters → titanium_stored → coinflip`, and passive income scores
  **zero** on the first rung. A bot that holds the ore and cuts the opponent's belts wins on the
  ladder's own terms without ever reaching their Core.
- **Sentinel-primary combat.** Measured from constants: Sentinel 9 dmg/round at 0.556 Ti/damage vs
  Gunner 7 at 0.571; 40 HP vs 25; reach 5 vs 3; unblockable vs blocked by the first building. A
  Sentinel kills a Gunner in 2 shots and cannot be reached back.
- **Launcher-rushed mid control.** One builder throws itself toward the map's largest ore cluster,
  claims it with a harvester + belt, and walls the approach with barriers.
- **A sabotage worker** that reaches the enemy half and destroys supply infrastructure — conveyors
  first, since denying the terminal conveyor zeroes an entire upstream chain.
- **Worker states ("emotions")** — `IDLE`, `SECURE_MID`, `SABOTAGE`, `BUILD_INFRA`, `MAINTAIN`,
  `DEFEND`, `EVADE`, `JAIL` — one behaviour per state, with a single arbiter choosing the state from
  observable features. Thresholded first; a learned selector only if the thresholds prove the state
  set is right.
- **Danger sensing and evasion.** Enemy turret facings are readable (`get_direction` works on enemy
  turrets), so a worker can compute the tiles a turret bears on and refuse to stand in them.
- **General guards, not special cases.** Every action is checked for self-harm before it is taken —
  in particular a build must not enclose the builder or seal our own belt, which is a property test
  on the resulting occupancy, not a blacklist of tiles or building types.
- **A diagnostics suite** built on `ct.draw_indicator_line` / `ct.draw_indicator_dot`, which render
  into replays, plus offline replay analysis that flags idling, wasted actions, oscillation,
  dead-end routes and wrong-state selection with counts per game.
- **Policy conditioned on map features, never on map identity.** The organisers have announced that
  **half the map pool rotates weekly**, three rotations in total, the last on the 21st — four days
  before finalists are picked. A parameter tuned to a named map therefore has an expected useful
  life of about one week. A parameter tuned to a *property* — "Cores more than 20 walk-rounds
  apart", "one dominant ore cluster", "few chokepoints" — survives every rotation and still
  specialises, because it fires on exactly the maps that share the property.

## Capabilities

### New Capabilities

- `engine-2-3-6-ground-truth`: re-establish which measured engine facts survived the rebalance, and
  what the new constants imply. Gate on this before design decisions depend on it.
- `map-resource-model`: identify ore clusters, their value, contest status, and the choke geometry
  that guards them, from observed terrain alone.
- `worker-states`: the state set, the arbiter that selects one per worker per round, and the
  per-state behaviour contracts.
- `resource-denial`: claiming, holding and stealing titanium; cutting enemy supply; the belt/barrier
  economics that decide whether a claim is worth making.
- `threat-evasion`: sensing turret coverage and enemy workers, and routing/acting to avoid them.
- `safe-action-guards`: general pre-action checks that prevent self-inflicted harm (enclosure, belt
  sealing, spawn-ring blocking, friendly-fire, action waste).
- `diagnostics`: indicator overlays plus offline replay analysis that surface suboptimal behaviour
  numerically.
- `map-feature-policy`: selecting behaviour parameters from measurable map properties rather than
  map identity, and the fitting pipeline that lets a frozen final pool be specialised to in days
  rather than built for.

### Modified Capabilities

None. The existing `bot/` is left as-is and serves as the control.

## Impact

- **New**: `bots/cand/rdb/` (working bot), `tools/diag/` (replay analysis), `tools/arena.py`
  (evaluation against the Nash panel), `maps/lab/` arenas for new probes, `bots/probes/` additions.
- **Untouched**: `bot/`, `bots/elias/`, `bots/rivals/`, `bots/nash/`.
- **Engine**: pinned to `fcode 2.3.6`. All pre-2.3.4 measurements in
  `llm-slop-analysis/elias/` are stale for combat and cost-scale numbers and must be re-verified
  before being cited.
- **Evaluation panel**: `bots/nash/{steward, vigil, heimdall, odin, prospect_rushonly}` — the five
  entries with non-zero Nash probability in the team's latest tournament run — treated strictly as
  **black boxes**. No reading their source to counter them.
