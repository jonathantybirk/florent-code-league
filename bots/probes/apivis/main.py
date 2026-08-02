"""Vision: is it a raw Euclidean disc, or true line of sight blocked by walls and barriers?

docs/game-rules-reference says a Barrier "Blocks LOS: Yes" and a Harvester/Conveyor/Splitter "No".
If vision really is occluded, scouting past a wall is impossible and hiding behind a barrier works.
If it is a raw disc, both of those beliefs are wrong and every "they cannot see us" assumption fails.

Arena `apilos` (maps/lab/mkapi.py): 24x14, Core A anchor (1,6), a solid WALL column at x=8 spanning
y=2..10.  Row y=1 is completely open, which gives a clean barrier-only control on the same map.

  V1  get_vision_radius_sq() for a builder, and len(get_nearby_tiles()) versus the exact count of
      in-bounds tiles with d^2 <= 20.  Equal => raw disc; smaller => occlusion.
  V2  from (6,6): is_in_vision / get_tile_env for (9,6) and (10,6), both strictly BEHIND the wall
      column at x=8 and both inside r^2=20 (d^2 = 9 and 16).
  V3  same two tiles read via get_nearby_tiles() membership.
  V4  on open row y=1: read (9,1) BEFORE building a barrier at (7,1), then AFTER.  Any change is
      barrier occlusion; no change means barriers do not block vision at all.

Reported through ct.resign() (G29); under the 500-char cap (M06).
"""

from fcode import Controller, Direction, Environment, EntityType, GameError, Position

HOME = Position(6, 6)
BEHIND1 = Position(9, 6)     # d^2 = 9 from HOME, one tile past the wall at (8,6)
BEHIND2 = Position(10, 6)    # d^2 = 16 from HOME
ROW1 = Position(6, 1)
BARR = Position(7, 1)
PAST = Position(9, 1)        # d^2 = 9 from ROW1, one tile past the barrier


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
            if not self.spawned and ct.can_spawn(Position(3, 6)):
                ct.spawn_builder(Position(3, 6))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return
        pos = ct.get_position()

        if self.ph == 0:
            if pos != HOME:
                self.step(ct, HOME)
                return
            self.ph = 1
            vr = ct.get_vision_radius_sq()
            tiles = ct.get_nearby_tiles()
            w, h = ct.get_map_width(), ct.get_map_height()
            disc = 0
            for y in range(h):
                for x in range(w):
                    if (x - pos.x) ** 2 + (y - pos.y) ** 2 <= vr:
                        disc += 1
            self.n.append("V1 vr=%d n=%d disc=%d" % (vr, len(tiles), disc))
            s = set((t.x, t.y) for t in tiles)
            self.n.append("V3 in=%d%d" % ((BEHIND1.x, BEHIND1.y) in s,
                                          (BEHIND2.x, BEHIND2.y) in s))
            self.n.append("V2 " + self.look(ct, BEHIND1) + " " + self.look(ct, BEHIND2))
            self.n.append("wall=" + self.look(ct, Position(8, 6)))
            return

        if self.ph == 1:
            if pos != ROW1:
                self.step(ct, ROW1)
                return
            self.ph = 2
            self.n.append("V4pre " + self.look(ct, PAST))
            ct.build_barrier(BARR)
            return

        if self.ph == 2:
            self.ph = 3
            s = set((t.x, t.y) for t in ct.get_nearby_tiles())
            self.n.append("V4post %s in=%d n=%d" % (
                self.look(ct, PAST), (PAST.x, PAST.y) in s, len(s)))
            self.done = True
            ct.resign("VIS|" + "|".join(self.n))

    def step(self, ct, tgt):
        d = ct.get_position().cardinal_direction_to(tgt)
        if ct.can_move(d):
            ct.move(d)
            return
        for alt in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
            if ct.can_move(alt):
                ct.move(alt)
                return

    def look(self, ct, p):
        """<in_vision><env letter>, env letter X when get_tile_env raises."""
        try:
            v = "1" if ct.is_in_vision(p) else "0"
        except GameError:
            v = "G"
        try:
            v += {Environment.EMPTY: "e", Environment.WALL: "w",
                  Environment.ORE_TITANIUM: "o"}[ct.get_tile_env(p)]
        except GameError:
            v += "X"
        return "%d,%d:%s" % (p.x, p.y, v)
