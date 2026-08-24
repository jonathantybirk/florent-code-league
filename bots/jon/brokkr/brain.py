"""Per-unit sensing: the InternalMap, the Terrain the pathfinder walks, and
the handful of derived facts every role needs.

One Brain lives on each unit's Player instance for the whole match, so the
map it accumulates is that unit's memory. Nothing here decides anything; it
answers "what is where" so core.py / builder.py / turret.py can decide.

The one judgement call is what counts as `blocked`. The InternalMap already
knows (walls, barriers, harvesters, turrets, cores block; conveyors and
splitters do not), with two corrections applied here:

  * a tile we have never seen is treated as walkable. The mining spec calls
    this the optimistic policy -- unrevealed tiles are provisionally
    traversable until disproved -- and it is what lets a Builder commit to a
    route across ground nobody has looked at yet.
  * `OUR_BOT_ON_CONVEYOR_*` reads as passable through InternalMap.is_passable
    (the name contains CONVEYOR), but a Builder is standing there. Bots block
    bots, so those tiles are re-blocked.
"""

import atlas
from utils.GCS.Base.interfaces import Fact
from utils.GCS.Base.protocol import STATE_CODE
from utils.internal_map.Base.internal_map import InternalMap
from utils.pathfinding import Terrain

from fcode import Direction, EntityType

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
DELTA = {Direction.NORTH: (0, -1), Direction.EAST: (1, 0),
         Direction.SOUTH: (0, 1), Direction.WEST: (-1, 0)}
# Which cardinal steps from a to b; used to face a conveyor at its successor.
STEP_DIR = {(0, -1): Direction.NORTH, (1, 0): Direction.EAST,
            (0, 1): Direction.SOUTH, (-1, 0): Direction.WEST}

TURRET_TYPES = (EntityType.GUNNER, EntityType.SENTINEL, EntityType.LAUNCHER)

# Rounds a unit sighting is treated as still true. Bots move every round, so
# this is short; the point is only to avoid walking into one we can see.
UNIT_MEMORY = 2
_OVERLAY_NAMES = ("TOOK_FIRE_HERE", "CONVEYOR_ISSUE", "HARVESTER_ISSUE")


class Brain:
    """What this unit knows. Rebuilt lazily once per round."""

    def __init__(self) -> None:
        self.imap: InternalMap | None = None
        self.round = -1
        self.terrain: Terrain | None = None
        self.me: tuple[int, int] = (0, 0)
        self.team = None
        self.etype = None
        self.width = 0
        self.height = 0
        # Roles and jobs persist between rounds; see builder.py.
        self.index: int | None = None      # spawn order, assigned by the Core
        self.job = None
        self.first_round: int | None = None
        self.stuck = 0                     # turns since we got closer to the goal
        # Deposits this unit has proved it cannot reach from where it keeps
        # ending up. Per-unit, not shared: a lane unreachable for a Builder
        # stranded in the enemy half is perfectly reachable for one at home.
        self.blacklist: set[tuple[int, int]] = set()
        self.frozen = 0           # consecutive turns that failed to move
        self.harass_target: tuple[int, int] | None = None
        self.station: tuple[int, int] | None = None   # relay tile we committed to
        self.map_name: str | None = None   # set once the atlas recognises it
        self.atlas_done = False

    # ------------------------------------------------------------------
    def sense(self, ct) -> None:
        """Refresh everything this unit can see. Cheap to call twice."""
        rnd = ct.get_current_round()
        if rnd == self.round and self.terrain is not None:
            return
        self.round = rnd
        if self.imap is None:
            self.width, self.height = ct.get_map_width(), ct.get_map_height()
            self.team = ct.get_team()
            self.etype = ct.get_entity_type()
            self.imap = InternalMap(self.width, self.height, self.team)
            self.first_round = rnd
        pos = ct.get_position()
        self.me = (pos.x, pos.y)
        self.imap.observe(ct)
        self._consult_atlas()
        self.terrain = self._terrain(ct)

    def _consult_atlas(self) -> None:
        """Recognise the pool map, once, and adopt what it knows.

        Inert in the fair build, where atlas.MAPS is empty.
        """
        if self.atlas_done or not atlas.available():
            return
        name = atlas.identify(self)
        if name is None:
            # Give up once the map is well explored and still unrecognised:
            # re-checking every round for the rest of a match on an unseen map
            # is pure CPU.
            if len(self.imap.tiles) > 0.6 * self.width * self.height:
                self.atlas_done = True
            return
        self.map_name = name
        self.atlas_done = True
        added = atlas.teach(self, name)
        import debug
        debug.log(f"r{self.round} ATLAS recognised {name}, +{added} deposits")

    # ------------------------------------------------------------------
    def _terrain(self, ct) -> Terrain:
        imap = self.imap
        blocked: set[tuple[int, int]] = set()
        launcher_hazards: set[tuple[int, int]] = set()
        friendly_launchers: list[tuple[int, int]] = []
        for key in imap.tiles:
            if self._solid(key):
                blocked.add(key)
            building = imap.building_at(*key)
            if building is None:
                continue
            name = _STATE_NAME[building]
            if name == "OUR_LAUNCHER":
                friendly_launchers.append(key)
            elif name == "ENEMY_LAUNCHER":
                launcher_hazards |= _ring(key, self.width, self.height)
        # Our own tile is never an obstacle to ourselves; travel() also exempts
        # the source, but other callers read `blocked` directly.
        blocked.discard(self.me)
        return Terrain(self.width, self.height, blocked=blocked,
                       threat=self._threat(),
                       launcher_hazards=launcher_hazards,
                       friendly_launchers=tuple(friendly_launchers))

    def _solid(self, key) -> bool:
        """Whether a Builder is stopped by this tile.

        Deliberately not InternalMap.is_passable, for one reason: that treats
        any recorded unit as blocking, and unit records do not expire. A
        Builder seen once on a tile keeps that tile blocked for the rest of
        the match even after it has walked away, so routes bend around ghosts
        and the map slowly fills with obstacles that are not there.

        Terrain and buildings are stable enough to trust at any age; a unit
        sighting is only worth believing while it is fresh.
        """
        imap = self.imap
        terrain = imap.terrain_at(*key)
        if terrain is not None and _STATE_NAME[terrain] == "WALL":
            return True
        building = imap.building_at(*key)
        if building is not None:
            name = _STATE_NAME[building]
            if name != "EMPTY" and not ("CONVEYOR" in name or "SPLITTER" in name
                                        or name in _OVERLAY_NAMES):
                return True
        unit = imap.unit_at(*key)
        if unit is not None and _STATE_NAME[unit] != "EMPTY":
            age = imap.age(*key)
            if age is not None and age <= UNIT_MEMORY:
                return True
        return False

    def _threat(self) -> set[tuple[int, int]]:
        """Tiles on a known enemy turret's firing line.

        A Gunner's ray stops at the first targetable tile and is blocked by
        walls; a Sentinel's is not blocked by anything. We trace both to the
        edge of their range and let the Gunner's ray stop on a wall only --
        stopping it on a unit would make the threat set depend on where our
        own bots happen to be standing this round, which flickers.
        """
        out: set[tuple[int, int]] = set()
        imap = self.imap
        for key in imap.tiles:
            building = imap.building_at(*key)
            if building is None:
                continue
            name = _STATE_NAME[building]
            if not name.startswith("ENEMY_"):
                continue
            if name.startswith("ENEMY_GUNNER_"):
                reach, pierces = 3, False       # r^2 = 13 -> 3 tiles of ray
            elif name.startswith("ENEMY_SENTINEL_"):
                reach, pierces = 5, True        # r^2 = 32 -> 5 tiles
            else:
                continue
            facing = name.rsplit("_", 1)[1]
            delta = _FACING_DELTA.get(facing)
            if delta is None:
                continue
            x, y = key
            for _ in range(reach):
                x, y = x + delta[0], y + delta[1]
                if not (0 <= x < self.width and 0 <= y < self.height):
                    break
                if not pierces and imap.is_passable(x, y) is False:
                    break
                out.add((x, y))
        return out

    # ------------------------------------------------------------------
    # derived facts
    # ------------------------------------------------------------------
    def core_tiles(self) -> set[tuple[int, int]]:
        """The four tiles of our Core, expanded from its 2x2 anchor."""
        anchor = self.imap.our_core if self.imap else None
        return _block(anchor)

    def sync_symmetry(self, ct, store) -> None:
        """Trade the map's symmetry with the rest of the team.

        Whoever works it out first tells everyone. That is almost never the
        Core: symmetry is inferred from tiles whose mirror image has also been
        observed, and a Core sits still in its own corner looking at ground
        whose mirror is on the far side of the map, so it can hold vision for
        a thousand rounds and never see a single supporting pair. It is the
        Builders who walk far enough to close one.

        The Core is the unit that needs the answer most, because knowing the
        symmetry is what gives it the enemy Core's position -- mirrored from
        our own -- and therefore whether there is anything to attack at all.
        Without this exchange the siege never opened on any map.
        """
        mine = self.imap.symmetry()
        shared = store.symmetry(ct)
        if mine is None and shared is not None:
            self.imap.set_symmetry(shared)
        # Our own Core's anchor travels with the symmetry: a turret is born
        # blind and may never see home, and without it it cannot mirror
        # anything.
        anchor = self.imap.our_core
        if anchor is None:
            told = store.home_anchor(ct)
            if told is not None:
                self.imap.note_core_block(told, ours=True)
        elif mine is not None and (shared != mine
                                   or store.home_anchor(ct) != anchor):
            store.publish_symmetry(ct, mine, anchor)

    def learn_ore(self, tiles) -> None:
        """Record deposits a teammate reported.

        InternalMap.apply_fact is the module's own route for a fact that
        arrived over the store, and it already does the right thing with it:
        our own fresh eyes beat a teammate's report, and the fact is marked
        published on arrival because the whole team has it. Feeding the
        bulletin in here rather than keeping a second list means every
        downstream query -- free_ore, is_passable, the route ban set --
        sees a shared deposit exactly as it sees one we found ourselves.
        """
        code = STATE_CODE["ORE"]
        added = 0
        for x, y in tiles:
            if not (0 <= x < self.width and 0 <= y < self.height):
                continue
            if self.imap.state_at(x, y) is None:
                self.imap.apply_fact(Fact(x, y, code), from_gcs=True)
                added += 1
        return added

    def learn_walls(self, tiles) -> None:
        """Record wall terrain from the atlas. Terrain never goes stale, so
        these are one-time facts like anything else observed."""
        code = STATE_CODE["WALL"]
        for x, y in tiles:
            if self.imap.state_at(x, y) is None:
                self.imap.apply_fact(Fact(x, y, code), from_gcs=True)

    def unreported_ore(self, reported) -> tuple[int, int] | None:
        """A deposit we know and the bulletin does not, nearest first."""
        known = set(reported)
        mine = [tile for tile in self.free_ore() if tile not in known]
        if not mine:
            return None
        return min(mine, key=lambda t: abs(t[0] - self.me[0]) + abs(t[1] - self.me[1]))

    def free_ore(self) -> list[tuple[int, int]]:
        """Known ore tiles with nothing built on them.

        Terrain and buildings are separate layers now, so "is ore" and "is
        free" are two questions rather than one state code.
        """
        imap = self.imap
        out = []
        for key in imap.tiles:
            if _name_or_none(imap.terrain_at(*key)) != "ORE":
                continue
            building = imap.building_at(*key)
            if building is None or _STATE_NAME[building] == "EMPTY":
                out.append(key)
        return out

    def is_free_ore(self, tile) -> bool:
        """Ore terrain with nothing standing on it.

        Terrain and buildings are separate layers, so a free deposit reads as
        terrain ORE *and* building EMPTY -- asking the building layer alone
        answers "EMPTY", which is not the same question.
        """
        if _name_or_none(self.imap.terrain_at(*tile)) != "ORE":
            return False
        building = self.imap.building_at(*tile)
        return building is None or _STATE_NAME[building] == "EMPTY"

    def our_launchers(self) -> list[tuple[int, int]]:
        return [key for key in self.imap.tiles
                if _name_or_none(self.imap.building_at(*key)) == "OUR_LAUNCHER"]

    def our_harvesters(self) -> list[tuple[int, int]]:
        return [key for key in self.imap.tiles
                if _name_or_none(self.imap.building_at(*key)) == "OUR_HARVESTER"]

    def our_conveyors(self) -> set[tuple[int, int]]:
        return {key for key in self.imap.tiles
                if (_name_or_none(self.imap.building_at(*key)) or "")
                .startswith(("OUR_CONVEYOR", "OUR_SPLITTER"))}


def _block(anchor) -> set[tuple[int, int]]:
    """The 2x2 footprint of a Core given its anchor, or nothing."""
    if anchor is None:
        return set()
    x, y = anchor
    return {(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)}


def _ring(centre, width, height) -> set[tuple[int, int]]:
    """The eight tiles around `centre` -- an enemy Launcher's pickup radius."""
    x, y = centre
    return {(x + dx, y + dy)
            for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            if (dx or dy) and 0 <= x + dx < width and 0 <= y + dy < height}


_FACING_DELTA = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0),
                 "NE": (1, -1), "NW": (-1, -1), "SE": (1, 1), "SW": (-1, 1)}

# Imported here rather than at module scope in internal_map's namespace so the
# name lookup in the hot loops above is a plain tuple index.
from utils.GCS.Base.protocol import TILE_STATES as _STATE_NAME  # noqa: E402


def _name_or_none(state):
    return None if state is None else _STATE_NAME[state]
