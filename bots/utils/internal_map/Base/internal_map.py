"""Per-unit internal map: everything a unit knows about the board.

Every unit keeps one InternalMap.  It has exactly two inputs — the unit's own
eyesight (`observe(ct)`) and facts absorbed from the Global Communication
Store (`apply_fact(fact, from_gcs=True)`) — and it fulfils the GCS module's
`MapSource` contract, so a unit's GCS publishes straight out of it.

Per tile it records the state (a code from the GCS tile-state alphabet), the
round the information dates from (its age), how it was obtained, and whether
it has been published to the store.

Terms
-----
state        an integer code from bots.utils.GCS.Base.protocol.TILE_STATES,
             e.g. WALL, ORE_FREE, OUR_CONVEYOR_E, ENEMY_GUNNER_N.
source       SEEN (own eyes) / GCS (a teammate told us) / INFERRED (derived
             from the map's symmetry).
negative     a fact that something is *gone*: a tile we recorded as occupied
             is seen empty.  Negatives are real facts and get published.
symmetry     maps come in three mirror kinds (left-right, top-bottom,
             180° rotation).  Once known, every terrain tile implies its twin
             and the enemy Core's position follows from our own.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...GCS.Base.interfaces import state_weight
from ...GCS.Base.messages import Fact
from ...GCS.Base.protocol import STATE_CODE, SYMMETRY_KINDS, TILE_STATES

SEEN, GCS, INFERRED = "seen", "gcs", "inferred"

EMPTY = STATE_CODE["EMPTY"]
WALL = STATE_CODE["WALL"]
ORE_FREE = STATE_CODE["ORE_FREE"]
TOOK_FIRE_HERE = STATE_CODE["TOOK_FIRE_HERE"]
_OUR_CORE = STATE_CODE["OUR_CORE"]
TERRAIN = frozenset({EMPTY, WALL, ORE_FREE})
# terrain never changes, so a terrain fact never goes stale; everything else
# (units, buildings) ages and is eventually worth re-checking
STATIC = frozenset({WALL, ORE_FREE})

_EIGHT = ("NORTH", "NORTHEAST", "EAST", "SOUTHEAST", "SOUTH", "SOUTHWEST", "WEST", "NORTHWEST")
_EIGHT_SHORT = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
_CARDINAL_SHORT = {"NORTH": "N", "EAST": "E", "SOUTH": "S", "WEST": "W"}

# how many rounds a non-terrain observation stays "fresh" for priority purposes
FRESH_ROUNDS = 30
# minimum observed tile pairs that must agree before a symmetry is trusted
SYMMETRY_MIN_EVIDENCE = 6


@dataclass
class TileInfo:
    state: int
    round: int          # round the information dates from
    source: str         # SEEN / GCS / INFERRED
    published: bool     # already on the store (ours or a teammate's write)


class InternalMap:
    """Fulfils the GCS `MapSource` contract; see bots/utils/GCS/Base/interfaces.py."""

    def __init__(self, map_w: int, map_h: int, team=None):
        self.w, self.h = map_w, map_h
        self.team = team
        self.tiles: dict[tuple[int, int], TileInfo] = {}
        self.round = 0
        self.our_core: tuple[int, int] | None = None      # 2x2 block anchor
        self._symmetry: int | None = None
        self._sym_alive = set(range(len(SYMMETRY_KINDS)))  # candidates not yet contradicted
        self._last_hp: int | None = None

    # ------------------------------------------------------------------
    # input 1: own eyesight
    # ------------------------------------------------------------------
    def observe(self, ct) -> list[Fact]:
        """Scan everything in vision and record it.  Returns the facts that
        are new or changed (already recorded in the map; returned for
        callers that want to react)."""
        self.round = ct.get_current_round()
        if self.team is None:
            self.team = ct.get_team()
        me = ct.get_position()
        if ct.get_entity_type().value == "core":
            self.our_core = (me.x, me.y)

        changed: list[Fact] = []
        occupied: dict[tuple[int, int], int] = {}
        my_id = ct.get_id()
        for eid in ct.get_nearby_entities():
            if eid == my_id:
                continue                # teammates track us by dead reckoning
            state = self._entity_state(ct, eid)
            if state is None:
                continue
            p = ct.get_position(eid)
            key = (p.x, p.y)
            # a builder standing on a conveyor: merge into the combo state
            if key in occupied:
                state = self._combine(occupied[key], state)
            occupied[key] = state

        for tile in ct.get_nearby_tiles():
            key = (tile.x, tile.y)
            if key in occupied:
                state = occupied[key]
            else:
                env = ct.get_tile_env(tile).value
                state = WALL if env == "wall" else ORE_FREE if env == "ore_titanium" else EMPTY
            if self._record(key, state, SEEN):
                changed.append(Fact(key[0], key[1], state))

        self._note_fire(ct, me)
        self._infer_symmetry()
        return changed

    def _entity_state(self, ct, eid) -> int | None:
        etype = ct.get_entity_type(eid).value
        ours = ct.get_team(eid) == self.team
        prefix = "OUR_" if ours else "ENEMY_"
        if etype == "builder_bot":
            name = prefix + "BUILDER_BOT"
        elif etype in ("conveyor", "splitter"):
            d = ct.get_direction(eid).name
            name = f"{prefix}{etype.upper()}_{_CARDINAL_SHORT.get(d, 'N')}"
        elif etype in ("gunner", "sentinel"):
            d = ct.get_direction(eid).name
            name = f"{prefix}{etype.upper()}_{_EIGHT_SHORT[_EIGHT.index(d)]}"
        elif etype in ("harvester", "barrier", "launcher", "core"):
            name = prefix + etype.upper()
        else:
            return None
        return STATE_CODE.get(name)

    @staticmethod
    def _combine(a: int, b: int) -> int:
        """Builder on a conveyor → the combo code; otherwise keep the building."""
        na, nb = TILE_STATES[a], TILE_STATES[b]
        bot, conv = (na, nb) if na.endswith("BUILDER_BOT") else (nb, na)
        if bot.endswith("BUILDER_BOT") and "_CONVEYOR_" in conv:
            team = "OUR_" if bot.startswith("OUR_") else "ENEMY_"
            return STATE_CODE[f"{team}BOT_ON_CONVEYOR_{conv[-1]}"]
        return a if not na.endswith("BUILDER_BOT") else b

    def _note_fire(self, ct, me) -> None:
        """HP dropped with no enemy turret in sight: mark our tile as under
        fire from something unseen (low-priority but shareable)."""
        hp = ct.get_hp()
        if self._last_hp is not None and hp < self._last_hp:
            enemy_turret_visible = any(
                TILE_STATES[t.state].startswith(("ENEMY_GUNNER", "ENEMY_SENTINEL"))
                for t in self.tiles.values() if t.source == SEEN and t.round == self.round)
            if not enemy_turret_visible:
                self._record((me.x, me.y), TOOK_FIRE_HERE, SEEN, overlay=True)
        self._last_hp = hp

    # ------------------------------------------------------------------
    # input 2: the store  (MapSource contract)
    # ------------------------------------------------------------------
    def apply_fact(self, fact: Fact, from_gcs: bool = True) -> None:
        """Record a fact.  A fact that came off the store is already known to
        the whole team, so it is marked published on arrival."""
        overlay = TILE_STATES[fact.state] in ("TOOK_FIRE_HERE", "CONVEYOR_ISSUE", "HARVESTER_ISSUE")
        self._record((fact.x, fact.y), fact.state, GCS if from_gcs else SEEN,
                     overlay=overlay, published=from_gcs)

    def note_shared(self, facts) -> None:
        for f in facts:
            t = self.tiles.get((f.x, f.y))
            if t is not None and t.state == f.state:
                t.published = True

    def pending_facts(self, budget: int) -> list[Fact]:
        """Unpublished facts, best first: class weight × freshness."""
        cands = [(self._score(t), Fact(x, y, t.state))
                 for (x, y), t in self.tiles.items() if not t.published]
        cands.sort(key=lambda pair: -pair[0])
        return [f for _, f in cands[:budget]]

    def known_facts(self) -> list[Fact]:
        return [Fact(x, y, t.state) for (x, y), t in self.tiles.items()]

    def symmetry(self) -> int | None:
        return self._symmetry

    # ------------------------------------------------------------------
    # queries for other modules
    # ------------------------------------------------------------------
    def state_at(self, x: int, y: int) -> int | None:
        t = self.tiles.get((x, y))
        return t.state if t else None

    def age(self, x: int, y: int) -> int | None:
        t = self.tiles.get((x, y))
        return self.round - t.round if t else None

    def is_passable(self, x: int, y: int) -> bool | None:
        """True/False if known, None if the tile has never been seen.  Walls,
        barriers, harvesters, turrets, cores and builders block movement;
        conveyors and splitters do not."""
        t = self.tiles.get((x, y))
        if t is None:
            return None
        name = TILE_STATES[t.state]
        if name in ("EMPTY", "ORE_FREE", "TOOK_FIRE_HERE") or "CONVEYOR" in name or "SPLITTER" in name:
            return True
        return False

    def enemy_core(self) -> tuple[int, int] | None:
        """Anchor of the enemy Core's 2x2 block: seen directly, else derived
        from our Core and the symmetry once known."""
        for (x, y), t in self.tiles.items():
            if TILE_STATES[t.state] == "ENEMY_CORE":
                return (x, y)
        if self._symmetry is None or self.our_core is None:
            return None
        return self._mirror_block(self.our_core)

    def set_symmetry(self, kind: int) -> None:
        """Accept a SYMMETRY control event from the Core."""
        self._symmetry = kind
        self._mirror_all()

    # ------------------------------------------------------------------
    # symmetry
    # ------------------------------------------------------------------
    def _mirror(self, x: int, y: int, kind: int | None = None) -> tuple[int, int]:
        kind = self._symmetry if kind is None else kind
        if kind == 0:                       # MIRROR_X: left-right
            return self.w - 1 - x, y
        if kind == 1:                       # MIRROR_Y: top-bottom
            return x, self.h - 1 - y
        return self.w - 1 - x, self.h - 1 - y   # ROT_180

    def _mirror_block(self, anchor: tuple[int, int]) -> tuple[int, int]:
        """Mirror a 2x2 block's top-left anchor (the far corner maps to the
        new top-left, so it is the anchor+1 corner that gets mirrored)."""
        x, y = anchor
        mx, my = self._mirror(x + 1, y + 1)
        if self._symmetry == 0:
            return mx, y
        if self._symmetry == 1:
            return x, my
        return mx, my

    def _infer_symmetry(self) -> None:
        """Eliminate symmetry kinds contradicted by observed terrain; adopt the
        last survivor once enough tile pairs back it."""
        if self._symmetry is not None or not self._sym_alive:
            return
        terrain = {k: t.state for k, t in self.tiles.items()
                   if t.source != INFERRED and t.state in TERRAIN}
        evidence = {k: 0 for k in self._sym_alive}
        for kind in list(self._sym_alive):
            for (x, y), st in terrain.items():
                twin = terrain.get(self._mirror(x, y, kind))
                if twin is None:
                    continue
                if twin != st:
                    self._sym_alive.discard(kind)
                    break
                evidence[kind] += 1
        if len(self._sym_alive) == 1:
            kind = next(iter(self._sym_alive))
            if evidence[kind] >= SYMMETRY_MIN_EVIDENCE:
                self._symmetry = kind
                self._mirror_all()

    def _mirror_all(self) -> None:
        """Every observed terrain tile implies its twin.  Twins are marked
        published: anyone who knows the symmetry can derive them, so they
        are never worth store bandwidth."""
        for (x, y), t in list(self.tiles.items()):
            if t.state in TERRAIN and t.source != INFERRED:
                mx, my = self._mirror(x, y)
                if (mx, my) not in self.tiles:
                    self.tiles[(mx, my)] = TileInfo(t.state, t.round, INFERRED, True)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _record(self, key, state, source, *, overlay=False, published=False) -> bool:
        """Store a fact; returns True if it changed what we knew.

        Newer information wins.  An overlay (fire / issue) does not replace
        the tile's identity unless the tile is unknown.  A fact that merely
        re-confirms the same state refreshes its round but stays published
        (nothing new to tell anyone).
        """
        if not (0 <= key[0] < self.w and 0 <= key[1] < self.h):
            return False
        cur = self.tiles.get(key)
        if overlay and cur is not None and cur.state not in (EMPTY, state):
            cur.round = self.round
            return False
        if cur is not None and cur.state == state:
            cur.round = max(cur.round, self.round)
            if cur.source == INFERRED:
                cur.source, cur.published = source, cur.published or published
            cur.published = cur.published or published
            return False
        if cur is not None and source == GCS and cur.source == SEEN and cur.round >= self.round:
            return False            # our own fresh eyes beat a teammate's report
        if state == EMPTY and cur is None:
            published = True        # "nothing there" on a never-known tile is not news;
                                    # only a negative replacing known content is
        self.tiles[key] = TileInfo(state, self.round, source, published)
        if state == _OUR_CORE:
            self.our_core = key         # the Core's anchor tile, however we learned it
        if self._symmetry is not None and state in TERRAIN and source != INFERRED:
            mx, my = self._mirror(*key)
            if (mx, my) not in self.tiles:
                self.tiles[(mx, my)] = TileInfo(state, self.round, INFERRED, True)
        return True

    def _score(self, t: TileInfo) -> float:
        w = state_weight(t.state)
        if t.state in STATIC:
            return w
        age = self.round - t.round
        return w * max(0.1, 1.0 - age / FRESH_ROUNDS)
