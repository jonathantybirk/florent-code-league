## ADDED Requirements

### Requirement: Turret coverage is computed, not guessed

The system SHALL compute the set of tiles each visible enemy turret can fire on, using the turret's
type, position and facing, all of which are readable for enemy entities.

#### Scenario: Coverage is derived from the turret's own facing

- **WHEN** an enemy Gunner or Sentinel is visible
- **THEN** its covered tiles are computed from its facing and reach
- **AND** a Sentinel's coverage ignores intervening obstructions while a Gunner's stops at the first
  blocking tile

#### Scenario: Coverage expires when the turret is no longer confirmed

- **WHEN** a remembered turret's tile is observed to be empty
- **THEN** its coverage is cleared, so stale memory does not permanently forbid good ground

### Requirement: Workers avoid standing in covered tiles

The system SHALL treat covered tiles as costly rather than merely forbidden, so that a worker
crosses one only when the alternative is worse.

#### Scenario: A route prefers uncovered ground

- **WHEN** two routes reach the same goal
- **THEN** the route spending fewer rounds inside turret coverage is preferred, even if slightly
  longer

#### Scenario: A worker under fire withdraws rather than continues

- **WHEN** a worker is losing HP and is standing in computed coverage
- **THEN** it enters `EVADE` and moves out of coverage, rather than continuing its previous task

#### Scenario: Evasion does not deadlock

- **WHEN** every adjacent tile is covered
- **THEN** the worker takes the action that minimises expected damage and still makes progress,
  rather than standing still

### Requirement: Danger is sensed before it is suffered

The system SHALL treat the appearance of an enemy turret or worker near a task site as a signal to
re-evaluate state, rather than waiting for damage.

#### Scenario: An approaching threat triggers re-evaluation

- **WHEN** an enemy entity enters vision within a configured distance of the worker's objective
- **THEN** the arbiter re-evaluates that worker's state on the same round

#### Scenario: A turret being built nearby is answered before it fires

- **WHEN** an enemy turret appears within reach of our position or our infrastructure
- **THEN** the worker either leaves its coverage or acts against it, and does not remain idle inside
  it
