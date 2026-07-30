# `.replay26` File Format

*LLM-generated, not from the official site.* Reverse-engineered by diffing byte structure across controlled matches (custom probe bots, run via `fcode.fcode_engine.run_game(player_a, player_b, engine_root, map_path, replay_path, seed, tle)` — `engine_root = str(Path(fcode.__file__).resolve().parent)`).

`.replay26` files (default `replay.replay26`, written by `run_game()` / `fcode run`) are **protobuf**, same undocumented-wire-format situation as [.map26](map26-file-format.md) — no `.proto` is published. Reuses the same varint/protobuf-field reader.

## Top-level structure

- **field 1** (len-delim, appears once): the initial map snapshot, **byte-identical schema to `.map26`** — field1=width, field2=height, field3=rows, field4=Cores. This is the starting board state, not deltas.
- **field 3** (len-delim, repeated, one per round — 1000 of these in a full match): round records. Each round is a flat list of typed **event** sub-messages (see below).
- **field 4** (varint, appears once, at the very end after all rounds): winner. Observed value `0` for a Team A win; team B / draw values not yet confirmed (probably `1`=B, `2`=draw, or similar).
- **field 6** (bytes, appears once, at the very end): win condition as a **raw ASCII string**, e.g. `"coinflip"`. Matches the `win_condition` key in the `run_game()` result dict and the `condition_labels` map in `fcode/commands/run.py` (`core_destroyed`, `resigned`, `resources`, `titanium_collected`, `harvesters`, `titanium_stored`, `coinflip`, `timeout`).

## Event wrapper quirk

Every event inside a round is stored as `field 1` (len-delim) at the round level, but the *actual* payload is wrapped in **1–2 extra layers of trivial single-field `field 1` messages** before you reach real content — i.e. keep unwrapping `{1: <bytes>}` while the decoded message has exactly one field numbered 1 of wire-type 2, until you hit a message with more than one field (or a different field number):

```python
def unwrap(v: bytes):
    while True:
        fs = fields(v)  # the generic reader from map26-file-format.md
        if len(fs) == 1 and fs[0][0] == 1 and fs[0][1] == 2:
            v = fs[0][2]
            continue
        return fs
```

## Event catalog (after unwrapping)

Identified by the field number of the *unwrapped* payload. Confidence noted per entry — "confirmed" means verified against a controlled probe match with known ground truth (entity type, position, cost); "probable" is structural inference only.

| Field # | Meaning | Shape | Confidence |
|---|---|---|---|
| 1 (nested once more) | **Spawn/build**: a new entity appeared | `{1: id, 2: team (omitted=A, 1=B), 3: pos{1:x, 2:y}, 4: hp, 5: maxhp, N: type-marker}` | Confirmed |
| 2 | **Position changed** (movement *or* a Launcher throw — same encoding, just a bigger jump; there is no separate "launch" event) | `{1: id, 2: pos{1:x, 2:y}}` | Confirmed |
| 5 | Likely **HP delta / damage** | `{1: id, 2: signed delta}` (raw two's-complement varint, e.g. saw `-10`, matching Gunner damage) | Probable |
| 4 | Likely **attack/fire ray visualization**, batched (repeated within one field-4 event when multiple shots land the same round) | repeated `{1: pos, 2: pos, 3: value}` triples (shooter tile → target tile → damage?) | Probable |
| 6 | Likely **per-round vision/fog-of-war delta**; exactly one per round | deeply nested, references large tile-index-like numbers (row-major?) plus a 16-byte raw block (bitmask?) | Unconfirmed — not decoded |
| 7 | Per-entity per-round scalar, seen on Cores with small values (0/1) | `{1: id, 2: value}` | Unconfirmed (maybe action-performed flag) |
| 8 | Co-occurs 1:1 with field-2 move events (same id, same round) | `{1: id, 2: value}` | Unconfirmed (maybe move cooldown / facing) |
| 9 | Very high frequency (~18/round), per-entity | `{1: id, 3: value}` (field 3, not 2 — field 2 not observed here) | Unconfirmed (maybe stored/held titanium) |
| 3 | Rare, single scalar | `{1: value}` | Unconfirmed |

### Type-marker field numbers (spawn events)

The trailing field number on a spawn event's payload (beyond `1,2,3,4,5`) indicates entity type — **empirically determined, not a fixed formula** (does not match `EntityType`'s declaration order in the Python bindings):

| Marker field # | Entity type | How confirmed |
|---|---|---|
| 10 | BUILDER_BOT | Probe bot spawns exactly 1 builder/team → exactly 2 marker-10 events, hp 40/40, positions matched the Core's known NE-adjacent tile from `.map26` core anchor data |
| 11 | CONVEYOR | hp 20/20, high count in starter-bot replay (conveyors built constantly); marker submessage sometimes carries 1 extra field (facing direction) |
| 15 | HARVESTER | hp 30/30, moderate count in starter-bot replay, no facing payload |
| 21 | GUNNER | hp 40/40, marker submessage carries 1 extra field (facing direction) — distinguishes it from Builder Bot despite identical hp |
| 22 | SENTINEL | hp 30/30; confirmed by a probe bot that builds exactly one Sentinel — marker submessage carries 1 extra field (facing direction), like Gunner/Conveyor |
| 24 | LAUNCHER | hp 30/30, probe bot spawns exactly 1 launcher/team → exactly 2 marker-24 events |

Not yet observed/confirmed: CORE (pre-placed via the initial map snapshot's field4, never spawned as an event), SPLITTER, BARRIER.

### Facing-direction wire ordinal (marker submessages)

Directional entities (Conveyor=11, Gunner=21, Sentinel=22) carry one extra varint field in their type-marker submessage: the facing direction, encoded as **an ordinal that does not match the Python `Direction` enum's declaration order**. Confirmed one fixed point: a probe Sentinel built with a facing forced (by the probe bot's own code) to be exactly `Direction.SOUTH` (target directly south, no diagonal ambiguity) serialized as wire value **`5`**. The rest of the mapping is not yet reverse-engineered — would need a few more forced-facing probes (one per cardinal at minimum) to pin down fully.

## Verified end-to-end example

Used to sanity-check every piece above at once: a probe bot has its Core spawn one Builder Bot northeast of itself, the Builder builds a Launcher on an adjacent tile, and the Launcher throws the Builder as far northeast as the throw radius (dist²≤26, measured **from the Launcher, not the bot**) allows. On the `twins` map (21×21, Team A core anchor `(2,2)`, Team B anchor `(2,17)`):

- Builder (Team A) spawned at `(3,1)` — exactly the NE-adjacent tile to the Core anchor.
- Launcher (Team A) built at `(3,0)` — NE was already occupied by the Core's own 2×2 footprint, so the builder's build loop fell through to its next candidate.
- The builder's only field-2 position event: `(3,1) → (8,0)`, dist² from the Launcher `(3,0)` = 25. It couldn't reach the theoretical dist²=26 tiles (`(8,-1)`/`(4,-5)`) because they're off the top edge of the map (y<0) — confirms both the "measured from the Launcher" rule and that out-of-bounds candidates are correctly rejected by `can_launch`.
- Team B (mirrored, Launcher at `(3,15)`) landed its builder at `(4,10)`, dist²=26 exactly (room to move since not edge-constrained) — confirms the radius cap and tie-breaking toward the most diagonal (northeast-most) candidate when multiple tiles achieve the max distance.

## Reuse

The generic varint/protobuf-field reader is identical to the one in [.map26 file format](map26-file-format.md) — no protobuf library needed. A recursive dumper that prints the whole tree (for exploring an unfamiliar replay) is ~30 lines built on top of the same `fields()`/`read_varint()` pair shown there.
