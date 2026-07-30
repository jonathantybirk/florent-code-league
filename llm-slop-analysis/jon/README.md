# jon — LLM-assisted analysis

*Nothing here is authoritative; see [../README.md](../README.md).*

This directory collects LLM-assisted research and quantitative analysis for Florent Code League. It separates source-oriented competitor research from our own strategy models and cross-cutting background notes.

Research pass: 29 July 2026.

## Structure

- [`competitors/`](competitors/) contains organizer results, tournament comparisons, and team-authored strategy accounts.
- [`strategy/`](strategy/) contains our transferable conclusions and quantitative Florent strategy models.
- [`meta/`](meta/) contains lineage, terminology, research conventions, and the source register.

## Reading guide

- [Similar competitions](competitors/competitions.md) records how each organizer describes its event.
- [Cambridge Battlecode 2026](competitors/cambridge-battlecode-2026.md) separates Grand Finals results from ladder positions.
- [Published team accounts](competitors/published-team-accounts.md) summarizes only what named teams or members reported.
- [MIT Battlecode](competitors/mit-battlecode.md) records winners and selected participant postmortems.
- [Other recorded winners](competitors/other-recorded-winners.md) covers additional bot competitions.
- [Strategy and communications](strategy/strategy-and-communications.md) synthesizes transferable lessons and communication models.
- [Opening economy and Builder count](strategy/opening-economy-builder-count.md) models one to four initial Builders across every bundled map.
- [Opening economy revision](strategy/opening-economy-revision.md) is an independent engine-backed rebuild of the above: corrected route timing, conveyor-trunk capacity as the dominant constraint, and delivered-titanium tempo curves per Builder count.
- [Round-one and early-game information](strategy/round-one-information.md) separates API facts, map constraints, symmetry inference, current-pool observations, and a map-agnostic scouting protocol.
- [Engine and tutorial mechanics audit](meta/mechanics-audit.md) records where the bundled tutorials disagree with the running engine.
- [Jonbot map-agnostic implementation](strategy/jonbot-map-agnostic-implementation.md) documents the runtime information boundary, economy executor, symmetry inference, and full-pool smoke test.
- [Lineage and terminology](meta/lineage.md) records the Florent–Cambridge–MIT relationship.
- [Sources](meta/sources.md) is the link register.
- [`reference/`](reference/) holds reverse-engineered file formats and the rendered map atlas (moved out of `docs/`, since they are derived rather than official).

## Evidence conventions

- **Official result** means a result displayed by the competition organizer.
- **Organizer statement** means a claim made by an organizer but not independently derived here.
- **Team account** means a claim made by a team or one of its members.
- Ladder rank and tournament placement are recorded separately.
- “No artifact located” means that this research pass did not locate one. It does not mean that none exists.

The catalogue uses broad inclusion: submitted programs compete in a game or simulated environment without live move-by-move control. Inclusion is not a claim that two games have identical rules or that a strategy transfers between them.
