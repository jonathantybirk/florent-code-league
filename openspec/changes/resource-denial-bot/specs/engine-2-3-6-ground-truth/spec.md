## ADDED Requirements

### Requirement: Combat arithmetic is derived from live constants

The system SHALL derive every combat and economic constant from `fcode.GameConstants` at analysis
time, never from documentation or from pre-2.3.4 notes. Documentation has been wrong 14 times on
this project.

#### Scenario: Constants are re-read after an engine bump

- **WHEN** the installed `fcode` version changes
- **THEN** the derivation tool is re-run and any conclusion whose inputs changed is marked stale
- **AND** no design decision cites a number from an earlier engine version

#### Scenario: Turret ranking is recomputed, not assumed

- **WHEN** comparing Gunner and Sentinel
- **THEN** damage/round, Ti/damage, HP, reach and blocking are computed from constants
- **AND** the comparison records that Sentinel is 9.00 dmg/round at 0.556 Ti/damage against Gunner's
  7.00 at 0.571, with 40 HP vs 25 and reach 5 vs 3

### Requirement: Pre-rebalance findings are re-verified before reuse

The system SHALL re-verify each load-bearing engine claim on 2.3.6 before any design depends on it,
and SHALL record the verdict with the probe that established it.

#### Scenario: A surviving claim is re-confirmed

- **WHEN** a 2.3.3 claim is re-probed on 2.3.6 and behaves identically
- **THEN** it is recorded as confirmed with its 2.3.6 evidence

#### Scenario: A claim that changed is corrected in place

- **WHEN** a 2.3.3 claim is re-probed and behaves differently
- **THEN** the old claim is marked superseded, the new behaviour recorded, and every design decision
  that cited it is re-opened

### Requirement: Blocking-and-piercing behaviour is established empirically

The system SHALL establish, in-engine, exactly what stops each turret's shot, because this decides
siting for every combat unit.

#### Scenario: Sentinel fires through solid obstruction

- **WHEN** a Sentinel is placed with WALL tiles between it and an enemy Core within r²≤32
- **THEN** `get_attackable_tiles` includes the wall tiles, `can_fire` on the Core returns True, and
  the Core loses HP at 18 per 2 rounds

#### Scenario: Gunner is stopped by the first obstruction

- **WHEN** a Gunner faces a target with any wall or building in the intervening tiles
- **THEN** `can_fire` on the target returns False

### Requirement: Investigation is ordered by decision impact

The system SHALL run first the probes whose outcome would most change the design, and SHALL NOT
begin building behaviour that depends on an unanswered gating question.

#### Scenario: A gating question is answered before dependent work starts

- **WHEN** a design decision depends on an unverified mechanic
- **THEN** the probe for that mechanic runs before any code implementing the decision is written
