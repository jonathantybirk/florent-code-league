"""Portable cross-map check of one claim: is a team's OWN Core passable to its own builder?

fcode's own Controller.is_tile_passable docstring says a tile is passable if it "has no building
on it or has a conveyor, splitter, or the allied core". pt_own and pt_foe both measured the
allied Core as IMPASSABLE on maps/lab/passlab.map26. This probe carries the same measurement to
stock tournament maps so the result cannot be an artefact of one lab arena.

It is map-agnostic: the builder finds its own Core by entity type + team, steps until it is
cardinally adjacent to a Core footprint tile, then takes all three measurements. Run e.g.

    rm -rf bots/probes/pt_core/__pycache__
    .venv/Scripts/python.exe tools/runprobe.py pt_core --map sprint --vs idle

Result goes to resign_message (short enough to survive the 500-char cap) and to a file.
"""

import os

from fcode import Controller, Direction, EntityType, Position

OUT = os.environ.get("PT_CORE_OUT") or (
    "C:/Users/edlun/AppData/Local/Temp/claude/"
    "c--Users-edlun-Desktop-lucky-shots-Hackathons-florent-code-league/"
    "69495691-95ef-4878-adf9-aeca64f3e3b5/scratchpad/pt_core.txt"
)

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


class Player:
    def __init__(self):
        self.spawned = False
        self.gen = None
        self.ct = None
        self.dead = False

    def run(self, ct: Controller) -> None:
        self.ct = ct
        try:
            et = ct.get_entity_type()
        except Exception:
            return
        if et == EntityType.CORE:
            if not self.spawned:
                for d in CARDINALS + (Direction.NORTHEAST, Direction.SOUTHEAST,
                                      Direction.SOUTHWEST, Direction.NORTHWEST):
                    for base in (ct.get_position(), ct.get_position().add(Direction.SOUTHEAST)):
                        p = base.add(d)
                        try:
                            if ct.can_spawn(p):
                                ct.spawn_builder(p)
                                self.spawned = True
                                return
                        except Exception:
                            pass
            return
        if et != EntityType.BUILDER_BOT or self.dead:
            return
        if self.gen is None:
            self.gen = self._script()
        try:
            next(self.gen)
        except StopIteration:
            self.dead = True
        except Exception as exc:
            self._done("FATAL %s: %s" % (type(exc).__name__, str(exc)[:150]))

    def _done(self, msg):
        self.dead = True
        try:
            with open(OUT, "a", encoding="utf-8") as fh:
                fh.write(msg + "\n")
        except Exception:
            pass
        try:
            self.ct.resign(msg[:480])
        except Exception:
            pass

    def _try(self, fn, *args):
        try:
            v = fn(*args)
            if v is None:
                return "None"
            return str(getattr(v, "name", v))
        except Exception as exc:
            return "%s<%s>" % (type(exc).__name__, str(exc)[:60])

    def _my_core_neighbour(self, ct):
        """Return a cardinally adjacent tile holding this team's Core, or None."""
        me = ct.get_position()
        mine = ct.get_team()
        for d in CARDINALS:
            p = me.add(d)
            try:
                bid = ct.get_tile_building_id(p)
            except Exception:
                continue
            if bid is None:
                continue
            try:
                if ct.get_entity_type(bid) == EntityType.CORE and ct.get_team(bid) == mine:
                    return p, d, bid
            except Exception:
                continue
        return None

    def _script(self):
        ct = self.ct
        # Locate our own Core so we can close in if the spawn tile was only diagonally adjacent.
        anchor = None
        for eid in ct.get_nearby_entities():
            try:
                if ct.get_entity_type(eid) == EntityType.CORE and ct.get_team(eid) == ct.get_team():
                    anchor = ct.get_position(eid)
                    break
            except Exception:
                pass

        for _ in range(40):
            hit = self._my_core_neighbour(self.ct)
            if hit is not None:
                break
            ct = self.ct
            if anchor is not None and ct.get_move_cooldown() == 0:
                d = ct.get_position().cardinal_direction_to(anchor)
                if ct.can_move(d):
                    ct.move(d)
                else:
                    for alt in CARDINALS:
                        if ct.can_move(alt):
                            ct.move(alt)
                            break
            yield
        else:
            self._done("pt_core: never became adjacent to own core")
            return

        tile, d, bid = hit
        ct = self.ct
        while ct.get_move_cooldown() != 0:
            yield
            ct = self.ct
        home = ct.get_position()
        msg = ("pt_core OWN_CORE tile=(%d,%d) from=(%d,%d) dir=%s id=%s/%s/%s "
               "passable=%s empty=%s move_cd=%d can_move=%s move()=%s"
               % (tile.x, tile.y, home.x, home.y, d.name, bid,
                  self._try(ct.get_entity_type, bid), self._try(ct.get_team, bid),
                  self._try(ct.is_tile_passable, tile),
                  self._try(ct.is_tile_empty, tile),
                  ct.get_move_cooldown(),
                  self._try(ct.can_move, d),
                  self._try(ct.move, d)))
        yield
        ct = self.ct
        landed = ct.get_position()
        self._done(msg + " pos_next_round=(%d,%d) RELOCATED=%s"
                   % (landed.x, landed.y, landed == tile))
