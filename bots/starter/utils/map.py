"""Per-unit memory of static terrain and time-sensitive map occupancy."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping

from fcode import (
    Controller,
    Direction,
    EntityType,
    Environment,
    Position,
    ResourceType,
    Team,
)


class DiscoverySource(Enum):
    """How a tile's authoritative ground information was discovered."""

    KNOWN_MAP = "known_map"
    REGISTRY = "registry"
    VISION = "vision"


@dataclass(frozen=True, slots=True)
class FixedCore:
    """A Core that is part of a map's fixed starting layout."""

    team: Team
    anchor: Position


@dataclass(frozen=True, slots=True)
class EntitySnapshot:
    """All state that the controller can query for an arbitrary visible entity."""

    id: int
    position: Position
    entity_type: EntityType
    team: Team
    hp: int
    max_hp: int
    direction: Direction | None = None
    stored_resource: ResourceType | None = None
    stored_resource_id: int | None = None


@dataclass(frozen=True, slots=True)
class TileObservation:
    """Common input format for direct vision and future registry updates."""

    position: Position
    environment: Environment
    building: EntitySnapshot | None = None
    builder_bot: EntitySnapshot | None = None
    occupancy_known: bool = True

    @property
    def fixed_core(self) -> FixedCore | None:
        if self.building is None or self.building.entity_type != EntityType.CORE:
            return None
        return FixedCore(self.building.team, self.building.position)


@dataclass(slots=True)
class TileState:
    """The last known ground and actual state for one map position."""

    environment: Environment
    fixed_core: FixedCore | None
    building: EntitySnapshot | None
    builder_bot: EntitySnapshot | None
    occupancy_known: bool
    source: DiscoverySource
    rounds_since_last_seen: int | None


@dataclass(frozen=True, slots=True)
class KnownMap:
    """Static ground information decoded from a bundled .map26 file."""

    name: str
    width: int
    height: int
    environments: tuple[tuple[Environment, ...], ...]
    cores: Mapping[Position, FixedCore]

    def environment_at(self, position: Position) -> Environment:
        return self.environments[position.y][position.x]


@dataclass(slots=True)
class MapMatchState:
    """Atlas-matching state kept separately for each Player instance."""

    known_maps: Mapping[str, KnownMap] = field(
        default_factory=lambda: load_known_maps(), repr=False
    )
    candidate_names: set[str] = field(default_factory=set)
    rejected_maps: set[str] = field(default_factory=set)
    inferred_map_name: str | None = None
    last_processed_round: int | None = None
    dimensions: tuple[int, int] | None = None


_DIRECTIONAL_ENTITIES = {
    EntityType.CONVEYOR,
    EntityType.SPLITTER,
    EntityType.GUNNER,
    EntityType.SENTINEL,
}
_STORAGE_ENTITIES = {EntityType.CONVEYOR, EntityType.SPLITTER}
_SOURCE_PRIORITY = {
    DiscoverySource.KNOWN_MAP: 0,
    DiscoverySource.REGISTRY: 1,
    DiscoverySource.VISION: 2,
}
_TILE_VALUES = {
    0: Environment.EMPTY,
    1: Environment.WALL,
    2: Environment.ORE_TITANIUM,
}
_TEAM_VALUES = {1: Team.A, 2: Team.B}


def decode_map_info(ct: Controller) -> list[TileObservation] | None:
    """Decode tile updates from the common registry once its format is defined."""

    pass


def update_map(
    ct: Controller,
    tiles: dict[Position, TileState],
    match_state: MapMatchState,
) -> None:
    """Age and refresh one Player's internal map, then update atlas inference."""

    current_round = ct.get_current_round()
    _age_tiles(tiles, match_state, current_round)

    registry_observations = decode_map_info(ct) or []
    vision_observations = _collect_visible_tiles(ct)

    width = ct.get_map_width()
    height = ct.get_map_height()
    dimensions = (width, height)
    if match_state.dimensions != dimensions:
        match_state.dimensions = dimensions
        match_state.candidate_names.clear()
        match_state.inferred_map_name = None

    # When both channels report the same position, current direct vision wins.
    evidence_by_position = {
        observation.position: observation for observation in registry_observations
    }
    evidence_by_position.update(
        {observation.position: observation for observation in vision_observations}
    )
    if _inferred_map_conflicts(evidence_by_position.values(), match_state):
        _reject_inferred_map(tiles, match_state)

    _apply_observations(
        tiles, registry_observations, DiscoverySource.REGISTRY
    )
    _apply_observations(tiles, vision_observations, DiscoverySource.VISION)

    _update_candidates(tiles, match_state, width, height)
    if len(match_state.candidate_names) == 1:
        name = next(iter(match_state.candidate_names))
        match_state.inferred_map_name = name
        _fill_from_known_map(tiles, match_state.known_maps[name])


def _age_tiles(
    tiles: dict[Position, TileState],
    match_state: MapMatchState,
    current_round: int,
) -> None:
    previous_round = match_state.last_processed_round
    match_state.last_processed_round = current_round
    if previous_round is None or current_round <= previous_round:
        return

    elapsed = current_round - previous_round
    for tile in tiles.values():
        if tile.rounds_since_last_seen is not None:
            tile.rounds_since_last_seen += elapsed


def _collect_visible_tiles(ct: Controller) -> list[TileObservation]:
    snapshots: dict[int, EntitySnapshot] = {}
    observations: list[TileObservation] = []

    def snapshot(entity_id: int | None) -> EntitySnapshot | None:
        if entity_id is None:
            return None
        if entity_id not in snapshots:
            snapshots[entity_id] = _snapshot_entity(ct, entity_id)
        return snapshots[entity_id]

    for position in ct.get_nearby_tiles():
        observations.append(
            TileObservation(
                position=position,
                environment=ct.get_tile_env(position),
                building=snapshot(ct.get_tile_building_id(position)),
                builder_bot=snapshot(ct.get_tile_builder_bot_id(position)),
            )
        )
    return observations


def _snapshot_entity(ct: Controller, entity_id: int) -> EntitySnapshot:
    entity_type = ct.get_entity_type(entity_id)
    direction = (
        ct.get_direction(entity_id)
        if entity_type in _DIRECTIONAL_ENTITIES
        else None
    )
    if entity_type in _STORAGE_ENTITIES:
        stored_resource = ct.get_stored_resource(entity_id)
        stored_resource_id = ct.get_stored_resource_id(entity_id)
    else:
        stored_resource = None
        stored_resource_id = None

    return EntitySnapshot(
        id=entity_id,
        position=ct.get_position(entity_id),
        entity_type=entity_type,
        team=ct.get_team(entity_id),
        hp=ct.get_hp(entity_id),
        max_hp=ct.get_max_hp(entity_id),
        direction=direction,
        stored_resource=stored_resource,
        stored_resource_id=stored_resource_id,
    )


def _apply_observations(
    tiles: dict[Position, TileState],
    observations: Iterable[TileObservation],
    source: DiscoverySource,
) -> None:
    for observation in observations:
        existing = tiles.get(observation.position)
        if existing is not None and _SOURCE_PRIORITY[existing.source] > _SOURCE_PRIORITY[source]:
            # A registry update can refresh a directly seen tile, but it must not
            # replace more authoritative ground or potentially newer occupancy.
            if existing.environment == observation.environment:
                existing.rounds_since_last_seen = 0
            continue

        tiles[observation.position] = TileState(
            environment=observation.environment,
            fixed_core=(
                observation.fixed_core if observation.occupancy_known else None
            ),
            building=(observation.building if observation.occupancy_known else None),
            builder_bot=(
                observation.builder_bot if observation.occupancy_known else None
            ),
            occupancy_known=observation.occupancy_known,
            source=source,
            rounds_since_last_seen=0,
        )


def _inferred_map_conflicts(
    observations: Iterable[TileObservation], match_state: MapMatchState
) -> bool:
    name = match_state.inferred_map_name
    if name is None:
        return False
    known_map = match_state.known_maps[name]
    return any(not _observation_matches_map(obs, known_map) for obs in observations)


def _observation_matches_map(
    observation: TileObservation, known_map: KnownMap
) -> bool:
    position = observation.position
    if not (0 <= position.x < known_map.width and 0 <= position.y < known_map.height):
        return False
    if known_map.environment_at(position) != observation.environment:
        return False
    if observation.occupancy_known:
        return known_map.cores.get(position) == observation.fixed_core
    return True


def _reject_inferred_map(
    tiles: dict[Position, TileState], match_state: MapMatchState
) -> None:
    name = match_state.inferred_map_name
    if name is not None:
        match_state.rejected_maps.add(name)
    match_state.inferred_map_name = None
    match_state.candidate_names.clear()
    for position in [
        position
        for position, tile in tiles.items()
        if tile.source == DiscoverySource.KNOWN_MAP
    ]:
        del tiles[position]


def _update_candidates(
    tiles: Mapping[Position, TileState],
    match_state: MapMatchState,
    width: int,
    height: int,
) -> None:
    candidates: set[str] = set()
    for name, known_map in match_state.known_maps.items():
        if name in match_state.rejected_maps:
            continue
        if known_map.width != width or known_map.height != height:
            continue
        if _known_map_matches_evidence(known_map, tiles):
            candidates.add(name)
    match_state.candidate_names = candidates


def _known_map_matches_evidence(
    known_map: KnownMap, tiles: Mapping[Position, TileState]
) -> bool:
    for position, tile in tiles.items():
        if tile.source == DiscoverySource.KNOWN_MAP:
            continue
        if not (0 <= position.x < known_map.width and 0 <= position.y < known_map.height):
            return False
        if known_map.environment_at(position) != tile.environment:
            return False
        if tile.occupancy_known and known_map.cores.get(position) != tile.fixed_core:
            return False
    return True


def _fill_from_known_map(
    tiles: dict[Position, TileState], known_map: KnownMap
) -> None:
    for y, row in enumerate(known_map.environments):
        for x, environment in enumerate(row):
            position = Position(x, y)
            if position in tiles:
                continue
            tiles[position] = TileState(
                environment=environment,
                fixed_core=known_map.cores.get(position),
                building=None,
                builder_bot=None,
                occupancy_known=False,
                source=DiscoverySource.KNOWN_MAP,
                rounds_since_last_seen=None,
            )


@lru_cache(maxsize=1)
def load_known_maps() -> Mapping[str, KnownMap]:
    """Parse and cache every .map26 file bundled with the bot."""

    maps_directory = Path(__file__).resolve().parent.parent / "maps"
    paths = sorted(maps_directory.glob("*.map26"))
    if not paths:
        raise RuntimeError(f"No bundled .map26 files found in {maps_directory}")
    return {path.stem: _parse_map_file(path) for path in paths}


def _parse_map_file(path: Path) -> KnownMap:
    fields = list(_protobuf_fields(path.read_bytes()))
    width = _required_varint(fields, 1)
    height = _required_varint(fields, 2)

    rows: list[tuple[Environment, ...]] = []
    core_records: list[tuple[Team, Position]] = []
    for field_number, wire_type, value in fields:
        if field_number == 3 and wire_type == 2:
            row_fields = list(_protobuf_fields(value))
            raw_tiles = _required_bytes(row_fields, 1)
            if len(raw_tiles) != width:
                raise ValueError(f"{path}: row width {len(raw_tiles)} != {width}")
            try:
                rows.append(tuple(_TILE_VALUES[tile] for tile in raw_tiles))
            except KeyError as error:
                raise ValueError(f"{path}: unknown environment value {error.args[0]}") from error
        elif field_number == 4 and wire_type == 2:
            core_fields = list(_protobuf_fields(value))
            raw_team = _required_varint(core_fields, 1)
            position_fields = list(
                _protobuf_fields(_required_bytes(core_fields, 3))
            )
            core_records.append(
                (
                    _TEAM_VALUES[raw_team],
                    Position(
                        _required_varint(position_fields, 1),
                        _required_varint(position_fields, 2),
                    ),
                )
            )

    if len(rows) != height:
        raise ValueError(f"{path}: row count {len(rows)} != {height}")

    cores: dict[Position, FixedCore] = {}
    for team, anchor in core_records:
        core = FixedCore(team, anchor)
        for dy in range(2):
            for dx in range(2):
                cores[Position(anchor.x + dx, anchor.y + dy)] = core

    return KnownMap(
        name=path.stem,
        width=width,
        height=height,
        environments=tuple(rows),
        cores=cores,
    )


def _required_varint(
    fields: Iterable[tuple[int, int, int | bytes]], field_number: int
) -> int:
    for number, wire_type, value in fields:
        if number == field_number and wire_type == 0:
            assert isinstance(value, int)
            return value
    raise ValueError(f"Missing protobuf varint field {field_number}")


def _required_bytes(
    fields: Iterable[tuple[int, int, int | bytes]], field_number: int
) -> bytes:
    for number, wire_type, value in fields:
        if number == field_number and wire_type == 2:
            assert isinstance(value, bytes)
            return value
    raise ValueError(f"Missing protobuf bytes field {field_number}")


def _protobuf_fields(data: bytes) -> Iterable[tuple[int, int, int | bytes]]:
    offset = 0
    while offset < len(data):
        key, offset = _read_varint(data, offset)
        field_number = key >> 3
        wire_type = key & 0x07
        if wire_type == 0:
            value, offset = _read_varint(data, offset)
        elif wire_type == 1:
            value = data[offset : offset + 8]
            offset += 8
        elif wire_type == 2:
            length, offset = _read_varint(data, offset)
            value = data[offset : offset + length]
            offset += length
        elif wire_type == 5:
            value = data[offset : offset + 4]
            offset += 4
        else:
            raise ValueError(f"Unsupported protobuf wire type {wire_type}")
        if offset > len(data):
            raise ValueError("Truncated protobuf field")
        yield field_number, wire_type, value


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
        if shift >= 64:
            raise ValueError("Protobuf varint is too long")
    raise ValueError("Truncated protobuf varint")
