# Overview
This module contains the GCS store standards and mechanics

# Slot usage
Slots are dedicated to units so one unit owns one slot. In cases where there are too many units, a round-robin can function as fallback, especially for launchers and turrets as they are less important than builders irt. to sharing info 
1: core
2: builder
… (prioritize builders getting a slot)

16: launchers/turrets (if there are empty slots they are given one each starting from 16 and going down until the last empty slot, new builder’s are prioritized to take over turret/launcher slots, until n (hyperparameter) slots are left for turrets/launchers). When there are too many builders (i.e. >15-n) or too many launcher/turrets (i.e. >min(,n) we do a round robin where some builders or turrets/launchers must share the same slot, that means they only get to use it every p rounds (calculated from the global round number, order can be determined from ID) where p is the amount sharing the same slot. This can be per-slot (I.e. 15 is shared by p=2, 16 is only used by p=1. Or 15 is shared by p=6 and 16 is shared by p=5)

# Info-sharing roles:
0: unless more important (free to be determined by a priority system which is a “hyperparameter”) things need to be communicated, all units should try to update everyone on the GCS store with their internal map. In their internal map (different module), it should be updated whether a piece of information has been shared already or not
1: Core will be the central memory system. When new builders are spawned, it assigns them a GCS ID (1-16) based on what is not already taken, and how long it will take to update the bot. Then it uses the bots GCS slot for the next 5-10 (hyperparameter, if not variable the core obviously need not announce how many rounds it will take) rounds and give it map updates including of course map symmetry and more.

# What if needed functionality outside the module’s scope isn’t implemented yet
Use placeholders and inform the user. Keep current implementation to the scope of the module. 

# How to embed
We have a single uint32 number per GCS slot (thus per unit). Instead of assigning bits, we can just assign what is necessary. I.e. if “what is the next message” is 5 potential message, don’t use 3 bits, just divide by 5 instead of 8, use modulo 5 instead of 8 etc. mixed-radix
# Embeddings
## encoder/decoder conventions (and convolutions??)
we need a convention for indicating the state of a tile, we could just make a convention for all possible tile states and enumerate/encode them: {1: “empty”, 2: “titanium_empty”, 3: “titanium_occupied_us”, 4: “titanium_occupied_theirs”, [...], 45: “enemy_turret_N”, 46: “enemy_turret_NW” [etc…] } which in turn can be decoded “locally” at each unit. with this, lookup and updating game state correspondingly would be O(1) for units, so satisfying 10ms max per unit remains  a negligible constraint. 
Another idea is taking common, super-tile patterns and compressing them into less bits such as a long path of enemy conveyors, which can be expressed as a starting coordinate, a cardinal direction, a length and obviously a compression marker, although it might be limited how often this representation is cheaper than just utilizing the already streamlined worker FOV tile order (read below) for relaying conveyer belt locations; Some simple experiments can decide this in minutes.

## builders
since these can move, they simply share their movements (5 possibilities) and the other units can then derive their exact location from this. Then, they also send updated info on all visible tiles in an embedding order we decide (reading direction of rows from top to bottom is likely the simplest, but doesn't really matter as long as we are consistent). the things it can update on includes but is likely not limited to: enemy workers, enemy core health, enemy turrets/sentinels (plus their directions, the worker also marks tiles in which it has been under fire if the adversary is not visible, but this is low-priority information to share), enemy miners, enemy conveyers, titanium ores, walls, enemy barriers, enemy launchers. Another important note is that fov can be obstructed by walls/barriers which should be accounted for (we don’t have info on tiles that are not in FOV)

Obviously also information negatives are important

### formatting
[message_type] x [detes] x [message_type] x [detes] etc… until filled
4 reserved for special messsage types (literally just the 4 last numbers, barely reduces the amount of information we can tell). One of these can e.g. be to tell everyone to not write to GCS next round because this unit wants to use all of them. 

## turrets 
- share if turning

## enemy builders
# TODO special embeddings for a builder moving so we don’t have to announce both the disappearance and appearance of a bot we see moving. Honestly, if a bot has moved it can be inferred that it must have been the one that was next to that spot one round ago.



---

# Resolved design (implemented 2026-08-22)

Everything above is the original brief. This section records what was decided and built. The exact wire
format — every reserved value, layout, tile-state code and field value — is **generated** from
`protocol.py` into [PROTOCOL.md](PROTOCOL.md) (`python -c "from utils.GCS.Base.protocol import
dump_protocol; print(dump_protocol())"`), so that file cannot drift from the encoder.

## Files
| file | role |
|---|---|
| `protocol.py` | declarative wire format: reserved values, slot map, alphabet, layouts, control/task tables |
| `codec.py` | mixed-radix `pack`/`unpack`; `CodecError` (a `ValueError` — see "engine constraints") |
| `fov.py` | FOV index tables per entity type (full geometric disc, reading order) |
| `messages.py` | stateless encode/decode: standard, RUN/REMOTE/CONTROL escapes, resync, onboarding chain |
| `registry.py` | slot ownership, ASSIGN/grant handling, liveness & reclamation, round windows, Core knowledge model |
| `gcs.py` | per-unit facade: `absorb`, `publish`, `queue`, `send_raw`, Core helpers |
| `interfaces.py` | placeholders for the internal-map / logistics / behaviour modules |
| `tests/test_gcs.py` | headless tests (pytest) |
| `bots/gcsprobe/` | real-engine probe bot used for end-to-end verification; prints a `GCSTRACE` JSON line per unit per round |
| `tools/gcs_viz.py` | turns a probe replay into **Store Scope**, a side-by-side viewer of the board and the decoded store; `--report` prints reckoning/learned-fact tallies |

## Slots
Engine indices 0–15. **0 = Core** (never reclaimed). Builders take 1, 2, … upward; turrets/launchers take
15, 14, … downward; the bottom `TURRET_RESERVED_SLOTS = 2` are never evicted by builders. Round-robin
sharing is per slot via `(period, phase)` carried in ASSIGN: the owner writes only when
`round % period == phase`.

## Reserved raw values (top of the u32 range)
`IDLE_A`/`IDLE_B` — alternating zero-payload heartbeat; two values free; a 512-value block for the Core's
**exact HP**, written only when HP has drifted > 50 from the last published value (HP starts at 500, which
everyone knows, so nothing is announced until it drifts). Payload space is `2^32 − 516`.

## Liveness (no sequence counter)
A live unit never writes the same u32 two rounds running. An unchanged slot on a round its owner was
scheduled to write ⇒ the owner is dead and the slot is reclaimed at once. Exemptions: off-phase
round-robin turns, the resync round, turret slots during onboarding, and slot 0.

A unit with nothing new to say does **not** send a bare idle value: it sends an empty standard message,
so its `move`/`turn` digit still goes out, with the filler fact's FOV index toggled (0/1) as a parity bit
(receivers ignore `UNKNOWN`-state facts whatever their index). The raw `IDLE_A`/`IDLE_B` values are only
the fallback when no message can be built. This was found by the visualiser: a builder that idled once lost
that round's move and its reckoned position drifted for the rest of the match.

## Per-sender layouts (most-significant first; `fact = FOV × 106`)
- Builder: `move(5) · fact_a · fact_b · aux(16)` — 1.004× full. `aux` = slot granted to a friendly
  turret/launcher named by a fact in the same message.
- Gunner: `speaker(2) · turn(3) · fact_a · fact_b`. `turn` = none/CW/CCW (one step per round by convention).
- Sentinel, Launcher: `speaker(2) · fact_a · fact_b` (sentinels cannot rotate in the engine).
- Core: `fact_a · fact_b`.
`speaker = 1` means the Core is speaking through a turret slot (onboarding, absolute coordinates).

## Escapes (state codes 103–105 in `fact_a`)
`RUN` (start index, direction, length, state), `REMOTE` (one absolute fact — also the automatic fallback
when a sender has nothing inside its FOV to say), `CONTROL` (`ASSIGN`, `SYMMETRY` (3 kinds, no coords),
`DIRECTIVE` = `x · y · task(24)` where task 0 = FIX_HARVESTER (anyone, unaddressed), 1–15 = FIX_CONVEYOR
addressed to that builder slot (Core only), 16–18 = BUILD/SCOUT/DEFEND_HERE).

## Spawn choreography (all common knowledge, zero header bits)
1. Core spawns in round R and writes `ASSIGN(slot)` the same round (outranks the HP announcement).
2. **The engine first runs the newborn in round R+1** (verified live) — the round the ASSIGN is readable.
   It matches on `first_run − 1 == R` and takes the slot.
3. Round R+1 is the **resync round**: every unit (Core included) writes `pos(W·H) · fact`. Readers decode
   the R+2 snapshot as resync format; dead reckoning restarts from exact positions.
4. Rounds R+2 … R+1+`ONBOARD_ROUNDS` (8): the Core streams absolute-coordinate **chains** (one absolute fact +
   one fact relative to it, window radius 9 in its own slot / 6 in a borrowed turret slot on 30×30) through
   its own slot and every turret/launcher slot; turrets stay silent. The Core keeps a per-slot model of what
   each unit already knows and streams only the rest.
5. The Core must not spawn while a resync/onboarding window is active (`registry.in_onboard_window`,
   `is_resync_round`).
6. Readers decode onboarding chains only in the Core's slot and in slots they *know* are turret/launcher
   owned. A slot whose owner is still unknown (a latecomer's view of an older builder) is skipped rather
   than guessed, so a builder's standard message can never be misread as a chain.

## Deviations from the plan made during implementation
- The Core takes part in the resync round like every other unit — that is how newborns learn its position.
- `publish()` falls back to one `REMOTE` (absolute) fact automatically when nothing pending lies inside the
  sender's FOV, instead of idling.
- Sentinels carry no `turn` digit (the engine's `rotate()` is Gunner-only).
- The initial Core HP (500) is never announced; the first HP message comes only after a >50 drift.

## Publication rule
Only unpublished facts are offered; a fact is marked published **only** when a write actually carried it
(`publish()` returns exactly those); anything absorbed from the store is marked published on arrival.

## Engine constraints discovered (fcode 2.3.9)
- The bot validator only allows **builtin exception names** in `except` clauses (syntactically) and bans
  `finally`. Hence `CodecError(ValueError)` is caught as `ValueError`, and `absorb`/`publish` catch
  `Exception`. No custom exception may ever appear after `except`.
- Bot modules are loaded from the sources found under the bot's own directory: the module must live (or be
  symlinked) inside each bot that uses it. `print()` output from bots is not shown by `fcode run`.
- `rotate()` is Gunner-only and accepts any compass direction; our gunners keep to one step per round so
  `turn(3)` stays complete.
- `get_nearby_tiles()` occlusion is irrelevant: FOV indices always name the full geometric disc.

## Usage
```python
from utils.GCS.Base.gcs import GCS
from utils.GCS.Base.messages import Fact
from utils.GCS.Base.protocol import STATE_CODE

class Player:
    def __init__(self):
        self.gcs = None

    def run(self, ct):
        if self.gcs is None:
            kind = ct.get_entity_type().value     # "core" / "builder_bot" / "gunner" / ...
            self.gcs = GCS(kind)
        result = self.gcs.absorb(ct)              # facts + control events + deaths + core_hp
        # ... observe: self.gcs.map.apply_fact(Fact(x, y, STATE_CODE["WALL"]), from_gcs=False)
        # ... Core on spawn: self.gcs.core_announce_assign(self.gcs.registry.pick_builder_slot())
        # ... act / move ...
        self.gcs.publish(ct)                      # call LAST, after moving
```
`bots/gcsprobe/main.py` is a complete working example.

## Verifying visually
```
.venv/bin/fcode run gcsprobe starter maps/frostgate.map26 --seed 3 --replay probe.replay26
.venv/bin/python tools/gcs_viz.py probe.replay26 store-scope.html    # open in a browser
.venv/bin/python tools/gcs_viz.py probe.replay26 --report            # tallies per unit
```
The viewer shows engine truth (unit positions, map) with the chosen unit's picture overlaid: its
dead-reckoned positions of teammates (green ring = exact, rose = off), tiles it learned through the store
(rose if they contradict the real map), and the 16 slots as that unit decodes them each round.

## Known limitations / TODO for other modules
- `interfaces.DictMapSource` is a stand-in for the internal map; `has_conveyor_issue`, `has_harvester_issue`
  and `on_directive` are stubs returning nothing.
- A builder sharing a slot (`period > 1`) that moves more than once between writes drifts in readers'
  reckoning until the next resync round.
- Enemy-builder movement inference (the TODO above) is not implemented; enemy bots are plain tile states.
- `SYMMETRY` is delivered as a control event; applying it to derive the enemy Core and mirror facts is the
  internal map's job.
