## ADDED Requirements

### Requirement: A worker occupies exactly one state per round

The system SHALL assign each worker exactly one state per round from a closed set, and SHALL
implement one behaviour per state.

#### Scenario: State set is closed and total

- **WHEN** a worker acts
- **THEN** its state is one of `IDLE`, `SECURE_MID`, `SABOTAGE`, `BUILD_INFRA`, `MAINTAIN`,
  `DEFEND`, `EVADE`, `JAIL`
- **AND** every state has a defined behaviour that either spends the round or explicitly yields

#### Scenario: IDLE is an error signal, not a resting state

- **WHEN** a worker ends a round in `IDLE`
- **THEN** the round is counted as wasted and reported by diagnostics

### Requirement: State selection is a separate, inspectable arbiter

The system SHALL select state through a single arbiter that reads observable features and returns a
state plus the reason, so the decision can be logged, overlaid and second-guessed independently of
the behaviours.

#### Scenario: Every state change is attributable

- **WHEN** a worker's state changes
- **THEN** the arbiter records the previous state, the new state, the round, and the deciding feature

#### Scenario: The arbiter is replaceable without touching behaviours

- **WHEN** the selection rule changes
- **THEN** only the arbiter changes, and the per-state behaviours are untouched

### Requirement: State selection is stable against oscillation

The system SHALL prevent a worker from alternating between states on consecutive rounds when the
underlying situation has not materially changed.

#### Scenario: Hysteresis prevents flapping

- **WHEN** the feature driving a state sits near its threshold
- **THEN** the worker retains its current state until the feature crosses a wider band, or a
  minimum dwell has elapsed

#### Scenario: Oscillation is detected and reported

- **WHEN** a worker changes state more than a configured number of times within a window
- **THEN** diagnostics report it as oscillation with the worker id, rounds, and states involved

### Requirement: Thresholded selection precedes any learned selection

The system SHALL implement and measure a thresholded arbiter first, and SHALL only consider a
learned selector once the thresholded one demonstrates the state set is sufficient.

#### Scenario: A learned selector is gated on the thresholded baseline

- **WHEN** a learned state selector is proposed
- **THEN** it is measured against the thresholded arbiter on the same games
- **AND** it ships only if it wins by more than the evaluation's discrimination floor

#### Scenario: Missing states are discovered from failures, not guessed

- **WHEN** diagnostics show workers repeatedly choosing a state that then wastes rounds
- **THEN** the failure is examined for a missing state or a missing feature before the thresholds
  are retuned
