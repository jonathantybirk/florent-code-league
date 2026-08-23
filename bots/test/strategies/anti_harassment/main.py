"""Anti-harassment: notice an enemy Builder Bot actively working over known
friendly infrastructure, and work out which of its own escape tiles an
allied Builder Bot should occupy to deny it a move.

Blocking, not fighting: bots/test/builder_combat_probe empirically settled
that a Builder Bot's Attack can never damage another Builder Bot -- not
directly (can_fire() is False against bare ground), and not as collateral
when the target is standing on a building being attacked (fire succeeds,
the building takes it, the co-located Builder Bot's HP never moves). So an
allied Builder Bot can never speed up a kill by dealing damage itself --
only a covering Gunner/Sentinel can actually kill a harasser. What an
allied Builder Bot *can* do is occupy a tile: "Tiles occupied by another
Builder Bot" are impassable (game-rules-builder-bot.txt), so parking one
on a harasser's escape route removes that move option outright, buying the
covering turret more consecutive clean shots before the harasser can juke
out of its line of fire -- the exact evasion the turret alone can't stop
(a Gunner's rotate-to-follow costs 10 Ti + a round that isn't spent
firing; a Sentinel can't rotate at all).

Reuses bots/test/strategies/defensive's turret threat geometry
(EnemyTurret/is_safe) to work out which of the harasser's cardinal
neighbours are already inside a covering turret's kill zone: the geometry
is symmetric -- a turret's threat envelope doesn't care which side built
it -- so a friendly turret is described with the exact same EnemyTurret
dataclass used elsewhere for enemy ones (see _read_turret below). Loaded
by direct file path (see _load_defensive), the same cross-bots/test/
import trick bots/test/splitter_probe uses to reuse bots/test/econ --
plain package-relative imports aren't available given the engine's flat
per-directory sys.path (see common/toolbox.py's module docstring).
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from fcode import Controller, Direction, EntityType, Environment, Position

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
_PASSABLE_BUILDING_TYPES = (EntityType.CONVEYOR, EntityType.SPLITTER)
_TURRET_TYPES = (EntityType.GUNNER, EntityType.SENTINEL, EntityType.LAUNCHER)


def _load_defensive():
    path = Path(__file__).resolve().parent.parent / "defensive" / "main.py"
    spec = importlib.util.spec_from_file_location("defensive_lib", path)
    module = importlib.util.module_from_spec(spec)
    # dataclass's field-type resolution (defensive.main uses `from __future__
    # import annotations`, so annotations are strings looked up lazily) needs
    # this module registered in sys.modules *before* exec_module runs --
    # otherwise dataclasses.dataclass's sys.modules.get(cls.__module__) call
    # returns None and it raises AttributeError. A normal `import` does this
    # registration for you; module_from_spec alone doesn't.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


defensive = _load_defensive()


def _try(fn):
    try:
        return fn(), None
    except Exception as e:
        return None, e


def _in_bounds(ct: Controller, pos: Position) -> bool:
    return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()


@dataclass(frozen=True)
class FriendlyInfra:
    """One tile this team expects to have built something on -- Conveyor,
    Splitter, or Harvester. Nothing here populates this list; a caller
    supplies it from its own build history, same division of labor as
    econ2's self.harvester_positions / defensive's EnemyTurret."""

    position: Position
    etype: EntityType


def find_active_harassers(ct: Controller, infra: Iterable[FriendlyInfra]) -> dict[int, Position]:
    """Enemy Builder Bot ids currently standing on, or orthogonally
    adjacent to, a tile in `infra` -- mapped to their current position.
    Only ever looks at tiles currently in this unit's own vision; an
    infra tile (or the enemy on it) outside vision is skipped entirely,
    not reported as clear -- "not currently visible" and "not being
    harassed" are different things, the same caution econ2/defensive both
    call out about their own cached state.
    """
    my_team = ct.get_team()
    found: dict[int, Position] = {}
    for f in infra:
        candidates = [f.position] + [f.position.add(d) for d in CARDINALS]
        for tile in candidates:
            if not _in_bounds(ct, tile) or not ct.is_in_vision(tile):
                continue
            bid = ct.get_tile_builder_bot_id(tile)
            if bid is not None and ct.get_team(bid) != my_team:
                found[bid] = tile
    return found


def _passable_for_builder(ct: Controller, tile: Position) -> bool:
    """Mirrors the Passable/Impassable list in
    game-rules-builder-bot.txt: WALL, another Builder Bot, and any
    building except Conveyor/Splitter all block a Builder Bot's move."""
    if ct.get_tile_env(tile) == Environment.WALL:
        return False
    if ct.get_tile_builder_bot_id(tile) is not None:
        return False
    bid = ct.get_tile_building_id(tile)
    if bid is None:
        return True
    return ct.get_entity_type(bid) in _PASSABLE_BUILDING_TYPES


def _read_turret(ct: Controller, turret_id: int):
    """Build a defensive.EnemyTurret describing turret_id's current
    position/type/facing, read live rather than cached -- a Gunner's
    facing can change (see defensive.threatens's docstring on why it
    ignores a cached Gunner direction entirely), so this always re-reads
    it fresh. None if turret_id isn't currently a queryable turret (out of
    vision, destroyed since, or not actually a turret)."""
    pos, err = _try(lambda: ct.get_position(turret_id))
    if err is not None:
        return None
    etype, err = _try(lambda: ct.get_entity_type(turret_id))
    if err is not None or etype not in _TURRET_TYPES:
        return None
    direction = None
    if etype in (EntityType.GUNNER, EntityType.SENTINEL):
        direction, err = _try(lambda: ct.get_direction(turret_id))
        if err is not None:
            direction = None
    return defensive.EnemyTurret(position=pos, etype=etype, direction=direction)


def escape_tiles(ct: Controller, harasser_pos: Position, friendly_turret_ids: Iterable[int]) -> list[Position]:
    """Which of harasser_pos's (in-bounds, Builder-Bot-passable) cardinal
    neighbours are NOT currently threatened by any of friendly_turret_ids
    -- i.e. where the harasser could step to get clear of every covering
    turret. An empty list means it's already boxed in: nothing to block,
    the turret(s) alone will finish it. Turrets not currently readable
    (out of vision, etc. -- see _read_turret) are silently skipped, which
    biases toward reporting MORE escape tiles than truly exist rather than
    fewer -- see Limitations in the README for why that's the safer
    direction for a blocking decision (worst case: an unnecessary block),
    versus assuming coverage that isn't really there (worst case: the
    harasser walks straight out).
    """
    turrets = [t for t in (_read_turret(ct, tid) for tid in friendly_turret_ids) if t is not None]
    escapes = []
    for d in CARDINALS:
        tile = harasser_pos.add(d)
        if not _in_bounds(ct, tile) or not _passable_for_builder(ct, tile):
            continue
        if defensive.is_safe(tile, turrets):
            escapes.append(tile)
    return escapes


def best_blocking_tile(escape: Sequence[Position], blocker_pos: Position) -> Position | None:
    """The escape tile closest to blocker_pos -- the one it can reach
    soonest -- or None if there's nothing to block (see escape_tiles).
    Doesn't account for a second blocker or for the harasser moving
    before the block lands; see Limitations.
    """
    if not escape:
        return None
    return min(escape, key=lambda t: blocker_pos.distance_squared(t))
