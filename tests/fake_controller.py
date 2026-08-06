"""A minimal fake fcode.Controller, backed by an in-memory grid World, for
testing bot logic without launching the real engine (no fcode CLI, no
replay file, no 1000-round match -- a scenario like "does a conveyor
chain actually connect a harvester to the Core" runs in milliseconds and
fails with a Python assertion instead of a titanium total you have to
puzzle backwards from).

Direction/Position/Team/EntityType/Environment/GameError are plain Python
objects in real fcode too (not Rust-bound) -- imported directly here
rather than reimplemented, so geometry helpers like Direction.rotate_left
or Position.add match production exactly. Only Controller itself is
injected from Rust at runtime and needs a stand-in.

Not a full engine: no resource-stack physical movement between conveyors/
splitters/harvesters, no unit cap, no CPU-time accounting, no launcher
throws. Scoped to what's needed to exercise a bot's decision logic --
movement, building (existence + facing + adjacency legality), the comm
store, and vision/adjacency queries -- across one or many simulated
rounds. Add a method here when a test needs one rather than working
around the gap; keep it named and shaped like the real Controller method
it stands in for (see fcode._types.Controller's TYPE_CHECKING stub for
the authoritative signatures and docstrings).

Passive titanium income (+PASSIVE_TITANIUM_AMOUNT every
PASSIVE_TITANIUM_INTERVAL rounds, verified against the real engine) and
cost scaling (get_scale_percent() and the get_<entity>_cost() getters,
per-team, rising as entities are built and falling again on destroy/
self_destruct -- see SCALE_CONTRIBUTION) are both modeled; advance_round()
applies the income tick and every build/spawn/destroy path spends and
adjusts scale together. Conveyor/Splitter storage (get_stored_resource(),
get_stored_resource_id()) is exposed as a flag a test sets directly via
World.set_stored_resource() -- since the physical stack movement that
would fill it in the real engine still isn't simulated, treat it the same
way as setting .hp below .max_hp: state a test asserts against, not state
that arises on its own.

Combat is modeled for a Builder Bot's adjacent-building attack (its full
real scope) and for a Gunner's ray -- straight-line trace along its
facing direction, stopping at the first builder bot or building within
GUNNER_RANGE_SQ, blocked (not pierced) by a wall -- plus rotate(). heal()
actually restores HP (capped at max_hp) so can_heal correctly requires a
genuinely damaged target, matching the real engine; fire()/GameError
otherwise still applies no damage to HP -- a test that needs "this thing
is already hurt" sets .hp below .max_hp directly rather than firing at
it down to that state. Units and buildings both start at hp=max_hp=1
unless a test sets otherwise, and there's no Sentinel/Launcher firing
line at all; extend when a test needs one.

Usage sketch:

    world = World(width=20, height=20, ore={Position(5, 5)})
    core_id = world.spawn(Position(2, 2), Team.A, EntityType.CORE)
    builder_id = world.spawn(Position(3, 2), Team.A, EntityType.BUILDER_BOT)
    ct = world.controller_for(builder_id)
    ct.move(Direction.EAST)
    world.advance_round()  # cooldowns tick, store writes commit, re-fetch ct next round
"""

from __future__ import annotations

from dataclasses import dataclass

from fcode import Direction, EntityType, Environment, GameConstants, GameError, Position, ResourceType, Team

BUILDING_TYPES = {
    EntityType.CORE,
    EntityType.HARVESTER,
    EntityType.CONVEYOR,
    EntityType.SPLITTER,
    EntityType.BARRIER,
    EntityType.GUNNER,
    EntityType.SENTINEL,
    EntityType.LAUNCHER,
}
UNIT_TYPES = {EntityType.CORE, EntityType.BUILDER_BOT, EntityType.GUNNER, EntityType.SENTINEL, EntityType.LAUNCHER}
TURRET_TYPES = {EntityType.GUNNER, EntityType.SENTINEL, EntityType.LAUNCHER}
DIRECTIONAL_TYPES = {EntityType.CONVEYOR, EntityType.SPLITTER, EntityType.GUNNER, EntityType.SENTINEL}
PASSABLE_BUILDING_TYPES = {EntityType.CONVEYOR, EntityType.SPLITTER}

VISION_RADIUS_SQ = {
    EntityType.CORE: 36,
    EntityType.BUILDER_BOT: 20,
    EntityType.GUNNER: 13,
    EntityType.SENTINEL: 32,
    EntityType.LAUNCHER: 26,
}

BASE_COST = {
    EntityType.CONVEYOR: 3,
    EntityType.SPLITTER: 6,
    EntityType.HARVESTER: 20,
    EntityType.BARRIER: 3,
    EntityType.GUNNER: 20,
    EntityType.SENTINEL: 30,
    EntityType.LAUNCHER: 20,
    EntityType.BUILDER_BOT: 30,
}

# Gunner-only combat constants (see docs/official/docs/game-rules-turrets.txt).
# Sentinel/Launcher firing lines are still not modeled -- see this module's
# docstring.
GUNNER_RANGE_SQ = 13
GUNNER_AMMO_COST = 4
ROTATE_COST = 10

# Percentage points each built entity adds to its team's cost scale, removed
# again on destroy()/self_destruct() -- see docs/official/docs/game-rules-
# resources.txt. Verified against the real engine: one Builder Bot spawn
# takes a fresh team from 100.0 to 120.0.
SCALE_CONTRIBUTION: dict[EntityType, float] = {
    EntityType.CONVEYOR: 1.0,
    EntityType.SPLITTER: 1.0,
    EntityType.BARRIER: 1.0,
    EntityType.HARVESTER: 5.0,
    EntityType.LAUNCHER: 10.0,
    EntityType.BUILDER_BOT: 20.0,
    EntityType.GUNNER: 20.0,
    EntityType.SENTINEL: 20.0,
}


@dataclass
class Entity:
    id: int
    pos: Position
    team: Team
    etype: EntityType
    direction: Direction | None = None
    hp: int = 1
    max_hp: int = 1
    action_cooldown: int = 0
    move_cooldown: int = 0
    used_move: bool = False
    used_action: bool = False
    stored_resource: ResourceType | None = None
    stored_resource_id: int | None = None


class World:
    """Shared simulation state for one scenario. Call controller_for(id)
    to get a fresh FakeController for a given unit each round -- the real
    engine hands each unit its own Controller instance too.
    """

    def __init__(
        self,
        width: int,
        height: int,
        walls: frozenset[Position] = frozenset(),
        ore: frozenset[Position] = frozenset(),
        starting_resources: int = 100_000,
    ) -> None:
        self.width = width
        self.height = height
        self.walls = set(walls)
        self.ore = set(ore)
        self.entities: dict[int, Entity] = {}
        self.resources: dict[Team, int] = {Team.A: starting_resources, Team.B: starting_resources}
        self.ammo: dict[Team, int] = {Team.A: 0, Team.B: 0}
        self.scale_percent: dict[Team, float] = {Team.A: 100.0, Team.B: 100.0}
        self.store: dict[Team, list[int]] = {Team.A: [0] * 16, Team.B: [0] * 16}
        self._pending_store: dict[Team, dict[int, int]] = {Team.A: {}, Team.B: {}}
        self._converted_this_round: set[Team] = set()
        self.round = 0
        self._next_id = 1
        self._next_resource_id = 1

    # --- setup ---

    def spawn(self, pos: Position, team: Team, etype: EntityType, direction: Direction | None = None) -> int:
        id_ = self._next_id
        self._next_id += 1
        self.entities[id_] = Entity(id=id_, pos=pos, team=team, etype=etype, direction=direction)
        return id_

    def set_stored_resource(self, building_id: int, resource: ResourceType | None) -> int | None:
        """Test setup helper: put resource on a Conveyor/Splitter, or clear
        it with None. Assigns a fresh id per call (mirroring how
        get_stored_resource_id lets real bots recognize the same physical
        stack persisting across rounds) -- conveyor movement itself still
        isn't simulated, so set this directly rather than building a chain
        and waiting for a stack to arrive.
        """
        e = self.entities[building_id]
        if resource is None:
            e.stored_resource = None
            e.stored_resource_id = None
            return None
        e.stored_resource = resource
        e.stored_resource_id = self._next_resource_id
        self._next_resource_id += 1
        return e.stored_resource_id

    def controller_for(self, id: int) -> FakeController:
        return FakeController(self, id)

    # --- round lifecycle ---

    def advance_round(self) -> None:
        for team, pending in self._pending_store.items():
            for idx, val in pending.items():
                self.store[team][idx] = val
            pending.clear()
        self._converted_this_round.clear()
        for e in self.entities.values():
            if e.action_cooldown > 0:
                e.action_cooldown -= 1
            if e.move_cooldown > 0:
                e.move_cooldown -= 1
            e.used_move = False
            e.used_action = False
        self.round += 1
        if self.round % GameConstants.PASSIVE_TITANIUM_INTERVAL == 0:
            for team in self.resources:
                self.resources[team] += GameConstants.PASSIVE_TITANIUM_AMOUNT

    # --- shared queries ---

    def in_bounds(self, pos: Position) -> bool:
        return 0 <= pos.x < self.width and 0 <= pos.y < self.height

    def footprint_contains(self, e: Entity, pos: Position) -> bool:
        if e.etype != EntityType.CORE:
            return e.pos == pos
        return e.pos.x <= pos.x < e.pos.x + 2 and e.pos.y <= pos.y < e.pos.y + 2

    def building_at(self, pos: Position) -> Entity | None:
        for e in self.entities.values():
            if e.etype in BUILDING_TYPES and self.footprint_contains(e, pos):
                return e
        return None

    def builder_at(self, pos: Position) -> Entity | None:
        for e in self.entities.values():
            if e.etype == EntityType.BUILDER_BOT and e.pos == pos:
                return e
        return None

    def env(self, pos: Position) -> Environment:
        if pos in self.walls:
            return Environment.WALL
        if pos in self.ore:
            return Environment.ORE_TITANIUM
        return Environment.EMPTY


class FakeController:
    def __init__(self, world: World, id: int) -> None:
        self.world = world
        self.id = id

    @property
    def _self(self) -> Entity:
        return self.world.entities[self.id]

    def _entity(self, id: int | None) -> Entity:
        return self.world.entities[id] if id is not None else self._self

    def _adjacent_dir(self, pos: Position) -> Direction | None:
        """The cardinal direction from this unit to pos, or None if pos
        isn't exactly one orthogonal step away (matches every build/heal/
        fire method's "orthogonally adjacent, not this unit's own tile"
        requirement).
        """
        for d in (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST):
            if self._self.pos.add(d) == pos:
                return d
        return None

    def _can_act_now(self) -> bool:
        return not self._self.used_move and not self._self.used_action and self._self.action_cooldown == 0

    # --- info ---

    def get_team(self, id: int | None = None) -> Team:
        return self._entity(id).team

    def get_position(self, id: int | None = None) -> Position:
        return self._entity(id).pos

    def get_id(self) -> int:
        return self.id

    def get_entity_type(self, id: int | None = None) -> EntityType:
        return self._entity(id).etype

    def get_direction(self, id: int | None = None) -> Direction:
        d = self._entity(id).direction
        if d is None:
            raise GameError("entity has no direction")
        return d

    def get_stored_resource(self, id: int | None = None) -> ResourceType | None:
        e = self._entity(id)
        if e.etype not in (EntityType.CONVEYOR, EntityType.SPLITTER):
            raise GameError("entity has no storage")
        return e.stored_resource

    def get_stored_resource_id(self, id: int | None = None) -> int | None:
        e = self._entity(id)
        if e.etype not in (EntityType.CONVEYOR, EntityType.SPLITTER):
            raise GameError("entity has no storage")
        return e.stored_resource_id

    def get_hp(self, id: int | None = None) -> int:
        return self._entity(id).hp

    def get_max_hp(self, id: int | None = None) -> int:
        return self._entity(id).max_hp

    def get_action_cooldown(self) -> int:
        return self._self.action_cooldown

    def get_move_cooldown(self) -> int:
        return self._self.move_cooldown

    def can_act(self) -> bool:
        return self.get_action_cooldown() == 0

    def get_vision_radius_sq(self, id: int | None = None) -> int:
        return VISION_RADIUS_SQ.get(self._entity(id).etype, 20)

    def get_map_width(self) -> int:
        return self.world.width

    def get_map_height(self) -> int:
        return self.world.height

    def get_current_round(self) -> int:
        return self.world.round

    def get_cpu_time_elapsed(self) -> int:
        return 0

    def get_unit_count(self) -> int:
        return sum(1 for e in self.world.entities.values() if e.team == self._self.team and e.etype in UNIT_TYPES)

    # --- tiles / vision ---

    def get_tile_env(self, pos: Position) -> Environment:
        if not self.world.in_bounds(pos):
            raise GameError("Position out of bounds")
        return self.world.env(pos)

    def get_tile_building_id(self, pos: Position) -> int | None:
        if not self.world.in_bounds(pos):
            raise GameError("Position out of bounds")
        b = self.world.building_at(pos)
        return b.id if b else None

    def get_tile_builder_bot_id(self, pos: Position) -> int | None:
        if not self.world.in_bounds(pos):
            raise GameError("Position out of bounds")
        b = self.world.builder_at(pos)
        return b.id if b else None

    def is_tile_empty(self, pos: Position) -> bool:
        if not self.world.in_bounds(pos):
            raise GameError("Position out of bounds")
        return self.world.env(pos) != Environment.WALL and self.world.building_at(pos) is None and self.world.builder_at(pos) is None

    def is_tile_passable(self, pos: Position) -> bool:
        if not self.world.in_bounds(pos) or pos in self.world.walls:
            return False
        if self.world.builder_at(pos) is not None:
            return False
        b = self.world.building_at(pos)
        return b is None or b.etype in PASSABLE_BUILDING_TYPES

    def is_in_vision(self, pos: Position) -> bool:
        return self._self.pos.distance_squared(pos) <= self.get_vision_radius_sq()

    def get_nearby_tiles(self, dist_sq: int | None = None) -> list[Position]:
        r2 = dist_sq if dist_sq is not None else self.get_vision_radius_sq()
        pos = self._self.pos
        r = int(r2**0.5) + 1
        out = []
        for x in range(max(0, pos.x - r), min(self.world.width, pos.x + r + 1)):
            for y in range(max(0, pos.y - r), min(self.world.height, pos.y + r + 1)):
                p = Position(x, y)
                if pos.distance_squared(p) <= r2:
                    out.append(p)
        return out

    def get_nearby_entities(self, dist_sq: int | None = None) -> list[int]:
        r2 = dist_sq if dist_sq is not None else self.get_vision_radius_sq()
        pos = self._self.pos
        return [e.id for e in self.world.entities.values() if pos.distance_squared(e.pos) <= r2]

    def get_nearby_buildings(self, dist_sq: int | None = None) -> list[int]:
        return [i for i in self.get_nearby_entities(dist_sq) if self.world.entities[i].etype in BUILDING_TYPES]

    def get_nearby_units(self, dist_sq: int | None = None) -> list[int]:
        return [i for i in self.get_nearby_entities(dist_sq) if self.world.entities[i].etype in UNIT_TYPES]

    # --- resources ---

    def get_global_resources(self) -> int:
        return self.world.resources[self._self.team]

    def get_global_ammo(self) -> int:
        return self.world.ammo[self._self.team]

    def can_convert_ammo(self, amount: int) -> bool:
        team = self._self.team
        return (
            self._self.etype == EntityType.CORE
            and team not in self.world._converted_this_round
            and self.world.resources[team] >= amount
        )

    def convert_ammo(self, amount: int) -> None:
        if not self.can_convert_ammo(amount):
            raise GameError("cannot convert ammo")
        team = self._self.team
        self.world.resources[team] -= amount
        self.world.ammo[team] += amount
        self.world._converted_this_round.add(team)

    def get_scale_percent(self) -> float:
        return self.world.scale_percent[self._self.team]

    def _scaled_cost(self, etype: EntityType) -> int:
        # effective_cost = base_cost * scale_percent / 100, floored -- verified
        # against the real engine (3 Ti conveyor at scale 120.0 costs 3, not 4).
        scale = self.world.scale_percent[self._self.team]
        return int(BASE_COST[etype] * scale / 100.0 + 1e-9)

    def get_conveyor_cost(self) -> int:
        return self._scaled_cost(EntityType.CONVEYOR)

    def get_splitter_cost(self) -> int:
        return self._scaled_cost(EntityType.SPLITTER)

    def get_harvester_cost(self) -> int:
        return self._scaled_cost(EntityType.HARVESTER)

    def get_barrier_cost(self) -> int:
        return self._scaled_cost(EntityType.BARRIER)

    def get_gunner_cost(self) -> int:
        return self._scaled_cost(EntityType.GUNNER)

    def get_sentinel_cost(self) -> int:
        return self._scaled_cost(EntityType.SENTINEL)

    def get_launcher_cost(self) -> int:
        return self._scaled_cost(EntityType.LAUNCHER)

    def get_builder_bot_cost(self) -> int:
        return self._scaled_cost(EntityType.BUILDER_BOT)

    # --- movement ---

    def can_move(self, direction: Direction) -> bool:
        if self._self.etype != EntityType.BUILDER_BOT:
            return False
        if not direction.is_cardinal():
            return False
        if not self._can_act_now() or self._self.move_cooldown > 0:
            return False
        target = self._self.pos.add(direction)
        if not self.world.in_bounds(target) or target in self.world.walls:
            return False
        if self.world.builder_at(target) is not None:
            return False
        b = self.world.building_at(target)
        if b is not None and b.etype not in PASSABLE_BUILDING_TYPES:
            return False
        return True

    def move(self, direction: Direction) -> None:
        if not self.can_move(direction):
            raise GameError(f"cannot move {direction}")
        self._self.pos = self._self.pos.add(direction)
        self._self.used_move = True
        self._self.move_cooldown = 1

    # --- building ---

    def _can_build_at(self, position: Position, etype: EntityType, *, needs_ore: bool = False) -> bool:
        if self._self.etype != EntityType.BUILDER_BOT:
            return False
        if self._adjacent_dir(position) is None:
            return False
        if not self._can_act_now():
            return False
        if not self.world.in_bounds(position) or position in self.world.walls:
            return False
        if needs_ore and position not in self.world.ore:
            return False
        if self.world.building_at(position) is not None:
            return False
        if self.world.builder_at(position) is not None:
            return False
        return self.world.resources[self._self.team] >= self._scaled_cost(etype)

    def _build(self, position: Position, etype: EntityType, direction: Direction | None) -> int:
        cost = self._scaled_cost(etype)
        id_ = self.world.spawn(position, self._self.team, etype, direction)
        self.world.resources[self._self.team] -= cost
        self.world.scale_percent[self._self.team] += SCALE_CONTRIBUTION.get(etype, 0.0)
        self._self.used_action = True
        self._self.action_cooldown = 1
        return id_

    def can_build_conveyor(self, position: Position, direction: Direction) -> bool:
        return self._can_build_at(position, EntityType.CONVEYOR)

    def build_conveyor(self, position: Position, direction: Direction) -> int:
        if not self.can_build_conveyor(position, direction):
            raise GameError("cannot build conveyor")
        return self._build(position, EntityType.CONVEYOR, direction)

    def can_build_splitter(self, position: Position, direction: Direction) -> bool:
        return self._can_build_at(position, EntityType.SPLITTER)

    def build_splitter(self, position: Position, direction: Direction) -> int:
        if not self.can_build_splitter(position, direction):
            raise GameError("cannot build splitter")
        return self._build(position, EntityType.SPLITTER, direction)

    def can_build_harvester(self, position: Position) -> bool:
        return self._can_build_at(position, EntityType.HARVESTER, needs_ore=True)

    def build_harvester(self, position: Position) -> int:
        if not self.can_build_harvester(position):
            raise GameError("cannot build harvester")
        return self._build(position, EntityType.HARVESTER, None)

    def can_build_barrier(self, position: Position) -> bool:
        return self._can_build_at(position, EntityType.BARRIER)

    def build_barrier(self, position: Position) -> int:
        if not self.can_build_barrier(position):
            raise GameError("cannot build barrier")
        return self._build(position, EntityType.BARRIER, None)

    def can_build_gunner(self, position: Position, direction: Direction) -> bool:
        return self._can_build_at(position, EntityType.GUNNER)

    def build_gunner(self, position: Position, direction: Direction) -> int:
        if not self.can_build_gunner(position, direction):
            raise GameError("cannot build gunner")
        return self._build(position, EntityType.GUNNER, direction)

    def can_build_sentinel(self, position: Position, direction: Direction) -> bool:
        return self._can_build_at(position, EntityType.SENTINEL)

    def build_sentinel(self, position: Position, direction: Direction) -> int:
        if not self.can_build_sentinel(position, direction):
            raise GameError("cannot build sentinel")
        return self._build(position, EntityType.SENTINEL, direction)

    def can_build_launcher(self, position: Position) -> bool:
        return self._can_build_at(position, EntityType.LAUNCHER)

    def build_launcher(self, position: Position) -> int:
        if not self.can_build_launcher(position):
            raise GameError("cannot build launcher")
        return self._build(position, EntityType.LAUNCHER, None)

    # --- healing ---

    def can_heal(self, position: Position) -> bool:
        if self._self.etype != EntityType.BUILDER_BOT:
            return False
        if self._adjacent_dir(position) is None:
            return False
        if not self._can_act_now():
            return False
        if self.world.resources[self._self.team] < 1:
            return False
        my_team = self._self.team
        b = self.world.building_at(position)
        bot = self.world.builder_at(position)
        damaged = (
            (b is not None and b.team == my_team and b.hp < b.max_hp)
            or (bot is not None and bot.team == my_team and bot.hp < bot.max_hp)
        )
        return damaged

    def heal(self, position: Position) -> None:
        if not self.can_heal(position):
            raise GameError("cannot heal")
        self.world.resources[self._self.team] -= 1
        self._self.used_action = True
        self._self.action_cooldown = 1
        my_team = self._self.team
        b = self.world.building_at(position)
        if b is not None and b.team == my_team:
            b.hp = min(b.max_hp, b.hp + 4)
        bot = self.world.builder_at(position)
        if bot is not None and bot.team == my_team:
            bot.hp = min(bot.max_hp, bot.hp + 4)

    # --- destruction ---

    def can_destroy(self, building_pos: Position) -> bool:
        if self._self.etype != EntityType.BUILDER_BOT:
            return False
        if self._adjacent_dir(building_pos) is None:
            return False
        b = self.world.building_at(building_pos)
        return b is not None and b.team == self._self.team

    def destroy(self, building_pos: Position) -> None:
        if not self.can_destroy(building_pos):
            raise GameError("cannot destroy")
        b = self.world.building_at(building_pos)
        assert b is not None
        self.world.scale_percent[b.team] -= SCALE_CONTRIBUTION.get(b.etype, 0.0)
        del self.world.entities[b.id]

    def self_destruct(self) -> None:
        self.world.scale_percent[self._self.team] -= SCALE_CONTRIBUTION.get(self._self.etype, 0.0)
        del self.world.entities[self.id]

    def resign(self, message: str | None = None) -> None:
        pass

    # --- communication store ---

    def read_store(self, index: int) -> int:
        if not 0 <= index < 16:
            raise GameError("store index out of range")
        return self.world.store[self._self.team][index]

    def write_store(self, index: int, value: int) -> None:
        if not 0 <= index < 16:
            raise GameError("store index out of range")
        self.world._pending_store[self._self.team][index] = value

    # --- combat (Builder Bot adjacent-attack + Gunner ray; Sentinel/Launcher
    # firing lines are not modeled -- see module docstring) ---

    def _gunner_ray_target(self, pos: Position, direction: Direction | None) -> Position | None:
        """Straight-line trace from pos along direction: the first tile
        carrying a builder bot or a building, within GUNNER_RANGE_SQ, or
        None if nothing qualifies. A wall blocks the ray outright (it
        isn't itself targetable) rather than being passed through.
        """
        if direction is None:
            return None
        cur = pos
        while True:
            cur = cur.add(direction)
            if not self.world.in_bounds(cur) or pos.distance_squared(cur) > GUNNER_RANGE_SQ:
                return None
            if cur in self.world.walls:
                return None
            if self.world.builder_at(cur) is not None or self.world.building_at(cur) is not None:
                return cur

    def can_fire(self, target: Position) -> bool:
        if self._self.etype == EntityType.BUILDER_BOT:
            if self._adjacent_dir(target) is None:
                return False
            if not self._can_act_now():
                return False
            if self.world.resources[self._self.team] < 2:
                return False
            return self.world.building_at(target) is not None
        if self._self.etype == EntityType.GUNNER:
            if not self._can_act_now():
                return False
            if self.world.ammo[self._self.team] < GUNNER_AMMO_COST:
                return False
            return self._gunner_ray_target(self._self.pos, self._self.direction) == target
        return False

    def fire(self, target: Position) -> None:
        if not self.can_fire(target):
            raise GameError("cannot fire")
        if self._self.etype == EntityType.GUNNER:
            self.world.ammo[self._self.team] -= GUNNER_AMMO_COST
        else:
            self.world.resources[self._self.team] -= 2
        self._self.used_action = True
        self._self.action_cooldown = 1

    def get_gunner_target(self) -> Position | None:
        if self._self.etype != EntityType.GUNNER:
            raise GameError("get_gunner_target: Gunner only")
        return self._gunner_ray_target(self._self.pos, self._self.direction)

    def can_fire_from(
        self, pos: Position, direction: Direction, turret_type: EntityType, target: Position
    ) -> bool:
        if turret_type != EntityType.GUNNER:
            return False  # Sentinel/Launcher hypothetical rays aren't modeled
        return self._gunner_ray_target(pos, direction) == target

    def can_rotate(self, direction: Direction) -> bool:
        if self._self.etype != EntityType.GUNNER:
            return False
        if not self._can_act_now():
            return False
        return self.world.resources[self._self.team] >= ROTATE_COST

    def rotate(self, direction: Direction) -> None:
        if not self.can_rotate(direction):
            raise GameError("cannot rotate")
        self.world.resources[self._self.team] -= ROTATE_COST
        self._self.direction = direction
        self._self.used_action = True
        self._self.action_cooldown = 1

    # --- core ---

    def can_spawn(self, position: Position) -> bool:
        if self._self.etype != EntityType.CORE:
            return False
        if not self._can_act_now():
            return False
        if not self.world.in_bounds(position) or position in self.world.walls:
            return False
        if self.world.building_at(position) is not None or self.world.builder_at(position) is not None:
            return False
        if self._self.pos.distance_squared(position) > 2 and not self.world.footprint_contains(self._self, position):
            # cheap approximation of "adjacent to the Core's 2x2 footprint"
            for corner_dx in (0, 1):
                for corner_dy in (0, 1):
                    corner = Position(self._self.pos.x + corner_dx, self._self.pos.y + corner_dy)
                    if corner.distance_squared(position) <= 2:
                        break
                else:
                    continue
                break
            else:
                return False
        return self.world.resources[self._self.team] >= self._scaled_cost(EntityType.BUILDER_BOT)

    def spawn_builder(self, position: Position) -> int:
        if not self.can_spawn(position):
            raise GameError("cannot spawn")
        cost = self._scaled_cost(EntityType.BUILDER_BOT)
        id_ = self.world.spawn(position, self._self.team, EntityType.BUILDER_BOT)
        self.world.resources[self._self.team] -= cost
        self.world.scale_percent[self._self.team] += SCALE_CONTRIBUTION[EntityType.BUILDER_BOT]
        self._self.used_action = True
        self._self.action_cooldown = 1
        return id_

    # --- debugging (no-ops) ---

    def draw_indicator_line(self, pos_a: Position, pos_b: Position, r: int, g: int, b: int) -> None:
        pass

    def draw_indicator_dot(self, pos: Position, r: int, g: int, b: int) -> None:
        pass
