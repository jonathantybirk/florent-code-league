"""The leftovers of the API sweep: Core vision, unit/building set membership, and build() return values.

  X1  Is the CORE's vision also a raw disc?  len(get_nearby_tiles()) from the Core versus the exact
      count of in-bounds tiles with d^2 <= 36 measured from every Core footprint tile.
  X2  get_nearby_entities vs get_nearby_units vs get_nearby_buildings.  The docs say "the Core and
      turrets are both a unit and a building" -- so a Gunner id should appear in BOTH lists, a
      Barrier only in buildings, a Builder Bot only in units.  Measured, not assumed.
  X3  get_unit_count() with only the Core alive, and after a builder and a turret exist.
  X4  build_* return values.  robot-api.txt's table says build_conveyor/build_barrier return None;
      the type stub says `-> int`.  One of them is wrong; this reads the value.
  X5  get_vision_radius_sq() per entity type, read from the Core against our own ids.
  X6  Does get_nearby_tiles(dist_sq) accept a value below the vision radius, and is it exact?

The CORE is the reporting unit; the builder relays nothing, so everything measured here is measured
from the Core except X4, which the builder must do.  X4 is relayed through store slot 6
(0 = never ran, 1 = returned None, 2 = returned a non-None int).

Arena `scal`.  Reported through ct.resign() (G29), under the 500-char cap (M06).
"""

from fcode import Controller, Direction, EntityType, GameError, Position

SPAWN = Position(3, 9)
GUN = Position(4, 9)     # EAST of the spawn tile
BAR = Position(3, 8)     # NORTH of the spawn tile


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
        r = ct.get_current_round()

        if et == EntityType.BUILDER_BOT:
            # X4: capture what build_* actually returns, and relay it.
            if self.ph == 0:
                self.ph = 1
                v = ct.build_barrier(BAR)
                ct.write_store(6, 1 if v is None else (2 if isinstance(v, int) else 3))
                ct.write_store(7, 0 if v is None else min(4000000000, int(v)))
            elif self.ph == 1:
                self.ph = 2
                ct.build_gunner(GUN, Direction.NORTH)
            return

        if et != EntityType.CORE or self.done:
            return

        if r == 0:
            self.n.append("X3 solo=%d" % ct.get_unit_count())
            p = ct.get_position()
            vr = ct.get_vision_radius_sq()
            w, h = ct.get_map_width(), ct.get_map_height()
            foot = [Position(p.x + dx, p.y + dy) for dx in (0, 1) for dy in (0, 1)]
            disc = 0
            for y in range(h):
                for x in range(w):
                    if any((x - f.x) ** 2 + (y - f.y) ** 2 <= vr for f in foot):
                        disc += 1
            self.n.append("X1 vr=%d n=%d disc4=%d" % (vr, len(ct.get_nearby_tiles()), disc))
            self.n.append("X6 n8=%d" % len(ct.get_nearby_tiles(8)))
            if ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
            return

        if r >= 6:
            ents = set(ct.get_nearby_entities())
            units = set(ct.get_nearby_units())
            blds = set(ct.get_nearby_buildings())
            kinds = {}
            for i in ents:
                kinds[str(ct.get_entity_type(i))[11:14]] = i
            rows = []
            for k in sorted(kinds):
                i = kinds[k]
                rows.append("%s%d%d" % (k[:3], i in units, i in blds))
            self.n.append("X2 " + ",".join(rows))
            self.n.append("X2n e=%d u=%d b=%d" % (len(ents), len(units), len(blds)))
            self.n.append("X3 now=%d" % ct.get_unit_count())
            vrs = []
            for k in sorted(kinds):
                vrs.append("%s%s" % (k[:3], self.vr(ct, kinds[k])))
            self.n.append("X5 " + ",".join(vrs))
            self.n.append("X4 kind=%d id=%d" % (ct.read_store(6), ct.read_store(7)))
            self.done = True
            ct.resign("MISC|" + "|".join(self.n))

    def vr(self, ct, i):
        """Vision radius, or 'GE' -- barriers and conveyors have none and raise."""
        try:
            return ct.get_vision_radius_sq(i)
        except GameError:
            return "GE"
