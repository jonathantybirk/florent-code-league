"""GCS end-to-end probe bot.

Exercises the GCS module inside a real match: the Core spawns builders and
announces their slots through the store; builders wander, record the walls
and ore they see, and publish them; every unit absorbs each round.

Every unit prints one `GCSTRACE {...}` JSON line per round (prints are kept
verbatim in the .replay26).  tools/gcs_viz.py turns a replay into a
side-by-side visualisation of the game and the store.

Not a competitive bot: it exists for verification of the GCS module.
`utils` is a symlink to ../utils (the engine only loads code found inside the
bot's own directory).
"""

import json
import random

from fcode import Direction, EntityType, Environment

from utils.GCS.Base.gcs import GCS
from utils.internal_map.Base.internal_map import InternalMap

CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
MAX_BUILDERS = 3
STOP_ROUND = 300            # resign here: enough rounds for the visualiser


class Player:
    def __init__(self):
        self.gcs: GCS | None = None
        self.num_spawned = 0
        self._dumped: dict = {}          # last traced map state per tile

    def run(self, ct):
        kind = ct.get_entity_type().value
        if kind not in ("core", "builder_bot", "gunner", "sentinel", "launcher"):
            return
        if self.gcs is None:
            self.gcs = GCS(kind, InternalMap(ct.get_map_width(), ct.get_map_height()))

        result = self.gcs.absorb(ct)
        self.gcs.map.observe(ct)
        if kind == "core":
            self._core(ct)
        elif kind == "builder_bot":
            self._builder(ct)
        written_before = self.gcs.last_written
        self.gcs.publish(ct)
        self._trace(ct, kind, result, written_before)

        if kind == "core" and ct.get_current_round() == STOP_ROUND:
            ct.resign("probe finished")

    def _core(self, ct):
        reg = self.gcs.registry
        r = ct.get_current_round()
        if (self.num_spawned >= MAX_BUILDERS or reg.in_onboard_window(r)
                or reg.is_resync_round(r)):
            return
        if ct.get_global_resources() < ct.get_builder_bot_cost():
            return
        pos = ct.get_position()
        for d in CARDINALS:
            spawn_pos = pos.add(d)
            if ct.can_spawn(spawn_pos):
                slot = reg.pick_builder_slot()
                if slot is None:
                    return
                ct.spawn_builder(spawn_pos)
                self.num_spawned += 1
                self.gcs.core_announce_assign(slot)
                return

    def _builder(self, ct):
        if ct.get_move_cooldown() != 0:
            return
        dirs = list(CARDINALS)
        random.shuffle(dirs)
        for d in dirs:
            if ct.can_move(d):
                ct.move(d)
                return

    def _map_delta(self):
        """Tiles whose (state, source, round) changed since last trace —
        the viewer rebuilds the unit's whole internal map from these."""
        out = []
        for (x, y), t in self.gcs.map.tiles.items():
            rec = (t.state, t.source[0], t.round)
            if self._dumped.get((x, y)) != rec:
                self._dumped[(x, y)] = rec
                out.append([x, y, t.state, t.source[0], t.round])
        return out

    def _trace(self, ct, kind, result, written_before):
        reg = self.gcs.registry
        pos = ct.get_position()
        wrote = self.gcs.last_written if self.gcs.last_written != written_before else None
        line = {
            "r": ct.get_current_round(), "id": ct.get_id(), "kind": kind,
            "slot": self.gcs.slot, "pos": [pos.x, pos.y],
            "wrote": wrote,
            "store": [ct.read_store(i) for i in range(16)],
            "owners": {s: [o.kind, list(o.pos) if o.pos else None, o.has_written]
                       for s, o in reg.owners.items()},
            "slots": {s: d for s, d in result.per_slot.items()},
            "learned": [[f.x, f.y, f.state] for f in result.facts],
            "known": len(self.gcs.map.tiles),
            "map_delta": self._map_delta(),
            "symmetry": self.gcs.map.symmetry(),
            "enemy_core": self.gcs.map.enemy_core(),
            "resync": reg.resync_write_round, "onboard_until": reg.onboard_until,
            "core_hp": reg.core_hp,
        }
        print("GCSTRACE " + json.dumps(line, separators=(",", ":")))
