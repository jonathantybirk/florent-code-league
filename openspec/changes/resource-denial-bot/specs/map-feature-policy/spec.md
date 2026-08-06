## ADDED Requirements

### Requirement: Policy is conditioned on map features, never on map identity

The system SHALL select its behaviour parameters from measurable properties of the live map, and
SHALL NOT branch on a map name, a map hash, or any stored table of specific maps.

This is what makes late specialisation safe. The competition rotates half its map pool weekly, so a
parameter tuned to a named map has an expected useful life of about a week; a parameter tuned to
"maps where the Cores are more than 20 walk-rounds apart" survives every rotation and still
specialises, because it fires on exactly the maps that share the property.

#### Scenario: An unseen map is handled by its features

- **WHEN** the bot plays a map it has never seen
- **THEN** it computes the feature vector from observed terrain and map dimensions and selects
  parameters from it
- **AND** its behaviour is identical to how it would treat any previously seen map with the same
  features

#### Scenario: Map identity is never consulted

- **WHEN** the policy selects parameters
- **THEN** no map name, file hash, or per-map table participates in the decision

### Requirement: The feature set is cheap, early, and map-agnostic

The system SHALL compute features that are available early enough to act on and cheap enough to fit
the per-unit CPU budget.

#### Scenario: Features are available in the opening rounds

- **WHEN** the bot must choose an opening posture
- **THEN** the features it uses are derivable from map dimensions, own Core position, the inferred
  enemy Core position, and terrain observed so far

#### Scenario: The feature set is enumerated and each is individually loggable

- **WHEN** a parameter selection is made
- **THEN** every feature value that fed it is recorded, so a wrong selection can be traced to the
  feature that caused it

### Requirement: Specialisation machinery exists before the final rotation

The system SHALL have a working feature-to-parameter fitting pipeline in place ahead of the final
map rotation, so that adapting to a frozen pool is an execution step rather than a build step.

#### Scenario: A new pool can be characterised immediately

- **WHEN** a map rotation lands
- **THEN** the feature vector for every map in the new pool is computed without code changes
- **AND** the existing parameter selector is re-fitted and evaluated against the panel

#### Scenario: Fitting is gated against overfitting even when the pool is frozen

- **WHEN** parameters are fitted to a known pool
- **THEN** the fit is validated on maps held out of the fit, or on generated maps sharing the same
  feature ranges
- **AND** a fit that does not generalise across the held-out set is rejected regardless of its score
  on the fitted maps

### Requirement: Map-derived quantities are recomputed, never cached across games

The system SHALL derive per-map quantities at runtime each game and SHALL NOT ship a precomputed
table of them.

#### Scenario: No precomputed map data ships with the bot

- **WHEN** the bot is packaged for submission
- **THEN** it contains no precomputed per-map data file, and its behaviour on the pool is produced
  entirely by runtime computation
