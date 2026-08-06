## ADDED Requirements

### Requirement: Guards are general properties, never special cases

The system SHALL express every self-harm guard as a property of the resulting game state, and SHALL
NOT encode a blacklist of specific tiles, building types, or map positions.

#### Scenario: A dead end is prevented by simulation, not by memory

- **WHEN** a worker considers a build that could enclose it
- **THEN** the guard evaluates the occupancy that build would produce and refuses if the worker
  would have no legal move
- **AND** the guard does not reference the specific tile or building type that previously caused a
  failure

#### Scenario: A newly observed failure strengthens the property, not the exception list

- **WHEN** diagnostics reveal a new class of self-inflicted failure
- **THEN** the fix is a general precondition covering that class

### Requirement: A build must not enclose the builder or any friendly worker

The system SHALL verify before building that the placement leaves the builder, and any friendly
worker adjacent to it, with at least one legal move.

#### Scenario: A build that would seal the builder is refused

- **WHEN** the only remaining passable neighbour of the builder would be filled by the build
- **THEN** the build is refused and an alternative placement or action is chosen

### Requirement: A build must not sever our own delivery

The system SHALL verify before building that the placement does not break the path by which our
titanium reaches a Core tile.

#### Scenario: A barrier across our own belt is refused

- **WHEN** a placement would occupy a tile our belt uses, or would make the belt's terminal tile
  unreachable
- **THEN** the placement is refused

#### Scenario: A build on our own spawn ring is priced, not banned

- **WHEN** a placement would occupy a Core spawn tile
- **THEN** it is allowed only if passable buildings are used, or if the remaining spawn tiles exceed
  the workers we still intend to spawn

### Requirement: Actions must not be wasted

The system SHALL verify that an intended action is legal and productive before spending the round on
it, and SHALL count any round that produces no state change.

#### Scenario: A predicate that lies does not cause a wasted round

- **WHEN** a capability predicate reports an action is possible
- **THEN** the system still confirms the action's precondition independently where that predicate is
  known to be unreliable, and falls through to a productive alternative if it fails

#### Scenario: Repeated failure at the same objective is abandoned

- **WHEN** a worker fails to progress its objective for a bounded number of consecutive rounds
- **THEN** it abandons that objective and re-enters state selection, rather than retrying forever

### Requirement: Friendly fire and friendly blocking are prevented

The system SHALL confirm target ownership before firing and SHALL avoid placing friendly entities in
our own turrets' firing lines.

#### Scenario: A turret confirms the target is hostile

- **WHEN** a turret has a target available
- **THEN** it fires only after confirming the occupant is an enemy

#### Scenario: A build is refused inside our own firing line

- **WHEN** a placement would occupy a tile inside one of our own turrets' covered tiles
- **THEN** the placement is refused unless that turret's line is not load-bearing
