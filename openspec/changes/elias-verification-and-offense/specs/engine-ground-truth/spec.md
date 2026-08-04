> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

## ADDED Requirements

### Requirement: Claim register with per-platform verification status

The project SHALL maintain a register (`docs/ground-truth.md`, generated from `probes/registry.py`) in which
every engine-behaviour claim used by any bot has exactly one entry with: a stable ID, the claim text, status
(`ASSERTED` | `VERIFIED-WIN` | `VERIFIED-LINUX` | `REFUTED`), the probe that established it, the platform and
fcode version it was measured on, and the date.

#### Scenario: Unverified claim blocks merge
- **WHEN** a pull request into `elias_dev` introduces bot logic that depends on a claim whose status is
  `ASSERTED` or absent from the register
- **THEN** the PR is rejected until a probe exists and the claim reaches at least `VERIFIED-WIN`, with
  `VERIFIED-LINUX` required for any claim that gates strategy selection

#### Scenario: Refuted claim triggers dependency sweep
- **WHEN** a probe re-run flips a claim to `REFUTED`
- **THEN** every register entry and code site listing that claim as a dependency is flagged and the bot
  build fails until each dependent is re-reviewed

### Requirement: Falsification-first probe protocol

Every claim SHALL be tested by a probe designed to REFUTE it, not to confirm it. A probe consists of a bot
directory under `probes/`, an arena (stock map or generated `.map26`), and an assertion script that exits
non-zero when the claim fails.

#### Scenario: Probe attempts refutation
- **WHEN** a new claim is registered (from docs, a teammate, or an agent report)
- **THEN** the probe author writes the experiment that would most plausibly disprove it — including edge
  inputs (map borders, 8×8 minimum maps, occupied tiles, zero titanium) — before any confirming case

#### Scenario: Doc corrections are themselves suspect
- **WHEN** a claim originates from a "Correction vs. the official docs" block in `docs/`
- **THEN** it receives the same `ASSERTED` status as official-doc prose, since at least one such correction
  block has itself been contradicted by runtime measurement

### Requirement: Cross-platform verification for platform-sensitive claims

Claims in the following categories SHALL NOT be relied upon from Windows measurements alone: CPU timing and
TLE enforcement, combat legality (`can_fire`/`fire` semantics), import/sandbox behaviour, and anything where
Windows and WSL measurements have ever disagreed.

#### Scenario: Builder-damage question resolved per platform
- **WHEN** the builder-bot damage probe (`can_fire`/`fire` vs adjacent enemy Core, Barrier, Conveyor,
  Harvester, Builder Bot) is run
- **THEN** it is executed on both the Windows wheel and the manylinux wheel under WSL, results are recorded
  separately, and — until a Graviton3 `fcode match test` confirms — the Linux result is treated as ladder
  truth

#### Scenario: CPU profiling never trusted from Windows
- **WHEN** any CPU-budget measurement is taken
- **THEN** it is taken on Linux (where `get_cpu_time_elapsed()` returns real microseconds and `--tle` fires),
  with the working budget set to 3 ms local ≙ 10 ms ladder to absorb the Graviton3 gap

### Requirement: Round-zero map identification from precomputed atlas

The bot SHALL identify the current map at round 0 using only legally available information — map width,
height, own Core position, and team — against a precomputed atlas of the published 15-map pool, and SHALL
carry a fallback for unknown maps.

#### Scenario: Known map fingerprinted
- **WHEN** the game starts on a map whose `(width, height, core_position, team)` tuple matches the atlas
- **THEN** the bot loads that map's precomputed data: true enemy Core position (respecting each map's actual
  symmetry type — vertical, horizontal, diagonal, or 180°), ore coordinates, and the per-map opening

#### Scenario: Unknown map fallback
- **WHEN** the fingerprint matches no atlas entry (the pool "may be updated between rounds")
- **THEN** the bot falls back to online discovery and generic play, and never indexes into atlas data that
  does not exist

#### Scenario: Symmetry never assumed rotational
- **WHEN** enemy Core position is inferred rather than observed
- **THEN** the inference uses the per-map symmetry recorded in the atlas, never a blanket 180° mirror, which
  is wrong on 6 of the 15 known maps
