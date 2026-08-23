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

import random

from fcode import Direction, EntityType, Environment

from utils.GCS.Base.gcs import GCS
from utils.GCS.Base.trace import Tracer
from utils.internal_map.Base.internal_map import InternalMap

CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
MAX_BUILDERS = 3
STOP_ROUND = 300            # resign here: enough rounds for the visualiser


class Player:
    def __init__(self):
        self.gcs: GCS | None = None
        self.num_spawned = 0
        self.tracer = Tracer()

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
        self.tracer.emit(ct, self.gcs, result, written_before)

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
