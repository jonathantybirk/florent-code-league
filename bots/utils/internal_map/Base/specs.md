# Overview
This module contains the standards for the internal maps for our units. Every unit has an internal map which essentially holds all information they have about the map, including age of info, how it was obtained

They will share information on the GCS or see things themselves, which is the two input
---

# Resolved design (implemented 2026-08-22)

Everything above is the original brief. `internal_map.py` is the implementation; `tests/test_internal_map.py`
the headless tests (`.venv/bin/python -m pytest tests/test_internal_map.py`).

## What it is
One `InternalMap` per unit. Every tile has **three layers**, each with its own record:

- **terrain** — `EMPTY` / `WALL` / `ORE`, what the ground is. Never changes, so ore knowledge is never
  erased by whatever is built on top of it.
- **building** — a structure on the terrain (`OUR_…` / `ENEMY_…` building codes), or `EMPTY` for "nothing
  built here". Ages, and is cleared by a negative.
- **unit** — a Builder Bot on the tile (`OUR_BUILDER_BOT` / `ENEMY_BUILDER_BOT`), or `EMPTY`. Bots move
  every round, so this layer is never worth a negative on the store; age handles it. Our own bots are
  recorded but never announced (teammates dead-reckon them).

A tile with ore, a conveyor and a bot is three facts; a Core fills all four tiles of its 2×2 block
(`our_core` / `enemy_core()` give the top-left anchor). Each record holds:

| field | meaning |
|---|---|
| `state` | a code from the GCS tile-state alphabet (`bots/utils/GCS/Base/protocol.py` → `TILE_STATES`), e.g. `WALL`, `ORE`, `OUR_CONVEYOR_E`, `ENEMY_GUNNER_N`, `ENEMY_BUILDER_BOT` |
| `round` | the round the information dates from; `age(x, y)` = current round − this |
| `source` | `SEEN` (own eyes), `GCS` (a teammate said so), `INFERRED` (derived from the map's symmetry) |
| `published` | whether this fact is already on the store — ours or anyone's |

The two inputs from the brief are the two entry points:

- **`observe(ct)`** — own eyesight. Scans every tile and entity in vision and records terrain, buildings
  with their facing, and bots — each in its own layer. Skips the unit itself
  (teammates track us by dead reckoning). Also records `TOOK_FIRE_HERE` on our own tile when our HP dropped
  and no enemy turret is in sight.
- **`apply_fact(fact, from_gcs=True)`** — the store. Anything that arrives this way is marked published on
  arrival: the whole team has already seen it.

It fulfils the GCS `MapSource` contract, so a unit wires it in with `GCS(kind, InternalMap(w, h))` and the
GCS publishes straight out of it: `pending_facts()` (unpublished, best first), `note_shared()` (only what a
write actually carried), `known_facts()` (everything, for restating), `symmetry()`.

## Rules that decide what is true and what is news
- **Newer information wins.** A teammate's report never overrides what we saw ourselves in the same or a
  later round.
- **Terrain never goes stale**; everything else decays for priority purposes over `FRESH_ROUNDS = 30`
  rounds (`score = class_weight × max(0.1, 1 − age/30)`). Class weights are the GCS's
  `interfaces.CLASS_WEIGHTS`.
- **Negatives are news, plain emptiness is not.** Seeing `EMPTY` where we recorded a building or unit is a
  fact worth publishing (the thing is gone). Seeing no occupant on a tile we never knew, or plain ground
  under anything, is recorded but marked published — nobody needs to be told that. On the wire `EMPTY`
  always means "no occupant".
- **Overlays don't replace identity.** `TOOK_FIRE_HERE`, `CONVEYOR_ISSUE`, `HARVESTER_ISSUE` are applied on
  top of whatever the tile holds; they only become the tile's state if it was empty or unknown.
- **Re-confirming a fact refreshes its round but keeps it published** — nothing new to tell anyone.

## Symmetry
Maps come in three kinds (`SYMMETRY_KINDS`): `MIRROR_X` (left-right), `MIRROR_Y` (top-bottom), `ROT_180`.
Every unit infers the kind itself: each observed terrain tile whose twin under a candidate kind is also
observed either supports the candidate or eliminates it; once one candidate remains with at least
`SYMMETRY_MIN_EVIDENCE = 6` supporting pairs it is adopted. Whichever unit gets there first announces it once
on the store (`CONTROL/SYMMETRY`); `set_symmetry()` accepts that, so the others don't have to re-derive it.

Once known: every observed terrain tile implies its twin, recorded as `INFERRED` and **marked published**
(anyone who knows the symmetry can derive it, so it never costs store bandwidth); and `enemy_core()` follows
from `our_core` — the 2×2 block is mirrored as a block (the far corner maps to the new anchor), which is
why naïvely mirroring the anchor tile alone is off by one on the mirrored axis. `our_core` is learned from
any `OUR_CORE` tile, so builders derive the enemy Core too. Verified live on frostgate: inferred `MIRROR_X`,
derived `(16, 9)`, the real enemy Core.

## Queries for other modules
`terrain_at(x, y)`, `building_at(x, y)`, `unit_at(x, y)`, `state_at(x, y)` (unit, else building, else
terrain), `age(x, y)`, `is_passable(x, y)` (True/False/None-if-unknown; conveyors and splitters are
walkable, everything else that is built is not), `enemy_core()`, `our_core`, `tiles` (the raw records).

## Not in scope here
- Deciding what to do with the knowledge (pathfinding, mining, combat) — those modules read this map.
- The `CONVEYOR_ISSUE` / `HARVESTER_ISSUE` detectors — the logistics module raises those via `apply_fact`.
- Enemy builder movement inference (the GCS brief's TODO); enemy bots are plain per-tile sightings.
- The "behind the direction of travel" preference for the Core's onboarding stream — the Core streams by
  score; receiver-aware ordering would go in `pending_facts` once a receiver position/heading is passed in.
