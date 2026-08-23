"""Per-unit internal map: everything a unit knows about the board.

Every unit keeps one InternalMap.  It has exactly two inputs — the unit's own
eyesight (`observe(ct)`) and facts absorbed from the Global Communication
Store (`apply_fact(fact, from_gcs=True)`) — and it fulfils the GCS module's
`MapSource` contract, so a unit's GCS publishes straight out of it.

Every tile has two layers, each with its own record:

    terrain   what the ground is: EMPTY / WALL / ORE.  Terrain never changes,
              so once a unit knows a tile has ore, nothing built on top of it
              ever erases that knowledge.
    occupant  a building or unit standing on the terrain (the OUR_/ENEMY_
              codes), or nothing.  This layer ages and can be cleared by a
              negative (an EMPTY fact: "nothing stands here any more").

A tile with ore and a harvester on it is two facts: ORE and OUR_HARVESTER.

Per record it keeps the state code (from the GCS tile-state alphabet), the
round the information dates from (its age), how it was obtained, and whether
it has been published to the store.

Terms
-----
state        an integer code from bots.utils.GCS.Base.protocol.TILE_STATES.
source       SEEN (own eyes) / GCS (a teammate told us) / INFERRED (derived
             from the map's symmetry).
negative     an EMPTY fact on a tile whose occupant we knew: it is gone.
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
ORE = STATE_CODE["ORE"]
TOOK_FIRE_HERE = STATE_CODE["TOOK_FIRE_HERE"]
OUR_CORE, ENEMY_CORE = STATE_CODE["OUR_CORE"], STATE_CODE["ENEMY_CORE"]
TERRAIN = frozenset({EMPTY, WALL, ORE})
OVERLAYS = frozenset(STATE_CODE[n] for n in ("TOOK_FIRE_HERE", "CONVEYOR_ISSUE", "HARVESTER_ISSUE"))
CORE_BLOCK = ((0, 0), (1, 0), (0, 1), (1, 1))      # a Core fills a 2x2 block

_EIGHT = ("NORTH", "NORTHEAST", "EAST", "SOUTHEAST", "SOUTH", "SOUTHWEST", "WEST", "NORTHWEST")
_EIGHT_SHORT = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
_CARDINAL_SHORT = {"NORTH": "N", "EAST": "E", "SOUTH": "S", "WEST": "W"}

# how many rounds an occupant sighting stays "fresh" for priority purposes
FRESH_ROUNDS = 30
# minimum observed tile pairs that must agree before a symmetry is trusted
SYMMETRY_MIN_EVIDENCE = 6


@dataclass
class Record:
    state: int
    round: int          # round the information dates from
    source: str         # SEEN / GCS / INFERRED
    published: bool     # already on the store (ours or a teammate's write)


@dataclass
class Tile:
    terrain: Record | None = None
    occupant: Record | None = None


class InternalMap:
    """Fulfils the GCS `MapSource` contract; see bots/utils/GCS/Base/interfaces.py."""

    def __init__(self, map_w: int, map_h: int, team=None):
        self.w, self.h = map_w, map_h
        self.team = team
        self.tiles: dict[tuple[int, int], Tile] = {}
        self.round = 0
        self._symmetry: int | None = None
        self._sym_alive = set(range(len(SYMMETRY_KINDS)))  # candidates not yet contradicted
        self._last_hp: int | None = None

    # ------------------------------------------------------------------
    # input 1: own eyesight
    # ------------------------------------------------------------------
    def observe(self, ct) -> list[Fact]:
        """Scan everything in vision and record it.  Returns the facts that
        are new or changed (already recorded; returned for callers that
        want to react)."""
        self.round = ct.get_current_round()
        if self.team is None:
            self.team = ct.get_team()
        me = ct.get_position()

        changed: list[Fact] = []
        occupants: dict[tuple[int, int], int] = {}
        my_id = ct.get_id()
        for eid in ct.get_nearby_entities():
            if eid == my_id and ct.get_entity_type().value != "core":
                continue                # teammates track us by dead reckoning
            state = self._entity_state(ct, eid)
            if state is None:
                continue
            p = ct.get_position(eid)
            if state in (OUR_CORE, ENEMY_CORE):          # a Core fills its 2x2 block
                for dx, dy in CORE_BLOCK:
                    occupants[(p.x + dx, p.y + dy)] = state
                continue
            key = (p.x, p.y)
            occupants[key] = self._combine(occupants[key], state) if key in occupants else state

        for tile in ct.get_nearby_tiles():
            key = (tile.x, tile.y)
            env = ct.get_tile_env(tile).value
            terrain = WALL if env == "wall" else ORE if env == "ore_titanium" else EMPTY
            if self._record(key, terrain, SEEN):
                changed.append(Fact(key[0], key[1], terrain))
            occ = occupants.get(key, EMPTY)
            if self._record(key, occ, SEEN, layer="occupant"):
                changed.append(Fact(key[0], key[1], occ))

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
            seen_now = (t.occupant for t in self.tiles.values()
                        if t.occupant and t.occupant.source == SEEN and t.occupant.round == self.round)
            if not any(TILE_STATES[r.state].startswith(("ENEMY_GUNNER", "ENEMY_SENTINEL")) for r in seen_now):
                self._record((me.x, me.y), TOOK_FIRE_HERE, SEEN, layer="occupant")
        self._last_hp = hp

    # ------------------------------------------------------------------
    # input 2: the store  (MapSource contract)
    # ------------------------------------------------------------------
    def apply_fact(self, fact: Fact, from_gcs: bool = True) -> None:
        """Record a fact.  A fact that came off the store is already known to
        the whole team, so it is marked published on arrival.  WALL/ORE go
        to the terrain layer; everything else (EMPTY included — it means
        "no occupant") to the occupant layer."""
        layer = "terrain" if fact.state in (WALL, ORE) else "occupant"
        self._record((fact.x, fact.y), fact.state, GCS if from_gcs else SEEN,
                     layer=layer, published=from_gcs)

    def note_shared(self, facts) -> None:
        for f in facts:
            t = self.tiles.get((f.x, f.y))
            if t is None:
                continue
            for rec in (t.terrain, t.occupant):
                if rec is not None and rec.state == f.state:
                    rec.published = True

    def pending_facts(self, budget: int) -> list[Fact]:
        """Unpublished facts from both layers, best first."""
        cands = []
        for (x, y), t in self.tiles.items():
            for rec in (t.terrain, t.occupant):
                if rec is not None and not rec.published:
                    cands.append((self._score(rec), Fact(x, y, rec.state)))
        cands.sort(key=lambda pair: -pair[0])
        return [f for _, f in cands[:budget]]

    def known_facts(self) -> list[Fact]:
        out = []
        for (x, y), t in self.tiles.items():
            for rec in (t.terrain, t.occupant):
                if rec is not None and rec.state != EMPTY:
                    out.append(Fact(x, y, rec.state))
        return out

    def symmetry(self) -> int | None:
        return self._symmetry

    # ------------------------------------------------------------------
    # queries for other modules
    # ------------------------------------------------------------------
    def terrain_at(self, x: int, y: int) -> int | None:
        t = self.tiles.get((x, y))
        return t.terrain.state if t and t.terrain else None

    def occupant_at(self, x: int, y: int) -> int | None:
        """Occupant state, EMPTY if known empty, None if never seen."""
        t = self.tiles.get((x, y))
        return t.occupant.state if t and t.occupant else None

    def state_at(self, x: int, y: int) -> int | None:
        """The most specific thing known: the occupant if any, else terrain."""
        occ = self.occupant_at(x, y)
        if occ is not None and occ != EMPTY:
            return occ
        return self.terrain_at(x, y)

    def age(self, x: int, y: int) -> int | None:
        """Age of the occupant record if it holds something, else of the
        terrain record."""
        t = self.tiles.get((x, y))
        if t is None:
            return None
        rec = t.occupant if t.occupant and t.occupant.state != EMPTY else (t.terrain or t.occupant)
        return self.round - rec.round if rec else None

    def is_passable(self, x: int, y: int) -> bool | None:
        """True/False if known, None if the tile has never been seen.  Walls,
        barriers, harvesters, turrets, cores and builders block movement;
        conveyors and splitters do not."""
        terr, occ = self.terrain_at(x, y), self.occupant_at(x, y)
        if terr is None and occ is None:
            return None
        if terr == WALL:
            return False
        if occ is None or occ == EMPTY or occ in OVERLAYS:
            return True
        name = TILE_STATES[occ]
        return "CONVEYOR" in name or "SPLITTER" in name

    @property
    def our_core(self) -> tuple[int, int] | None:
        """Top-left anchor of our Core's 2x2 block, however we learned it."""
        return self._block_anchor(OUR_CORE)

    def enemy_core(self) -> tuple[int, int] | None:
        """Anchor of the enemy Core's 2x2 block: seen directly, else derived
        from our Core and the symmetry once known."""
        seen = self._block_anchor(ENEMY_CORE)
        if seen is not None:
            return seen
        ours = self.our_core
        if self._symmetry is None or ours is None:
            return None
        return self._mirror_block(ours)

    def note_core_block(self, anchor: tuple[int, int], ours: bool = True) -> None:
        """Record a whole 2x2 Core block from its anchor (e.g. the position the
        GCS learned from the Core's resync message).  Marked published: the
        store already carried it."""
        state = OUR_CORE if ours else ENEMY_CORE
        for dx, dy in CORE_BLOCK:
            self._record((anchor[0] + dx, anchor[1] + dy), state, GCS,
                         layer="occupant", published=True)

    def set_symmetry(self, kind: int) -> None:
        """Accept a SYMMETRY control event from the store."""
        if self._symmetry is None:
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
        """Mirror a 2x2 block's top-left anchor: the far corner maps to the
        new top-left on every mirrored axis."""
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
        terrain = {k: t.terrain.state for k, t in self.tiles.items()
                   if t.terrain and t.terrain.source != INFERRED}
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
            if t.terrain and t.terrain.source != INFERRED:
                self._infer_twin((x, y), t.terrain)

    def _infer_twin(self, key, rec: Record) -> None:
        mk = self._mirror(*key)
        twin = self.tiles.setdefault(mk, Tile())
        if twin.terrain is None:
            twin.terrain = Record(rec.state, rec.round, INFERRED, True)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _record(self, key, state, source, *, layer="terrain", published=False) -> bool:
        """Store a fact in one layer; returns True if it changed what we knew.

        Newer information wins, except that a teammate's report never
        overrides what we saw ourselves in the same or a later round.  An
        overlay (fire / issue) does not displace a real occupant.  Re-
        confirming a known state refreshes its round but keeps it published.
        """
        if not (0 <= key[0] < self.w and 0 <= key[1] < self.h):
            return False
        tile = self.tiles.setdefault(key, Tile())
        cur = getattr(tile, layer)
        if state in OVERLAYS and cur is not None and cur.state not in (EMPTY, state) \
                and cur.state not in OVERLAYS:
            cur.round = self.round
            return False
        if cur is not None and cur.state == state:
            cur.round = max(cur.round, self.round)
            if cur.source == INFERRED:
                cur.source = source
            cur.published = cur.published or published
            return False
        if cur is not None and source == GCS and cur.source == SEEN and cur.round >= self.round:
            return False            # our own fresh eyes beat a teammate's report
        if state == EMPTY and (layer == "terrain" or cur is None or cur.state in OVERLAYS):
            # plain ground is never broadcast (EMPTY on the wire means "no
            # occupant"), and "nothing here" where nothing was known is not news
            published = True
        setattr(tile, layer, Record(state, self.round, source, published))
        if layer == "terrain" and self._symmetry is not None and source != INFERRED:
            self._infer_twin(key, getattr(tile, layer))
        return True

    def _block_anchor(self, core_state: int) -> tuple[int, int] | None:
        keys = [k for k, t in self.tiles.items() if t.occupant and t.occupant.state == core_state]
        if not keys:
            return None
        return min(x for x, _ in keys), min(y for _, y in keys)

    def _score(self, rec: Record) -> float:
        w = state_weight(rec.state)
        if rec.state in TERRAIN:
            return w
        age = self.round - rec.round
        return w * max(0.1, 1.0 - age / FRESH_ROUNDS)
