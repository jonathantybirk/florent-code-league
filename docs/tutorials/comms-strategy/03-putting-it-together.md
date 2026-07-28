# Coordination & Strategy · Step 3 of 4

Source: https://game.code.florent.vc/tutorials/comms-strategy/03-putting-it-together

## Putting it all together

Everything from Tutorials 1 through 5 fits into one bot: sense the map, harvest ore, route it to the Core with a conveyor chain that ends in a Splitter, use the Splitter's spare side to feed a Gunner, and share ore locations over the Store so Builder Bots aren't all working blind.

> **Correction vs. the official docs.** `_build_gunner` below uses `pos.cardinal_direction_to(self.splitter_pos)` on the published page. **This method does not exist** in the installed `fcode` engine (confirmed by direct call at runtime — raises `AttributeError`). Corrected below to `pos.direction_to(...)` with a rotate-left/right fallback.

```python
import random

from fcode import Controller, Direction, Environment, EntityType, Position

CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]

SLOT_ORE_X = 0
SLOT_ORE_Y = 1

def in_bounds(ct: Controller, pos: Position) -> bool:
    return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()

class Player:
    def __init__(self):
        self.core_tile: Position | None = None
        self.harvester_pos: Position | None = None
        self.chain_done = False
        self.gunner_built = False
        self.gunner_side: Direction | None = None
        self.splitter_pos: Position | None = None

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self._run_core(ct)
        elif etype == EntityType.BUILDER_BOT:
            self._run_builder(ct)
        elif etype == EntityType.GUNNER:
            self._run_gunner(ct)

    def _run_core(self, ct: Controller) -> None:
        for pos in ct.get_nearby_tiles(dist_sq=2):
            if ct.can_spawn(pos):
                ct.spawn_builder(pos)
                break

    def _run_builder(self, ct: Controller) -> None:
        pos = ct.get_position()
        if self.core_tile is None:
            for tile in ct.get_nearby_tiles():
                bid = ct.get_tile_building_id(tile)
                if bid is not None and ct.get_entity_type(bid) == EntityType.CORE:
                    self.core_tile = tile
                    break

        self._share_ore(ct, pos)

        if self.harvester_pos is None:
            self._seek_and_harvest(ct, pos)
        elif not self.chain_done and self.core_tile is not None:
            self._lay_conveyor_toward_core(ct, pos)
        elif not self.gunner_built and self.splitter_pos is not None and self.gunner_side is not None:
            self._build_gunner(ct)

    def _share_ore(self, ct: Controller, pos: Position) -> None:
        for tile in ct.get_nearby_tiles():
            if ct.get_tile_env(tile) == Environment.ORE_TITANIUM and ct.get_tile_building_id(tile) is None:
                ct.write_store(SLOT_ORE_X, tile.x)
                ct.write_store(SLOT_ORE_Y, tile.y)
                return

    def _seek_and_harvest(self, ct: Controller, pos: Position) -> None:
        for d in CARDINALS:
            tile = pos.add(d)
            if not in_bounds(ct, tile):
                continue
            if ct.get_tile_env(tile) == Environment.ORE_TITANIUM and ct.can_build_harvester(tile):
                ct.build_harvester(tile)
                self.harvester_pos = tile
                return

        ore_tiles = [t for t in ct.get_nearby_tiles() if ct.get_tile_env(t) == Environment.ORE_TITANIUM]
        if ore_tiles:
            target = min(ore_tiles, key=lambda t: pos.distance_squared(t))
        else:
            shared_x, shared_y = ct.read_store(SLOT_ORE_X), ct.read_store(SLOT_ORE_Y)
            target = Position(shared_x, shared_y) if (shared_x or shared_y) else None

        if target is not None:
            direction = pos.direction_to(target)
            if ct.can_move(direction):
                ct.move(direction)
                return

        open_dirs = [
            d for d in CARDINALS
            if ct.can_move(d) and ct.get_tile_env(pos.add(d)) == Environment.EMPTY
        ]
        move_options = open_dirs or [d for d in CARDINALS if ct.can_move(d)]
        if move_options:
            ct.move(random.choice(move_options))

    def _pick_direction(self, ct: Controller, pos: Position) -> Direction | None:
        assert self.core_tile is not None
        dx = self.core_tile.x - pos.x
        dy = self.core_tile.y - pos.y
        if dx != 0:
            d = Direction.EAST if dx > 0 else Direction.WEST
            if ct.can_move(d):
                return d
        if dy != 0:
            d = Direction.SOUTH if dy > 0 else Direction.NORTH
            if ct.can_move(d):
                return d
        return None

    def _lay_conveyor_toward_core(self, ct: Controller, pos: Position) -> None:
        # Builder bots can only build on an orthogonally adjacent tile now,
        # never their own -- so we check every tile we could build on for
        # the Core first, one tile further out than before, since the
        # final relay (the Splitter) can no longer be built by standing on
        # it either.
        for d in CARDINALS:
            next_pos = pos.add(d)
            if not in_bounds(ct, next_pos):
                continue
            for d2 in CARDINALS:
                neighbor = next_pos.add(d2)
                if not in_bounds(ct, neighbor):
                    continue
                bid = ct.get_tile_building_id(neighbor)
                if bid is not None and ct.get_entity_type(bid) == EntityType.CORE:
                    if ct.can_build_splitter(next_pos, d2):
                        ct.build_splitter(next_pos, d2)
                        self.splitter_pos = next_pos
                        for side in CARDINALS:
                            if side != d2 and side != d2.opposite():
                                self.gunner_side = side
                                break
                    self.chain_done = True
                    return

        direction = self._pick_direction(ct, pos)
        if direction is None:
            self.chain_done = True
            return

        next_pos = pos.add(direction)
        if ct.can_build_conveyor(next_pos, direction):
            ct.build_conveyor(next_pos, direction)
        if ct.can_move(direction):
            ct.move(direction)

    def _build_gunner(self, ct: Controller) -> None:
        assert self.splitter_pos is not None and self.gunner_side is not None
        pos = ct.get_position()
        if pos != self.splitter_pos:
            # The Splitter sits one tile ahead of us -- we stopped short of
            # it on purpose, since it can't be built while standing on it.
            # Splitters are bot-passable, so just walk onto it like any
            # other tile; the Gunner build happens next round from there.
            desired = pos.direction_to(self.splitter_pos)
            for d in (desired, desired.rotate_left(), desired.rotate_right()):
                if ct.can_move(d):
                    ct.move(d)
                    return
            return

        gunner_pos = self.splitter_pos.add(self.gunner_side)
        if in_bounds(ct, gunner_pos) and ct.can_build_gunner(gunner_pos, self.gunner_side):
            ct.build_gunner(gunner_pos, self.gunner_side)
        self.gunner_built = True

    def _run_gunner(self, ct: Controller) -> None:
        target = ct.get_gunner_target()
        if target is not None and ct.can_fire(target):
            ct.fire(target)
```

Nothing here is new mechanically — every piece was introduced and tested in an earlier tutorial. What's new is the state machine tying them together: each Builder Bot works through harvest → route → defend in order, tracked with a handful of instance attributes (`harvester_pos`, `chain_done`, `gunner_built`, ...) that persist for that unit's entire lifetime, exactly like `self.num_spawned` did all the way back in Tutorial 1.

One genuinely new wrinkle: because the Splitter is now built from one tile back rather than by standing on it, `_build_gunner` has to walk the bot onto the Splitter's tile first (Splitters are bot-passable) before it can build the Gunner beside it — the same "a build blocks this round's move, so wait a round" pattern you've already seen in `_lay_conveyor_toward_core`. The Gunner sits on `gunner_side`, one of the Splitter's three output sides (the other two being the Core-facing side and the opposite of that), so it receives a stack — and ammo — whenever the Splitter's round-robin reaches that side.

Be honest with yourself about what this bot isn't: it's not optimized, it doesn't handle every map layout, and independent Builder Bots can still collide with each other's plans. That's fine. It's a real, working demonstration of every mechanic in the game, and a legitimate base to build a stronger strategy from.

## Try it

```
fcode run starter starter
fcode watch replay.replay26
```

What you should see: Harvesters, conveyor chains, Splitters, and Gunners all appearing over the course of the match, Builder Bots occasionally converging on a shared ore target, and — on at least some runs — a Gunner that actually fires because its ammo pipeline is connected. Run it a few times with different seeds; results will vary, and that's expected.

Next: where to take this from here.
