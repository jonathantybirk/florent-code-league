"""Perception and memory: what this unit knows about the board.

One instance per unit, because module globals are **not** shared between units --
each runs in its own sub-interpreter, so there is no team-wide map object and
never can be. Everything here is this unit's private recollection, widened only
by the handful of facts the 16-slot store can carry.

The model is deliberately dict-and-set based rather than bitmasked. On a 30x30
board the whole map is 900 tiles and the budget is 10 ms per unit-turn, so the
big-integer machinery a 50x50 board needs would be optimising the wrong thing.
If a future meta moves to larger maps, this is the module to replace, and the
`WorldModel` surface below is what the replacement has to keep.
"""
from __future__ import annotations

from fcode import Controller, EntityType, Environment, GameError, Position

import comms
import geom

TURRET_TYPES = (EntityType.GUNNER, EntityType.SENTINEL)
BLOCKING = (EntityType.CORE, EntityType.HARVESTER, EntityType.BARRIER,
            EntityType.GUNNER, EntityType.SENTINEL, EntityType.LAUNCHER)


class Sighting:
    """A building we have seen, remembered past the moment we could see it."""
    __slots__ = ("eid", "pos", "etype", "team", "hp", "round_seen")

    def __init__(self, eid, pos, etype, team, hp, round_seen):
        self.eid = eid
        self.pos = pos
        self.etype = etype
        self.team = team
        self.hp = hp
        self.round_seen = round_seen


class WorldModel:
    def __init__(self):
        self.w = 0
        self.h = 0
        self.round = 0
        self.me = None                  # our own Position this turn
        self.team = None
        self.env = {}                   # (x,y) -> Environment, permanent once seen
        self.seen = set()
        self.ore = set()                # (x,y) of ORE_TITANIUM tiles
        self.walls = set()
        self.buildings = {}             # (x,y) -> Sighting, ours and theirs
        self.enemy_units = []           # [(id, Position, EntityType)] this turn only
        self.ally_units = []
        self.my_core = None
        self.enemy_core = None          # inferred or observed
        self.enemy_core_seen = False
        self.symmetries = list(geom.SYMMETRIES)
        self.threat = set()             # tiles an enemy turret can already hit
        self.contact = False

    # -- lifecycle ----------------------------------------------------------
    def observe(self, ct: Controller) -> None:
        """Refresh everything cheap, once per turn, before any behaviour runs."""
        self.round = ct.get_current_round()
        self.w = ct.get_map_width()
        self.h = ct.get_map_height()
        self.team = ct.get_team()
        try:
            self.me = ct.get_position()
        except GameError:
            return

        self._ingest_tiles(ct)
        self._ingest_entities(ct)
        self._resolve_core(ct)
        self._infer_symmetry(ct)
        self._build_threat(ct)

    def _ingest_tiles(self, ct: Controller) -> None:
        try:
            tiles = ct.get_nearby_tiles()
        except GameError:
            return
        env = self.env
        seen = self.seen
        for p in tiles:
            key = (p.x, p.y)
            if key in seen:
                continue
            try:
                e = ct.get_tile_env(p)
            except GameError:
                continue          # outside vision despite being nearby: skip
            seen.add(key)
            env[key] = e
            if e == Environment.WALL:
                self.walls.add(key)
            elif e == Environment.ORE_TITANIUM:
                self.ore.add(key)

    def _ingest_entities(self, ct: Controller) -> None:
        self.enemy_units = []
        self.ally_units = []
        my_team = self.team
        try:
            ids = ct.get_nearby_entities()
        except GameError:
            return
        for eid in ids:
            try:
                pos = ct.get_position(eid)
                etype = ct.get_entity_type(eid)
                team = ct.get_team(eid)
                hp = ct.get_hp(eid)
            except GameError:
                continue
            key = (pos.x, pos.y)
            if etype == EntityType.BUILDER_BOT:
                if team == my_team:
                    self.ally_units.append((eid, pos, etype))
                else:
                    self.enemy_units.append((eid, pos, etype))
                    self.contact = True
                continue
            self.buildings[key] = Sighting(eid, pos, etype, team, hp, self.round)
            if team != my_team:
                self.contact = True
                if etype in TURRET_TYPES or etype == EntityType.LAUNCHER:
                    self.enemy_units.append((eid, pos, etype))
                if etype == EntityType.CORE:
                    self.enemy_core = pos
                    self.enemy_core_seen = True
            elif etype == EntityType.CORE:
                self.my_core = pos

        # Forget buildings we can currently see the absence of: a remembered
        # turret that is actually rubble makes us avoid tiles that are safe.
        stale = []
        for key, s in self.buildings.items():
            if s.round_seen == self.round:
                continue
            p = Position(key[0], key[1])
            try:
                if ct.is_in_vision(p) and ct.get_tile_building_id(p) is None:
                    stale.append(key)
            except GameError:
                continue
        for key in stale:
            del self.buildings[key]

    def _resolve_core(self, ct: Controller) -> None:
        if self.my_core is None:
            stored = comms.get_pos(ct, comms.CORE_X, comms.CORE_Y)
            if stored is not None:
                self.my_core = stored

    def _infer_symmetry(self, ct: Controller) -> None:
        """Strike any symmetry contradicted by terrain we have actually seen.

        Cheap because it only ever tests tiles already in `env`: a candidate dies
        the moment one observed tile disagrees with its mirror image, and most
        maps resolve to a single candidate within the first dozen rounds.
        """
        if self.my_core is None or len(self.symmetries) <= 1:
            return
        w, h, env = self.w, self.h, self.env
        alive = []
        for sym in self.symmetries:
            ok = True
            checked = 0
            for key, e in env.items():
                mirror = geom.reflect(Position(key[0], key[1]), sym, w, h)
                mk = (mirror.x, mirror.y)
                other = env.get(mk)
                if other is None:
                    continue
                checked += 1
                if other != e:
                    ok = False
                    break
                if checked >= 120:      # enough to discriminate; keep it bounded
                    break
            if ok:
                alive.append(sym)
        if alive:
            self.symmetries = alive
        if not self.enemy_core_seen and self.my_core is not None:
            self.enemy_core = self._predict_enemy_core()

    def _predict_enemy_core(self):
        """Commit to a guess even while several symmetries survive.

        A two-player map is built to be fair, so the Cores sit as far apart as the
        transform allows -- the *farthest* surviving candidate is the right guess
        far more often than the nearest, and rotational symmetry (the commonest
        case in this pool) is by construction the farthest of the three.
        """
        best = None
        best_d = -1
        for sym in self.symmetries:
            cand = geom.core_anchor_reflect(self.my_core, sym, self.w, self.h)
            if not (0 <= cand.x < self.w and 0 <= cand.y < self.h):
                continue
            d = geom.dist_sq(self.my_core, cand)
            if d > best_d:
                best_d = d
                best = cand
        return best

    def _build_threat(self, ct: Controller) -> None:
        """Tiles already covered by a living enemy turret.

        Uses the engine's own `get_attackable_tiles_from`, so the pattern is
        exact -- including the Sentinel's obstacle-ignoring line, which no
        hand-rolled ray would reproduce correctly.
        """
        self.threat = set()
        for key, s in self.buildings.items():
            if s.team == self.team or s.etype not in TURRET_TYPES:
                continue
            try:
                facing = ct.get_direction(s.eid)
            except GameError:
                facing = None
            if facing is None:
                continue
            try:
                tiles = ct.get_attackable_tiles_from(s.pos, facing, s.etype)
            except GameError:
                continue
            for t in tiles:
                self.threat.add((t.x, t.y))

    # -- queries ------------------------------------------------------------
    def is_wall(self, key) -> bool:
        return key in self.walls

    def building_at(self, key):
        return self.buildings.get(key)

    def passable(self, ct: Controller, pos: Position) -> bool:
        """Whether a Builder of ours could stand on this tile.

        Trusts the engine inside vision and falls back to memory outside it,
        because `is_tile_passable` raises for tiles we cannot see.
        """
        key = (pos.x, pos.y)
        if key in self.walls:
            return False
        try:
            if ct.is_in_vision(pos):
                return ct.is_tile_passable(pos)
        except GameError:
            pass
        s = self.buildings.get(key)
        if s is not None and s.etype in BLOCKING:
            return False
        return key in self.seen or True    # unseen tiles are optimistically open

    def my_buildings(self, etype=None):
        for s in self.buildings.values():
            if s.team != self.team:
                continue
            if etype is None or s.etype == etype:
                yield s

    def their_buildings(self, etype=None):
        for s in self.buildings.values():
            if s.team == self.team:
                continue
            if etype is None or s.etype == etype:
                yield s

    def count_mine(self, etype) -> int:
        n = 0
        for s in self.buildings.values():
            if s.team == self.team and s.etype == etype:
                n += 1
        return n
