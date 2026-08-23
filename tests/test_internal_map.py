"""Internal map tests — headless, with a fake controller."""

from __future__ import annotations

from bots.utils.GCS.Base.messages import Fact
from bots.utils.GCS.Base.protocol import STATE_CODE, TILE_STATES
from bots.utils.internal_map.Base.internal_map import (
    GCS, INFERRED, SEEN, InternalMap,
)

W, H = 12, 10
EMPTY, WALL, ORE = STATE_CODE["EMPTY"], STATE_CODE["WALL"], STATE_CODE["ORE_FREE"]


def enum(name, value):
    return type(name, (), {"value": value, "name": name})()


class Pos:
    def __init__(self, x, y):
        self.x, self.y = x, y


class FakeCt:
    """A unit of team A at `pos` with vision radius² 20, on a map whose
    terrain is `terrain[(x, y)]` ('wall'/'ore'/'empty') and whose entities
    are dicts {id: (type, team, (x, y), direction_name)}."""

    def __init__(self, pos, terrain, entities, me_id=1, me_type="builder_bot",
                 round_no=0, hp=40):
        self.pos, self.terrain, self.entities = pos, terrain, entities
        self.me_id, self.me_type, self.round_no, self.hp = me_id, me_type, round_no, hp

    def get_current_round(self): return self.round_no
    def get_team(self, id=None): return "A" if id is None else self.entities[id][1]
    def get_position(self, id=None):
        return Pos(*self.pos) if id is None else Pos(*self.entities[id][2])
    def get_entity_type(self, id=None):
        return enum(self.me_type, self.me_type) if id is None else enum(self.entities[id][0], self.entities[id][0])
    def get_id(self): return self.me_id
    def get_hp(self, id=None): return self.hp
    def get_direction(self, id): return enum(self.entities[id][3], self.entities[id][3])
    def get_nearby_entities(self):
        return [i for i, e in self.entities.items()
                if (e[2][0]-self.pos[0])**2 + (e[2][1]-self.pos[1])**2 <= 20]
    def get_nearby_tiles(self):
        return [Pos(x, y) for y in range(H) for x in range(W)
                if (x-self.pos[0])**2 + (y-self.pos[1])**2 <= 20]
    def get_tile_env(self, p):
        t = self.terrain.get((p.x, p.y), "empty")
        return enum(t, {"wall": "wall", "ore": "ore_titanium", "empty": "empty"}[t])


def test_observe_records_terrain_and_entities_with_facing():
    terrain = {(6, 5): "wall", (7, 5): "ore"}
    ents = {1: ("builder_bot", "A", (5, 5), None),
            2: ("gunner", "B", (6, 6), "NORTHEAST"),
            3: ("conveyor", "A", (5, 6), "EAST"),
            4: ("builder_bot", "A", (5, 6), None)}        # on the conveyor
    m = InternalMap(W, H)
    m.observe(FakeCt((5, 5), terrain, ents))
    assert m.state_at(6, 5) == WALL and m.state_at(7, 5) == ORE
    assert TILE_STATES[m.state_at(6, 6)] == "ENEMY_GUNNER_NE"
    assert TILE_STATES[m.state_at(5, 6)] == "OUR_BOT_ON_CONVEYOR_E"
    assert m.state_at(5, 5) == EMPTY                          # own tile: self skipped


def test_pending_prefers_enemy_turret_and_excludes_plain_empty():
    terrain = {(6, 5): "wall"}
    ents = {1: ("builder_bot", "A", (5, 5), None), 2: ("sentinel", "B", (7, 6), "SOUTH")}
    m = InternalMap(W, H)
    m.observe(FakeCt((5, 5), terrain, ents))
    pend = m.pending_facts(10)
    assert TILE_STATES[pend[0].state] == "ENEMY_SENTINEL_S"
    assert all(f.state != EMPTY for f in pend)               # empty-on-unknown is not news


def test_negative_fact_is_published_when_building_disappears():
    ents = {1: ("builder_bot", "A", (5, 5), None), 2: ("harvester", "B", (6, 5), None)}
    m = InternalMap(W, H)
    m.observe(FakeCt((5, 5), {}, ents, round_no=0))
    m.note_shared(m.pending_facts(10))
    assert not m.pending_facts(10)
    del ents[2]                                               # harvester destroyed
    m.observe(FakeCt((5, 5), {}, ents, round_no=1))
    assert m.pending_facts(10) == [Fact(6, 5, EMPTY)]         # the negative goes out


def test_gcs_fact_is_published_on_arrival_and_loses_to_fresh_eyes():
    m = InternalMap(W, H)
    m.apply_fact(Fact(3, 3, ORE), from_gcs=True)
    assert m.tiles[(3, 3)].published and m.tiles[(3, 3)].source == GCS
    assert m.pending_facts(5) == []
    m.observe(FakeCt((3, 4), {(3, 3): "wall"}, {1: ("builder_bot", "A", (3, 4), None)}, round_no=5))
    assert m.state_at(3, 3) == WALL and m.tiles[(3, 3)].source == SEEN
    m.apply_fact(Fact(3, 3, ORE), from_gcs=True)              # stale teammate report
    assert m.state_at(3, 3) == WALL                           # our fresh eyes win


def test_age_and_freshness_scoring():
    ents = {1: ("builder_bot", "A", (5, 5), None), 2: ("builder_bot", "B", (6, 5), None)}
    m = InternalMap(W, H)
    m.observe(FakeCt((5, 5), {}, ents, round_no=0))
    m.round = 40
    assert m.age(6, 5) == 40
    old = m._score(m.tiles[(6, 5)])
    m.round = 0
    assert m._score(m.tiles[(6, 5)]) > old                    # enemy sightings decay


def test_symmetry_inferred_from_terrain_and_mirrors():
    # a left-right mirrored map: wall columns at x=2 and x=W-3, ore at (1,2)/(W-2,2)
    terrain = {}
    for y in range(H):
        terrain[(2, y)] = "wall"; terrain[(W-3, y)] = "wall"
    terrain[(1, 2)] = "ore"; terrain[(W-2, 2)] = "ore"
    m = InternalMap(W, H)
    ents = {1: ("builder_bot", "A", (5, 4), None)}
    # walk across the middle so both halves get seen
    for r, x in enumerate((4, 5, 6, 7)):
        ents[1] = ("builder_bot", "A", (x, 4), None)
        m.observe(FakeCt((x, 4), terrain, ents, round_no=r))
    assert m.symmetry() == 0                                  # MIRROR_X
    # an unseen twin of a seen wall is inferred and marked published
    m.tiles.pop((W-3, 9), None)
    m._record((2, 9), WALL, SEEN)
    assert m.tiles[(W-3, 9)].source == INFERRED and m.tiles[(W-3, 9)].published


def test_enemy_core_from_symmetry():
    m = InternalMap(20, 20)
    m.our_core = (2, 9)
    m.set_symmetry(0)                                         # MIRROR_X
    assert m.enemy_core() == (16, 9)                          # 2x2 block mirrored
    m.set_symmetry(2)                                         # ROT_180
    assert m.enemy_core() == (16, 9)


def test_builder_learns_our_core_and_derives_enemy_core():
    m = InternalMap(20, 20)
    m.apply_fact(Fact(2, 9, STATE_CODE["OUR_CORE"]), from_gcs=True)
    assert m.our_core == (2, 9)
    m.set_symmetry(0)
    assert m.enemy_core() == (16, 9)


def test_took_fire_overlay_when_hp_drops_unseen():
    ents = {1: ("builder_bot", "A", (5, 5), None)}
    m = InternalMap(W, H)
    m.observe(FakeCt((5, 5), {}, ents, round_no=0, hp=40))
    m.observe(FakeCt((5, 5), {}, ents, round_no=1, hp=33))
    assert TILE_STATES[m.state_at(5, 5)] == "TOOK_FIRE_HERE"


def test_is_passable():
    m = InternalMap(W, H)
    m.apply_fact(Fact(1, 1, WALL))
    m.apply_fact(Fact(2, 1, STATE_CODE["OUR_CONVEYOR_N"]))
    m.apply_fact(Fact(3, 1, STATE_CODE["ENEMY_HARVESTER"]))
    assert m.is_passable(1, 1) is False
    assert m.is_passable(2, 1) is True
    assert m.is_passable(3, 1) is False
    assert m.is_passable(9, 9) is None
