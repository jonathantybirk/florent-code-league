# Game Rules — Builder Bot

Source: https://game.code.florent.vc/docs/game-rules-builder-bot

## Overview

**Builder Bots** are your team's mobile workforce. They are the only entities that can move freely across the map, and they are responsible for constructing and repairing all buildings.

## Stats

| Property | Value |
|----------|-------|
| HP | 40 |
| Cost | 30 Ti |
| Vision radius² | 20 |
| Action range | Orthogonally adjacent tile only (Build, Attack, Heal, Destroy — no radius) |
| Move cooldown | 1 round |
| Action cooldown | 1 round |

## Passable Terrain

Builder Bots can traverse:

- Any tile with no building, excluding `WALL` tiles (including `EMPTY` and `ORE_TITANIUM` tiles)
- Tiles with Conveyor or Splitter buildings from either team

Impassable terrain includes walls, other Builder Bots, and tiles occupied by Harvesters, Barriers, Cores, or turrets.

## Abilities

- **Move:** Travel one tile in cardinal directions only. Builder Bots **cannot move diagonally**; attempting diagonal movement raises an error.
- **Build:** Construct buildings on orthogonally adjacent tiles. Building triggers an action cooldown.
- **Attack:** Damage enemy buildings on adjacent orthogonal tiles at 2 Ti per hit for 2 damage, primarily for sabotage.
- **Heal:** Heals 4 HP for 1 Ti on friendly entities at orthogonal positions.
- **Destroy:** Remove allied buildings on adjacent tiles at no cost without using action cooldown.
- **Self-destruct:** Destroy the Builder Bot without dealing damage.

## Unit Cap

Builder Bots count toward the 50-unit team cap.
