# Florent Code League — Documentation

A single corrected mirror of the official docs at https://game.code.florent.vc/docs/ and https://game.code.florent.vc/tutorials, plus a small amount of original reference material.

## How this is organized

- **Every page below is based on the official site's text**, reformatted to Markdown. Where the installed `fcode` engine actually disagrees with what the site says, the page has a `> **Correction vs. the official docs.**` callout at that exact spot — the surrounding text is corrected to match reality, and the callout explains what changed and how it was verified (usually: enumerating the real `Controller`/`Position`/`Direction` objects at runtime, or a direct call that raises `AttributeError`).
- **`reference/`** and **`maps/map-atlas.md`** are not from the official site at all — original material written for this repo (reverse-engineered file formats, a rendered map atlas). Each says so at the top.
- **`scraped-originals/`** keeps the raw, byte-for-byte scraped source text (unedited) — kept around so any correction above can be checked against exactly what the site said. If you're only reading the docs, you want the pages above, not this folder.

If you find something else that's wrong, verify it against the running engine (a probe bot that calls `dir(ct)` or attempts the call directly beats trusting prose) before "correcting" it — this doc set has been burned by trusting the official site more than once.

## Getting Started
- [Florent Code League (overview)](getting-started/florent-code-league.md)
- [Quick Start](getting-started/quick-start.md)

## CLI
- [Installation](cli/cli-installation.md)
- [Your First Bot](cli/cli-first-bot.md)
- [Running Matches](cli/cli-running-matches.md)
- [Submitting](cli/cli-submitting.md)
- [CLI Reference](cli/cli-reference.md)

## Game Rules
- [Overview](game-rules/game-rules-overview.md)
- [How Matches Work](game-rules/game-rules-how-matches-work.md)
- [Core](game-rules/game-rules-core.md)
- [Builder Bot](game-rules/game-rules-builder-bot.md)
- [Turrets](game-rules/game-rules-turrets.md)
- [Conveyors](game-rules/game-rules-conveyors.md)
- [Harvester](game-rules/game-rules-harvester.md)
- [Other Buildings](game-rules/game-rules-other-buildings.md)
- [Resources](game-rules/game-rules-resources.md)
- [Reference](game-rules/game-rules-reference.md)

## API Reference
- [Controller API Reference](api-reference/robot-api.md)
- [Types & Enums](api-reference/api-types.md)
- [Global Communication Store](api-reference/global-comms.md)

## Agents
- [AGENTS.md](agents/agents-md.md) — copy this into your bot project as `AGENTS.md`/`CLAUDE.md` for AI coding assistants

## Tutorials

Five modules, 24 lessons total, in order:

1. **Your First Bot: Movement & Sensing** — [Welcome](tutorials/movement-sensing/01-welcome.md), [Spawning](tutorials/movement-sensing/02-spawning.md), [Moving](tutorials/movement-sensing/03-moving.md), [Sensing](tutorials/movement-sensing/04-sensing.md), [Recap](tutorials/movement-sensing/05-recap.md)
2. **Harvesting Titanium** — [The Titanium Economy](tutorials/harvesting-titanium/01-the-titanium-economy.md), [Finding Ore](tutorials/harvesting-titanium/02-finding-ore.md), [Building a Harvester](tutorials/harvesting-titanium/03-building-a-harvester.md), [Cost Scaling](tutorials/harvesting-titanium/04-cost-scaling.md), [Recap](tutorials/harvesting-titanium/05-recap.md)
3. **Logistics: Conveyors & Splitters** — [Why Routing Matters](tutorials/conveyors-logistics/01-why-routing-matters.md), [Building a Conveyor Chain](tutorials/conveyors-logistics/02-building-a-conveyor-chain.md), [The Last Mile](tutorials/conveyors-logistics/03-the-last-mile.md), [Splitting the Flow](tutorials/conveyors-logistics/04-splitting-the-flow.md), [Recap](tutorials/conveyors-logistics/05-recap.md)
4. **Building an Army: Turrets & Combat** — [Meet the Turrets](tutorials/turrets-combat/01-meet-the-turrets.md), [Building a Gunner](tutorials/turrets-combat/02-building-a-gunner.md), [The Ammo Gap](tutorials/turrets-combat/03-the-ammo-gap.md), [Healing and Sabotage](tutorials/turrets-combat/04-healing-and-sabotage.md), [Recap](tutorials/turrets-combat/05-recap.md)
5. **Coordination & Strategy** — [The Global Communication Store](tutorials/comms-strategy/01-the-global-communication-store.md), [Coordinating Roles](tutorials/comms-strategy/02-coordinating-roles.md), [Putting It All Together](tutorials/comms-strategy/03-putting-it-together.md), [Where to Go From Here](tutorials/comms-strategy/04-where-to-go-from-here.md)

The turret combat tutorials (module 4) needed the heaviest correction — the official docs' ammo model (a team-wide pool filled by the Core) doesn't exist in the engine. Ammo is per-turret and conveyor-fed; the corrected tutorials rebuild the same lessons around that.

## Maps (original, not from the official site)
- [Map Atlas](maps/map-atlas.md) — all pool maps rendered in isometric + replay top-down views

## Reference (original, not from the official site)
- [.map26 file format](reference/map26-file-format.md) — the map file format, reverse-engineered
- [.replay26 file format](reference/replay26-file-format.md) — the match replay format, reverse-engineered
