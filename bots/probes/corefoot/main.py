"""How many tiles does the CORE occupy?  The one fact that decides whether the enemy Core is free.

Terrain on all 15 pool maps is exactly symmetric under x -> W-1-x (0 mismatches), but the two Core
positions reflect under x -> W-2-x.  Those disagree by one tile.  A 2x2 Core reported by its
north-west corner explains it exactly: the mirror of the BLOCK [x, x+1] is [W-2-x, W-1-x], whose
north-west corner is W-2-x.  If that is what is happening, the enemy Core is derivable at round 0
for zero bits of communication -- and the two slots every bot in this repo spends broadcasting it
are free again.

Report: our own id, our reported position, and get_tile_building_id() over the 3x3 around it.
"""

from fcode import Controller, EntityType, Position


class Player:
    def __init__(self):
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            pass

    def _run(self, ct):
        if self.done or ct.get_entity_type() != EntityType.CORE:
            return
        if ct.get_current_round() < 1:
            return
        self.done = True
        me = ct.get_id()
        p = ct.get_position()
        w, h = ct.get_map_width(), ct.get_map_height()
        rows = []
        for dy in (-1, 0, 1, 2):
            cells = []
            for dx in (-1, 0, 1, 2):
                q = Position(p.x + dx, p.y + dy)
                try:
                    b = ct.get_tile_building_id(q)
                except Exception as exc:
                    cells.append("!" + type(exc).__name__[:2])
                    continue
                cells.append("CORE" if b == me else ("b%s" % b if b else "."))
            rows.append(",".join(cells))
        # how many tiles in vision report our core id?
        n = 0
        for q in ct.get_nearby_tiles():
            try:
                if ct.get_tile_building_id(q) == me:
                    n += 1
            except Exception:
                pass
        ct.resign("pos=(%d,%d) dims=%dx%d TILES_WITH_CORE_ID=%d | grid(dx,dy from -1..2): %s" % (
            p.x, p.y, w, h, n, " / ".join(rows)))
