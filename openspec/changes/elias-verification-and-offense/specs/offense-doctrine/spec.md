## ADDED Requirements

### Requirement: Forward-gunner thesis stated with kill criteria

The offensive doctrine — "a forward Gunner fed by one adjacent Harvester kills an undefended Core by ~turn 80
for under ~100 Ti, and this is the dominant strategy on short maps" — SHALL be held as a falsifiable thesis
with explicit kill criteria, not as an adopted strategy.

#### Scenario: Thesis falsified by ore geometry
- **WHEN** the map-atlas audit computes, for each of the 15 maps, whether a Gunner firing position on the
  enemy Core exists with an ore tile orthogonally adjacent
- **THEN** if the count is materially below the asserted 13/15, the "zero-conveyor" variant is demoted to
  the affected maps only and a conveyor-fed variant is costed separately

#### Scenario: Thesis falsified by competent defence
- **WHEN** the rush probe is run against a defender that (a) heals the Core at 4 HP/1 Ti, (b) fields one fed
  home Gunner covering the approach, and (c) targets the attacking Harvester (30 HP)
- **THEN** if the attack fails against all three, the doctrine is reclassified from "default plan" to
  "punisher of passive opponents" and the per-map decision procedure is updated

#### Scenario: Thesis survives
- **WHEN** the rush succeeds against the defender battery on the short-map class
- **THEN** the doctrine is adopted for maps where the walk to the nearest firing position is at most a
  threshold (initially ~15 rounds), with economy-first retained elsewhere

### Requirement: Attack the attacker's weak points before opponents do

The doctrine SHALL enumerate its own failure modes and cost each counter, so we know what beats us before
the ladder teaches us.

#### Scenario: Forward harvester sniped
- **WHEN** the defender kills the attacking Harvester (30 HP — 3 gunner shots)
- **THEN** the attack's ammo supply dies with it; the probe suite SHALL measure whether the attacker can
  rebuild (harvester cost at current scale, builder exposure while building) faster than the defender can
  keep killing it

#### Scenario: Approach lane pre-jammed
- **WHEN** the defender places a building in the forward Gunner's only firing lane (friendly-block mechanics
  permitting)
- **THEN** the probe suite SHALL determine whether lane-blocking is legal for the defender and what it costs,
  since it may be the cheapest counter to our own doctrine

### Requirement: Per-map offence/economy decision procedure

Strategy selection SHALL be a precomputed per-map decision, made at round 0 from the atlas, between at
minimum: RUSH (forward gunner), ECON (max connected harvesters), and HYBRID (econ with a timing switch).

#### Scenario: Short-map class
- **WHEN** the fingerprinted map's distance from spawn to the nearest enemy-Core firing position is small
  (e.g. sprint/duel/twins/crossfire/pinch class)
- **THEN** the opening is the doctrine's rush build, and the economic build runs with whatever builder
  actions remain

#### Scenario: Long-map class
- **WHEN** the walk exceeds the threshold (e.g. vault/hive/quarry/aurora class)
- **THEN** the opening is ECON, the tiebreak is treated as the primary win condition, and any rush is a
  mid-game decision gated on observed enemy passivity

### Requirement: Offence exploits verified fire-discipline mechanics

Firing policy SHALL follow verified magazine mechanics, not RTS intuition.

#### Scenario: Magazine-dump policy
- **WHEN** the ammo-refill claim ("a turret only receives new ammo at exactly 0") is `VERIFIED-LINUX`
- **THEN** turret policy dumps the magazine rather than conserving shots, since a partially-full magazine
  blocks resupply

#### Scenario: No firing at empty air
- **WHEN** a Sentinel has no confirmed target in its arc (there is no `get_sentinel_target()`; it will
  happily burn 10 Ti per shot at empty tiles)
- **THEN** the Sentinel holds fire unless a remembered or store-shared enemy position falls inside its
  precomputed attack arc
