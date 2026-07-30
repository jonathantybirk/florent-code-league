# Jonbot map-agnostic opening implementation

Implementation and validation pass: 31 July 2026.

## Runtime information boundary

Jonbot does not import map files, branch on map names, contain known ore/core
coordinates, or match live observations against bundled-map fingerprints. Its
decisions use only `Controller` information available during the match:

- map width and height;
- own Core position found through vision;
- locally visible terrain, buildings, and units;
- legal `can_*` actions, resources, and cooldowns; and
- the team's 16-slot delayed communication store.

Offline scripts may use the bundled maps to evaluate a policy, but none of
that map-specific state is imported by `bots/jonbot/`.

## Opening economy

- The Core spawns exactly two Builders on rounds 0 and 1.
- Builders obtain deterministic ids and lease distinct visible ore through
  store claims.
- A job is ranked by Builder travel plus cardinal conveyor length.
- The Harvester is built first. The Builder then walks the planned line toward
  the Core, building a Conveyor beneath itself and moving in the same round.
- Existing lines are treated as obstacles, preventing accidental saturated
  shared trunks.
- Idle Builders leave already-visible sectors instead of occupying economy
  routes. This fixes the Hive/Longship deadlock found in the first version.

The online router is deliberately optimistic about unseen terrain and replans
from new observations. This is a heuristic under fog, not hidden map access.

## Enemy-Core inference

Each Builder independently maintains the three rule-compatible hypotheses:

1. 180-degree rotation;
2. reflection across the vertical axis; and
3. reflection across the horizontal axis.

A hypothesis is rejected when observed paired terrain differs or its complete
predicted Core footprint is visible without an enemy Core. The two opening
Builders have separate single-writer rejection slots, avoiding buffered-store
lost-update races. Direct enemy-Core sight is broadcast immediately. If all
surviving hypotheses imply one coordinate, that coordinate is broadcast as the
inferred target.

When no visible economic job exists, the two Builders split the unresolved
candidate footprints. This makes scouting information-directed while still
discovering terrain and ore along the route.

## Seed-1 full-pool smoke test

Opponent: `do_nothing_bot`; 1,000 rounds. Every bundled map produced positive
mined titanium after the congestion fix.

| Map | Stored Ti | Mined Ti |
|---|---:|---:|
| atoll | 14,640 | 12,190 |
| aurora | 23,118 | 21,220 |
| crossfire | 17,219 | 14,640 |
| duel | 12,648 | 9,880 |
| fjord | 16,828 | 14,480 |
| hive | 16,711 | 14,500 |
| longship | 18,806 | 16,620 |
| pinch | 10,018 | 7,380 |
| quarry | 28,912 | 27,540 |
| runestone | 21,527 | 19,190 |
| skerry | 23,296 | 21,420 |
| sprint | 14,905 | 12,270 |
| strait | 14,643 | 12,200 |
| twins | 18,900 | 16,710 |
| vault | 12,039 | 9,670 |

This is a smoke test of economy execution, not evidence of combat strength.
Harassment, defense placement, route repair, and symmetry-target confirmation
against an active opponent still need adversarial tests.
