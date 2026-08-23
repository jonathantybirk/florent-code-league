# Reading guide: the GCS and the internal map

How to read `bots/utils/GCS` and `bots/utils/internal_map` in an order that makes sense. Each step says what
the file is for, what to look at, and what to skip on a first pass. Total code: ~2,000 lines; the first four
steps (about 600 lines) are enough to understand everything else.

## The one-paragraph version

Each team has 16 shared integers (the store). Writes made in round *N* are visible to everyone in round
*N+1*. The GCS gives **one slot to one unit** (slot 0 is the Core's) and packs each unit's message into its
u32 using *mixed radix* — multiply by each field's own size instead of rounding up to bits. A message is
mostly two **facts** ("tile T is in state S", with T named by its index in the sender's field of view) plus a
few tiny digits (a builder's last move, a gunner's turn). Readers **dead-reckon** every builder's position
from its move digits, so no message ever spends bits on coordinates. Everything else — who owns which slot,
which rounds use which format, who is dead — follows from conventions everybody can compute from the store
and the round number, so it costs no bits either. The **internal map** is each unit's picture of the board,
fed by its own eyes and by the store, and it decides what is worth saying next.

## Read in this order

### 1. `GCS/Base/protocol.py` — the wire format, as data (read fully)
Pure declarations; everything else is generated from them. Read top to bottom:
- **Reserved raw values** — the top 516 u32 values are not messages: two (unused) idle values, two free,
  and a 512-value block meaning "Core HP is exactly *h*" (written only when it drifts by >50).
- **Slot map** — Core 0, builders upward from 1, turrets downward from the top; `GCS_SLOTS` lets a bot keep
  some engine slots for itself (`starter_gcs` keeps 12–15).
- **Timing conventions** — spawn → `ASSIGN` → resync round → onboarding window. This block is the protocol's
  calendar; every reader computes the same calendar from the round number.
- **`TILE_STATES`** — the 65-code alphabet. Note the three *layers* comment: `WALL`/`ORE` are terrain,
  `OUR_…`/`ENEMY_…` are buildings or bots, `EMPTY` means "nothing built or standing here".
- **`LAYOUTS`** — one tuple of `(field, radix)` per sender kind. This is the whole message format. The
  import-time assert proves each layout fits in a u32.
- **Escapes and control kinds** — `RUN`, `REMOTE`, `CONTROL` (`ASSIGN`, `SYMMETRY`, `DIRECTIVE`, `GRANT`).

`PROTOCOL.md` is `dump_protocol()`'s output: the same thing as tables.

### 2. `GCS/Base/codec.py` — mixed radix (50 lines)
`pack(digits, radices)` and `unpack(value, radices)`. Read both functions once; after that, every "encode"
in the module is just "build the digit list, call pack".

### 3. `GCS/Base/fov.py` — naming tiles without coordinates (40 lines)
For each unit kind, the tiles within its vision radius in a fixed reading order. `index_of(dx, dy)` and
`offset_of(index)`. Occlusion never changes the numbering; a unit just never mentions a tile it cannot see.

### 4. `GCS/Base/messages.py` — encode and decode (the core of the module)
Stateless. Read in this order:
- `Fact`, `ControlEvent`, `Decoded` — the data types every other file passes around.
- `encode_standard` / `decode_standard` — the common case: prefix digits + two facts. Note the *filler*
  (state `UNKNOWN`, ignored by readers) and its `parity` trick used to avoid ever repeating a value.
- `classify_raw` — is this u32 a reserved value or a payload?
- The escape section: `_encode_with_combined` / `_combined_parts` explain the one trick used by all three
  escapes — `fact_a`'s index digit and every field after it are read *together* as one big number.
- `encode_resync` / `decode_resync` — position + kind + one fact; self-describing so a newborn can read it.
- `chain_params` / `encode_onboard` / `decode_onboard` — the Core's absolute-coordinate stream: one
  absolute fact plus one fact relative to it.

Skip on first pass: `run_max_len`, `ctrl_args_cap` (capacity arithmetic).

### 5. `GCS/Base/registry.py` — who owns what, and what round it is
Every unit has its own `SlotRegistry`; they converge because their inputs are identical. Read:
- `Owner` — kind, position (dead-reckoned for builders), facing, round-robin period/phase.
- `absorb_snapshot` — the per-round loop: for each slot, `_absorb_slot` picks the format from the
  calendar (`resync`, `onboard`, or standard) and the owner's kind, then `_settle_grants`, `_liveness`.
- `_absorb_slot` — the decision tree. This is where "which format is this slot in right now" lives.
- `_liveness` — an owner whose value did not change on a round it should have written is dead.
- `_on_assign`, `_settle_grants`, `_probe_grant` — how builders and turrets come to own slots, and how
  same-round grant collisions are settled identically by everyone.
- `is_resync_round`, `_in_onboard_window`, `may_write` — the calendar and the write gate.

### 6. `GCS/Base/gcs.py` — the facade a bot actually calls
- `absorb(ct)` → reads the store, updates the registry, applies facts to the map, forwards events.
- `publish(ct)` → the fallback ladder in `_publish` and `_publish_facts`: queued control → HP → resync →
  onboarding stream (Core) → new facts (standard) → new fact via `REMOTE` → restate old facts
  (`_publish_restate`) → empty message with parity. **The store never idles.**
- `_move_digit` — why `publish()` must be called *after* moving.
- Core helpers: `core_announce_assign`, `_core_stream`; builder helper: `grant_turret`.
Both public calls catch everything: a bug inside never costs the bot its turn.

### 7. `GCS/Base/interfaces.py` — the seam to other modules
`MapSource` is the five-method contract the map fulfils; `CLASS_WEIGHTS` is the priority table; the issue
detectors and `on_directive` are placeholders for logistics/behaviour.

### 8. `internal_map/Base/internal_map.py` — what a unit knows
- `Tile` = three `Record`s (terrain, building, unit), each with state, round, source, published.
- `observe(ct)` — own eyes → records; `apply_fact` — the store → records.
- `_record` — the merge rules in one place: newer wins, fresh own eyes beat a teammate's report, overlays
  don't displace buildings, what is *born published* (plain ground, "no bot here", our own bots).
- `pending_facts` / `known_facts` — what the GCS may say next, and what it may restate.
- Symmetry: `_infer_symmetry` (eliminate candidates, adopt the survivor), `_mirror_all`, `enemy_core()`.

### 9. Verification and tooling
- `tests/test_gcs.py`, `tests/test_internal_map.py` — headless; the `World`/`FakeController` harness at the
  top of `test_gcs.py` is the quickest way to see a whole round's choreography.
- `bots/gcsprobe` (random walk) and `bots/starter_gcs` (real logic) run the module in the engine; both print
  a `GCSTRACE` line per unit per round via `GCS/Base/trace.py`.
- `tools/gcs_viz.py replay --report` prints reckoning/fact tallies; `tools/gcs_viz.py replay out.html` is
  Store Scope — click a unit, see its internal map beside the truth and the store as it decodes it.

## Following one round end to end
1. Engine calls `Player.run`. Bot calls `gcs.absorb(ct)`: `registry.absorb_snapshot` decodes all slots →
   facts go to `map.apply_fact(..., from_gcs=True)` (published on arrival), events to the bot.
2. Bot calls `map.observe(ct)`: own eyesight, new facts marked unpublished.
3. Bot acts and moves.
4. Bot calls `gcs.publish(ct)`: picks the best thing to say, packs it, `write_store`, marks exactly those
   facts published. Visible to everyone next round.

## Vocabulary
slot · owner · fact · FOV index · mixed radix · escape code · resync round · onboarding window · dead
reckoning · negative (an `EMPTY` that cancels something known) · restate (say an old fact again rather than
idle) · grant (a builder giving its new turret a slot).
