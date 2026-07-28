# Building an Army: Turrets & Combat · Step 3 of 5

Source: https://game.code.florent.vc/tutorials/turrets-combat/03-the-ammo-gap

## The ammo gap

> **Correction vs. the official docs.** The published page fixes the silent Gunner from the previous step with `ct.convert_ammo(amount)` at the Core, describing ammunition as a team-wide balance filled 1:1 from titanium. **None of that exists** in the installed `fcode` engine — confirmed by enumerating the real `Controller` object at runtime (`convert_ammo`/`can_convert_ammo`/`get_global_ammo` aren't there; calling any of them raises `AttributeError`). Ammo is titanium, held locally by each turret, delivered the same way you'd deliver titanium to anything else: **a Conveyor**. The fix below is nowhere near the Core — it's connecting the Harvester and Gunner from the previous step with a Conveyor, exactly like routing a Harvester's output to your Core in the [logistics tutorial](../conveyors-logistics/01-why-routing-matters.md).

The Harvester and Gunner from step 2 were both adjacent to the Builder Bot, but not to each other — one tile apart, with the bot standing between them. A Conveyor there, facing from the Harvester's side toward the Gunner's side, closes that gap. The bot has to move off that tile first (Builder Bots can't build on their own tile), then build the Conveyor from next door:

```python
import random

from fcode import Controller, Direction, Environment, EntityType, Position

CARDINALS = [Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST]

def in_bounds(ct: Controller, pos: Position) -> bool:
    return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()

class Player:
    def __init__(self):
        self.built = False
        self.gap_pos: Position | None = None
        self.wired = False

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            for pos in ct.get_nearby_tiles(dist_sq=2):
                if ct.can_spawn(pos):
                    ct.spawn_builder(pos)
                    break
        elif etype == EntityType.BUILDER_BOT:
            self._run_builder(ct)
        elif etype == EntityType.GUNNER:
            self._run_gunner(ct)

    def _run_builder(self, ct: Controller) -> None:
        pos = ct.get_position()

        if not self.built:
            harvester_pos = pos.add(Direction.NORTH)
            gunner_pos = pos.add(Direction.SOUTH)
            if not in_bounds(ct, harvester_pos) or not in_bounds(ct, gunner_pos):
                self._explore(ct, pos)
                return

            if ct.get_tile_env(harvester_pos) == Environment.ORE_TITANIUM:
                if ct.can_build_harvester(harvester_pos):
                    ct.build_harvester(harvester_pos)
                if ct.can_build_gunner(gunner_pos, Direction.SOUTH):
                    ct.build_gunner(gunner_pos, Direction.SOUTH)
                    self.built = True
                    self.gap_pos = pos
                return

            self._explore(ct, pos)
            return

        if self.wired:
            return

        # Step off the gap tile, then build a Conveyor there facing south:
        # it takes input from the Harvester (its north side) and delivers
        # straight into the Gunner (its south side).
        if pos == self.gap_pos:
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
            return

        if ct.can_build_conveyor(self.gap_pos, Direction.SOUTH):
            ct.build_conveyor(self.gap_pos, Direction.SOUTH)
            self.wired = True

    def _explore(self, ct: Controller, pos: Position) -> None:
        open_dirs = [
            d for d in CARDINALS
            if ct.can_move(d) and ct.get_tile_env(pos.add(d)) == Environment.EMPTY
        ]
        move_options = open_dirs or [d for d in CARDINALS if ct.can_move(d)]
        if move_options:
            ct.move(random.choice(move_options))

    def _run_gunner(self, ct: Controller) -> None:
        if ct.get_current_round() % 100 == 0:
            print(f"round {ct.get_current_round()}: ammo = {ct.get_ammo_amount()}")
        target = ct.get_gunner_target()
        if target is not None and ct.can_fire(target):
            ct.fire(target)
```

Once the Conveyor is in place, the Harvester's next output stack travels one tile onto the Conveyor, then one more tile into the Gunner — arriving as ammo, ready to spend on its next shot. `ct.can_build_conveyor` / `ct.can_move` gate everything the same way every other check-then-act call in these tutorials has, so nothing here is a new pattern — just the same delivery problem you've already solved once, applied to a turret instead of a Core.

## Try it

```
fcode run starter starter
fcode watch replay.replay26
```

What you should see: the printed ammo line stays at 0 for a while (however long it takes the bot to finish building and the first Harvester stack to travel the two-tile path), then starts climbing as stacks arrive, and dips by 2 each time the Gunner actually fires. In the visualiser, hover the Gunner to see its own held ammo, separate from your team's titanium balance.

Next: give your Builder Bots a way to defend themselves too.
