# jon — LLM-assisted analysis

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

*Nothing here is authoritative; see [../README.md](../README.md).*

This directory collects LLM-assisted research and quantitative analysis for Florent Code League. It separates source-oriented competitor research from our own strategy models and cross-cutting background notes.

Research pass: 29 July 2026. Second external-source pass: 5 August 2026.

## Structure

- [`legacy/`](legacy/) holds the 29 July research pass: organizer results, tournament
  comparisons, team-authored strategy accounts, our early strategy models, and the source
  register. All of it predates engine 2.3.3 — read [`legacy/README.md`](legacy/README.md) first.
- [`reference/`](reference/) holds reverse-engineered file formats, the rendered map atlas, and
  digests of external technical sources.
- [`tools/`](tools/) holds analysis scripts and notes on tooling.

> The former `competitors/`, `strategy/`, and `meta/` directories were emptied when their
> contents moved into `legacy/`. The links below point at the current locations.

## Reading guide — 5 August 2026 external sources

- [Pantheon / "Khaos" postmortem](reference/pantheon-khaos-postmortem.md) is the **Cambridge
  Battlecode winner's account of the game our engine is derived from**. It is the artifact that
  [`legacy/published-team-accounts.md`](legacy/published-team-accounts.md) and
  [`legacy/sources.md`](legacy/sources.md) both record as not located — those two "no artifact
  located" notes are now stale. It carries a Cambridge-vs-Florent engine divergence table that
  must be applied before borrowing anything from it.
- [XSquare's Guide to Battlecode](reference/xsquare-battlecode-guide.md) is process and
  code-structure advice from a long-running MIT competitor. Its bytecode section is Java-engine
  specific and does not apply to us; its testing discipline does.
- [oarena](tools/oarena.md) is a third-party web UI, replay visualiser, and local league runner
  built for **this competition specifically**, with a read-only client that downloads live
  ladder replays.

## Reading guide — 29 July 2026 pass (pre-2.3.3, treat as stale)

- [Similar competitions](legacy/competitions.md) records how each organizer describes its event.
- [Cambridge Battlecode 2026](legacy/cambridge-battlecode-2026.md) separates Grand Finals results from ladder positions.
- [Published team accounts](legacy/published-team-accounts.md) summarizes only what named teams or members reported.
- [MIT Battlecode](legacy/mit-battlecode.md) records winners and selected participant postmortems.
- [Other recorded winners](legacy/other-recorded-winners.md) covers additional bot competitions.
- [Strategy and communications](legacy/strategy-and-communications.md) synthesizes transferable lessons and communication models.
- [Opening economy and Builder count](legacy/opening-economy-builder-count.md) models one to four initial Builders across every bundled map.
- [Opening economy revision](legacy/opening-economy-revision.md) is an independent engine-backed rebuild of the above: corrected route timing, conveyor-trunk capacity as the dominant constraint, and delivered-titanium tempo curves per Builder count.
- [Round-one and early-game information](legacy/round-one-information.md) separates API facts, map constraints, symmetry inference, current-pool observations, and a map-agnostic scouting protocol.
- [Engine and tutorial mechanics audit](legacy/mechanics-audit.md) records where the bundled tutorials disagree with the running engine.
- [Jonbot map-agnostic implementation](legacy/jonbot-map-agnostic-implementation.md) documents the runtime information boundary, economy executor, symmetry inference, and full-pool smoke test.
- [Lineage and terminology](legacy/lineage.md) records the Florent–Cambridge–MIT relationship.
- [Sources](legacy/sources.md) is the link register.

## Evidence conventions

- **Official result** means a result displayed by the competition organizer.
- **Organizer statement** means a claim made by an organizer but not independently derived here.
- **Team account** means a claim made by a team or one of its members.
- Ladder rank and tournament placement are recorded separately.
- “No artifact located” means that this research pass did not locate one. It does not mean that none exists.

The catalogue uses broad inclusion: submitted programs compete in a game or simulated environment without live move-by-move control. Inclusion is not a claim that two games have identical rules or that a strategy transfers between them.
