## ADDED Requirements

### Requirement: Ore is grouped into clusters and valued

The system SHALL group observed ore tiles into connected clusters and SHALL value each cluster by
the titanium it can deliver, not by tile count alone.

#### Scenario: Cluster value accounts for delivery

- **WHEN** a cluster is evaluated
- **THEN** its value reflects the number of harvester seats, the belt length required to reach a
  Core tile, and the round at which the first stack would land
- **AND** a cluster with no viable delivery path is valued at zero, because only stacks landing on a
  Core tile count toward `titanium_collected`

#### Scenario: Clusters are re-valued as terrain is observed

- **WHEN** new terrain is observed that shortens or lengthens a delivery path
- **THEN** the affected cluster's value is recomputed

### Requirement: Clusters are classified by contest status

The system SHALL classify each cluster as OURS, THEIRS, or CONTESTED using walk distance from each
Core, and SHALL treat the classification as a decision input rather than a label.

#### Scenario: A near cluster is claimed, not contested

- **WHEN** our walk distance to a cluster is materially shorter than the opponent's
- **THEN** the cluster is OURS and is claimed by building, not by denial

#### Scenario: A cluster we cannot reach first is denied, not claimed

- **WHEN** the opponent reaches a cluster materially sooner than we can
- **THEN** the cluster is THEIRS and is a denial target, because a harvester we build there will be
  taken or cut

### Requirement: Belt viability is decided by arithmetic before it is built

The system SHALL decide whether a harvester-plus-belt claim pays before committing titanium, using
the measured income rate, the build cost at current cost scale, and the number of rounds expected to
remain.

#### Scenario: A belt that cannot repay itself is not built

- **WHEN** the projected delivered titanium over the remaining rounds is less than the build cost
  plus the cost-scale tax on future purchases
- **THEN** the claim is refused and the titanium is spent elsewhere

#### Scenario: A single long belt from a large cluster is evaluated on its own terms

- **WHEN** the largest cluster is far from our Core
- **THEN** the system evaluates a single conveyor run from that cluster, including the barrier cost
  of protecting its flanks, and records delivered Ti/round against total cost

### Requirement: Choke geometry around a cluster is identified

The system SHALL identify the tiles that control access to a cluster, so that holding a cluster
costs the fewest possible buildings.

#### Scenario: A cluster with a narrow approach is walled cheaply

- **WHEN** a cluster's approach passes through few tiles
- **THEN** those tiles are identified as the barrier sites that deny access
- **AND** the system verifies the wall does not also seal our own access or our own belt
