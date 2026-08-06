## ADDED Requirements

### Requirement: Intent is drawn into the replay

The system SHALL draw each worker's current state and current objective into the replay using
`ct.draw_indicator_line` and `ct.draw_indicator_dot`, so behaviour can be judged by watching rather
than by reading logs.

#### Scenario: A worker's state is visible in the visualiser

- **WHEN** a worker acts
- **THEN** it draws a dot at its own position in the colour assigned to its state
- **AND** draws a line to its current objective tile when it has one

#### Scenario: Overlays are cheap enough to leave on

- **WHEN** overlays are enabled
- **THEN** the per-unit round cost stays within the CPU budget with margin, and overlays can be
  switched off by a single flag

### Requirement: Suboptimal behaviour is detected offline and counted

The system SHALL analyse a finished replay and report per-game counts of behaviours that are hard to
notice by eye, each attributed to a worker and a round range.

#### Scenario: Idling is reported

- **WHEN** a worker takes no productive action in a round
- **THEN** the analyser counts an idle round for that worker and reports the total per game

#### Scenario: Oscillation is reported

- **WHEN** a worker alternates between two positions or two states across a window
- **THEN** the analyser reports the worker, the window and the values it alternated between

#### Scenario: Route inefficiency is reported

- **WHEN** a worker reaches an objective in materially more rounds than the shortest known path
- **THEN** the analyser reports the excess rounds and the two endpoints

#### Scenario: Wasted actions are reported

- **WHEN** an attempted action does not change game state
- **THEN** the analyser counts it and attributes it to the worker and the action type

#### Scenario: State misuse is reported

- **WHEN** a worker spends rounds in a state whose behaviour produced no progress
- **THEN** the analyser reports the state, the worker and the round count

### Requirement: Every change is reviewed against the Nash panel in the visualiser

The system SHALL, after each accepted improvement, produce replays against the five highest
Nash-probability team bots, so behaviour can be inspected before the next change is designed.

#### Scenario: A change produces watchable evidence

- **WHEN** an improvement is accepted on the numbers
- **THEN** replays against each panel bot are generated and the command to open them is reported
- **AND** the diagnostics summary for those games is reported alongside the win counts

### Requirement: Findings are recorded with numbers

The system SHALL record every finding with the measurement that established it, and SHALL update the
change's artifacts as findings land.

#### Scenario: A claim without a number is not recorded as a finding

- **WHEN** an observation is proposed as a finding
- **THEN** it is recorded only with the measured quantity, the sample size and the probe or sweep
  that produced it

#### Scenario: A refuted expectation is recorded as prominently as a confirmed one

- **WHEN** an expected improvement measures neutral or negative
- **THEN** the result is recorded with its numbers and the idea is marked refuted
