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
that map-specific state is imported by `bots/jon/fair/jonbot/`.

## Opening economy

- The Core spawns exactly two Builders on rounds 0 and 1, placing them toward
  distinct visible ore staging tiles and otherwise toward generic symmetry
  scout targets.
- Builders obtain deterministic ids and lease distinct visible ore through
  store claims.
- A job is ranked by Builder travel plus cardinal conveyor length.
- Construction uses only fully observed terrain. The Builder lays the line
  outward from the Core or a known-good trunk and builds the Harvester last,
  making “every built Harvester is connected” true by construction.
- Each Builder owns a reusable conveyor network capped at four Harvesters, the
  engine-measured throughput limit. Other lines remain obstacles.
- Idle Builders leave already-visible sectors instead of occupying economy
  routes. This fixes the Hive/Longship deadlock found in the first version.

Unknown terrain is never treated as permission to spend. Builders scout until
they know a complete route. They replan when newly observed infrastructure
invalidates an unbuilt segment.

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

## Replay-topology audit

`../tools/analyze_replay_economy.py` decodes `.replay26` files directly and
checks the final directed conveyor graph. Against `do_nothing_bot` for 1,000
rounds on every bundled map, every built Harvester had a valid accepting path
to the Core: **100% connected on 15/15 maps**. This caught bugs that the match
summary's positive aggregate mining had hidden: incompatible conveyor reuse,
routes invalidated by walls revealed through fog, and committing Harvesters
before their lines were proven.

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

The table above predates the topology fixes and is retained as historical
context rather than a performance benchmark. The topology audit is a smoke
test of economy correctness, not evidence of combat strength.
Harassment, defense placement, route repair, and symmetry-target confirmation
against an active opponent still need adversarial tests.
