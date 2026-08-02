"""What the API lets us read and do about the ENEMY: observability, passability, occlusion, sabotage.

Four questions in one probe, because all four need a Team A builder standing on Team B's stuff:

  (A) OBSERVABILITY.  Which getters answer for an enemy id, and do the TEAM-GLOBAL getters accept an
      id at all?  get_global_resources(enemy_core), get_scale_percent(id), get_global_ammo(id),
      get_unit_count(id) -- if any answered, the enemy treasury and cost scale would be free.
  (B) ENEMY PASSABILITY.  is_tile_passable / is_tile_empty / can_move against an enemy barrier,
      conveyor, splitter, builder bot and Core footprint -- then actually walk onto the conveyor and
      the splitter to prove it.
  (C) OCCLUSION.  From on top of the enemy splitter, read the two tiles directly behind their barrier.
  (D) SILENT FAILURE.  A builder's attack "only damages the building on the tile".  Firing at a tile
      that holds ONLY an enemy builder bot is the prime silent-failure candidate: does it raise, or
      quietly spend 2 titanium for nothing?

Arena `close` (14x11) against fixture `apifoe`, which plants (6,4) barrier, (6,5) conveyor facing
EAST, (6,6) splitter facing EAST, and parks a builder on (6,7).

Reported through ct.resign() (G29), under the 500-char cap (M06).
"""

from fcode import Controller, Direction, Environment, EntityType, GameError, Position

STANCE = Position(5, 5)
E_BAR = Position(6, 4)
E_CNV = Position(6, 5)
E_SPL = Position(6, 6)
E_BOT = Position(6, 7)
E_COR = Position(8, 5)
BEHIND = (Position(6, 3), Position(6, 2))   # directly behind the enemy barrier from (6,5)/(6,6)


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.ph = 0
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("T:" + type(exc).__name__)

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 5)):
                ct.spawn_builder(Position(3, 5))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return
        r = ct.get_current_round()
        pos = ct.get_position()

        if self.ph == 0:
            if pos != STANCE:
                d = pos.cardinal_direction_to(STANCE)
                if ct.can_move(d):
                    ct.move(d)
                return
            if r < 30:            # let apifoe finish building before measuring
                return
            self.ph = 1
            return

        # (B) enemy passability, read from (5,5).
        if self.ph == 1:
            self.ph = 2
            self.n.append("BAR" + self.row(ct, E_BAR, None))
            self.n.append("CNV" + self.row(ct, E_CNV, Direction.EAST))
            self.n.append("SPL" + self.row(ct, E_SPL, None))
            self.n.append("BOT" + self.row(ct, E_BOT, None))
            self.n.append("COR" + self.row(ct, E_COR, None))
            # (A) getters against real enemy ids of three different kinds.
            cid = ct.get_tile_building_id(E_CNV)
            kid = ct.get_tile_building_id(E_COR)
            uid = ct.get_tile_builder_bot_id(E_BOT)
            self.n.append("ids=%s,%s,%s" % (cid, kid, uid))
            for label, name, arg in (("res", "get_global_resources", kid),
                                     ("amm", "get_global_ammo", kid),
                                     ("scl", "get_scale_percent", kid),
                                     ("cnt", "get_unit_count", kid),
                                     ("vis", "get_vision_radius_sq", uid),
                                     ("vsC", "get_vision_radius_sq", kid),
                                     ("dirC", "get_direction", cid),
                                     ("stC", "get_stored_resource", cid),
                                     ("hpK", "get_hp", kid)):
                self.n.append(label + "=" + self.call(ct, name, arg))
            return

        if self.ph == 2:
            self.ph = 3
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
            return

        if self.ph == 3:
            self.ph = 4
            self.n.append("on%d,%d" % (pos.x, pos.y))
            if ct.can_move(Direction.SOUTH):
                ct.move(Direction.SOUTH)
            return

        # (C) occlusion behind the enemy barrier, and (D) the silent-fire test.
        if self.ph == 4:
            self.ph = 5
            self.n.append("on%d,%d" % (pos.x, pos.y))
            self.n.append("beh=" + "".join(self.look(ct, p) for p in BEHIND))
            hid = ct.get_tile_building_id(BEHIND[0])
            self.n.append("hid=%s inB=%s inE=%s" % (
                hid, hid in ct.get_nearby_buildings(), hid in ct.get_nearby_entities()))
            ti = ct.get_global_resources()
            cf = self.safe(ct.can_fire, E_BOT)
            res = "N"
            try:
                ct.fire(E_BOT)
            except GameError:
                res = "R"
            self.n.append("FIREBOT cf=%s r=%s dTi=%d" % (cf, res, ct.get_global_resources() - ti))
            return

        if self.ph == 5:
            self.done = True
            ct.resign("SPY|" + "|".join(self.n))

    def safe(self, fn, arg):
        try:
            return fn(arg)
        except GameError:
            return "GE"

    def call(self, ct, name, eid):
        fn = getattr(ct, name, None)
        if fn is None:
            return "-"
        try:
            return str(fn(eid))[:9]
        except GameError:
            return "GE"
        except TypeError:
            return "TE"

    def look(self, ct, p):
        try:
            v = "1" if ct.is_in_vision(p) else "0"
        except GameError:
            v = "G"
        try:
            v += {Environment.EMPTY: "e", Environment.WALL: "w",
                  Environment.ORE_TITANIUM: "o"}[ct.get_tile_env(p)]
        except GameError:
            v += "X"
        return v

    def row(self, ct, tile, d):
        out = "="
        for fn in (ct.is_tile_passable, ct.is_tile_empty):
            try:
                out += "1" if fn(tile) else "0"
            except GameError:
                out += "X"
        if d is None:
            out += "-"
        else:
            try:
                out += "1" if ct.can_move(d) else "0"
            except GameError:
                out += "X"
        return out
