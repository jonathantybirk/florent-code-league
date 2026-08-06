## ADDED Requirements

### Requirement: Winning is defined as resource dominance, not Core destruction

The system SHALL treat `titanium_collected` as the primary objective and SHALL NOT trade delivered
titanium for Core damage unless the Core kill is projected to complete.

#### Scenario: A game that reaches the final round is won on the ladder

- **WHEN** neither Core is destroyed
- **THEN** the system has delivered more titanium than the opponent, or failing that holds more live
  harvesters, in that order of preference

#### Scenario: Core damage is not pursued speculatively

- **WHEN** a Core kill would require more titanium than remains, or more rounds than remain
- **THEN** the titanium is spent on denial and delivery instead

### Requirement: Mid is secured early by launcher displacement

The system SHALL move a worker toward the highest-value contested cluster faster than walking allows
by building a Launcher and throwing itself, when the hop's round saving exceeds its cost.

#### Scenario: A hop is taken only when it pays

- **WHEN** a Launcher hop is considered
- **THEN** it is taken only if the projected saving exceeds a measured minimum in rounds
- **AND** the Launcher is destroyed once spent, if it is not serving as a guard, to refund its
  cost-scale contribution

#### Scenario: Arrival is converted into a claim

- **WHEN** a worker arrives at a contested cluster ahead of the opponent
- **THEN** it establishes delivery and closes the approach, rather than waiting

### Requirement: Enemy supply is cut at the point that zeroes the most upstream value

The system SHALL prefer sabotage targets whose destruction denies the largest quantity of enemy
titanium per titanium spent, and SHALL prefer occupying the vacated tile over merely destroying.

#### Scenario: The terminal conveyor is preferred over an upstream one

- **WHEN** an enemy belt is observed
- **THEN** the target is the element whose loss zeroes the whole chain's delivery, because only
  stacks landing on a Core tile score

#### Scenario: Sabotage is abandoned when it loses the exchange

- **WHEN** the opponent repairs a cut faster than the cut costs them
- **THEN** the sabotage worker changes target or state rather than repeating the exchange

#### Scenario: A cut tile is held where holding is possible

- **WHEN** a destroyed enemy building leaves a tile we can occupy
- **THEN** the system occupies it, because `destroy` is allied-only and the opponent must then shoot
  the tile clear

### Requirement: Enemy ore is denied where denial is cheaper than contest

The system SHALL deny ore the opponent would otherwise mine when the denial is cheap and durable.

#### Scenario: An ore tile is plugged

- **WHEN** an unmined ore tile is reachable and is not one we will mine ourselves
- **THEN** a barrier is placed on it, denying the seat for a cost far below the cost of clearing it

#### Scenario: Denial does not block our own delivery

- **WHEN** a denial placement is considered
- **THEN** the system verifies it does not sever our own belt or seal our own access before building
