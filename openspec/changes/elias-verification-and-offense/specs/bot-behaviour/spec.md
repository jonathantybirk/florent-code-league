## ADDED Requirements

### Requirement: Survive the forward-gunner kill

The bot SHALL not lose its Core to the cheapest known attack. Measured baseline: AutistimusPrime loses its
Core in 21/30 games against `luc1` and 25/30 against `lockin`, collecting zero titanium in half of those —
it dies before its first chain completes.

#### Scenario: Enemy firing positions are denied before they are occupied
- **WHEN** the map is identified at round 0 and the per-map table lists the tiles from which a Gunner can
  bear on our Core footprint
- **THEN** the bot treats those tiles as denial targets, blocking the highest-value ones with Barriers
  (3 Ti, 30 HP, blocks movement and line of sight) before the enemy can occupy them, and never places a
  friendly building where it would jam our own turret ray

#### Scenario: Ore adjacent to our own Core approach is contested
- **WHEN** an ore tile lies orthogonally adjacent to a firing position bearing on our Core
- **THEN** that ore is prioritised for our own harvester, since taking it both grows our economy and denies
  the enemy the zero-conveyor ammo supply their rush depends on

#### Scenario: Core under fire
- **WHEN** our Core is losing HP
- **THEN** the bot locates the source, and responds by killing the attacking Harvester (30 HP — the single
  point of failure of the whole attack) rather than by healing the Core, since healing loses the exchange
  (0.25 Ti/HP against a Gunner's 0.20 Ti/damage at 10 damage per round)

### Requirement: Parallel chain construction

Economy throughput SHALL not be limited by serial per-builder chain construction. Measured baseline: losses
to the shipped starter were by a deficit of ~2470 titanium — the yield of **exactly one** connected harvester
— repeatedly.

#### Scenario: Builder finishes a chain
- **WHEN** a builder completes a chain and the map still has unclaimed reachable ore
- **THEN** it begins the next chain without an idle return trip, and the builder count adapts to the number
  of reachable unclaimed ore tiles rather than a fixed constant

#### Scenario: Chain is broken by sabotage
- **WHEN** a belt tile on a completed chain is destroyed (enemy range-0 sabotage costs them 2 Ti per 2
  damage against a 20 HP conveyor)
- **THEN** the break is detected and repaired, because a chain missing one link delivers exactly zero (G02)

### Requirement: Never regress on the crash and validator gates

Every candidate SHALL pass the safety gates before any strategic comparison is considered meaningful.

#### Scenario: Pre-submission gate
- **WHEN** a candidate build is prepared
- **THEN** `tools/check_bot.py` passes (no `finally:`, no bare `except:`, no non-allowlisted exception names,
  no BOM, no stray `__pycache__`, `main.py` entry point with a top-level `class Player`), and the exhaustive
  mirrored sweep records zero own-unit deletions

#### Scenario: Opponents in the zoo are deterministic
- **WHEN** a bot is admitted to the evaluation zoo
- **THEN** it seeds its randomness per unit, because the shipped starter's unseeded `random` made three
  identical runs of identical code score 20-10, 18-12 and 16-14 — a measurement band wide enough to hide
  every increment we care about
