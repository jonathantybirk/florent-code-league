"""GCS end-to-end probe bot.

Exercises the GCS module inside a real match: the Core spawns builders and
announces their slots through the store; builders wander, record the walls
and ore they see, and publish them; every unit absorbs each round.  A line
starting with [probe] is printed whenever a unit learns a tile it has never
seen with its own eyes — proof the fact travelled through the store.

Not a competitive bot: it only fights for verification step 9 of the GCS plan.
"""

import random


from fcode import Direction, EntityType, Environment, GameError  # noqa: E402

from utils.GCS.Base.gcs import GCS  # noqa: E402
from utils.GCS.Base.messages import Fact  # noqa: E402
from utils.GCS.Base.protocol import STATE_CODE  # noqa: E402

CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
_KIND = {EntityType.CORE: "core", EntityType.BUILDER_BOT: "builder_bot",
         EntityType.GUNNER: "gunner", EntityType.SENTINEL: "sentinel",
         EntityType.LAUNCHER: "launcher"}

MAX_BUILDERS = 3
REPORT_ROUND = 400
_LOG: list[str] = []        # shared by the whole team (one interpreter per team)


class Player:
    def __init__(self):
        self.gcs: GCS | None = None
        self.seen: set[tuple[int, int]] = set()   # tiles this unit saw itself
        self.num_spawned = 0
        self.spawned_ids: dict[int, int] = {}     # slot -> unit id (core only)

    def run(self, ct):
        try:
            self._run(ct)
        except Exception as exc:
            import traceback
            ct.resign("PROBE CRASH: " + traceback.format_exc()[-1500:])

    def _run(self, ct):
        etype = ct.get_entity_type()
        kind = _KIND.get(etype)
        if kind is None:
            return
        if self.gcs is None:
            self.gcs = GCS(kind)
            _LOG.append(f"r={ct.get_current_round()} {kind} id={ct.get_id()} first run")

        before = set(self.gcs.map.tiles)
        result = self.gcs.absorb(ct)
        for f in result.facts:
            if (f.x, f.y) not in self.seen and (f.x, f.y) not in before \
                    and len(_LOG) < 40:
                _LOG.append(f"r={ct.get_current_round()} {kind} slot={self.gcs.slot} "
                            f"learned ({f.x},{f.y})={f.state} via GCS")
        if result.assigned_slot is not None:
            _LOG.append(f"r={ct.get_current_round()} {kind} spawn_round="
                        f"{self.gcs.spawn_round} got slot {result.assigned_slot}")
        if kind == "core" and ct.get_current_round() == REPORT_ROUND:
            reg = self.gcs.registry
            rows = []
            for s, o in reg.owners.items():
                if o.kind != "builder_bot":
                    continue
                uid = self.spawned_ids.get(s)
                try:
                    truth = ct.get_position(uid) if uid is not None else None
                    truth = (truth.x, truth.y) if truth is not None else None
                except GameError:
                    truth = "out of vision"
                verdict = "?" if isinstance(truth, str) else ("OK" if o.pos == truth else "MISMATCH")
                rows.append(f"slot {s}: reckoned={o.pos} truth={truth} {verdict}")
            cx, cy = ct.get_position().x, ct.get_position().y
            far = [xy for xy in self.gcs.map.tiles
                   if (xy[0]-cx)**2 + (xy[1]-cy)**2 > 36]
            ct.resign(f"PROBE REPORT r={REPORT_ROUND}\n" + "\n".join(rows)
                      + f"\nfar tiles learned from builders: {len(far)} e.g. {sorted(far)[:6]}")

        self._observe(ct)
        if kind == "core":
            self._core(ct)
        elif kind == "builder_bot":
            self._builder(ct)
        self.gcs.publish(ct)

    def _observe(self, ct):
        """Feed own eyesight into the map as unpublished facts."""
        for tile in ct.get_nearby_tiles():
            xy = (tile.x, tile.y)
            self.seen.add(xy)
            env = ct.get_tile_env(tile)
            if env == Environment.WALL:
                self.gcs.map.apply_fact(Fact(tile.x, tile.y, STATE_CODE["WALL"]),
                                        from_gcs=False)
            elif env == Environment.ORE_TITANIUM:
                self.gcs.map.apply_fact(Fact(tile.x, tile.y, STATE_CODE["ORE_FREE"]),
                                        from_gcs=False)

    def _core(self, ct):
        reg = self.gcs.registry
        if (self.num_spawned >= MAX_BUILDERS
                or reg.in_onboard_window(ct.get_current_round())
                or reg.is_resync_round(ct.get_current_round())):
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
                new_id = ct.spawn_builder(spawn_pos)
                self.spawned_ids[slot] = new_id
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
