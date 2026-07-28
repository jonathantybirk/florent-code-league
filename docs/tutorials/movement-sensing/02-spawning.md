# Your First Bot: Movement & Sensing · Step 2 of 5

Source: https://game.code.florent.vc/tutorials/movement-sensing/02-spawning

## Spawning a Builder Bot

The Core is stationary — it can't move or attack. Its one job is spawning Builder Bots, your mobile workforce. Spawning costs titanium and only works on a tile within the Core's spawn range.

```python
from fcode import Controller, EntityType

class Player:
    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            for pos in ct.get_nearby_tiles(dist_sq=2):
                if ct.can_spawn(pos):
                    ct.spawn_builder(pos)
                    break
```

`ct.get_nearby_tiles(dist_sq=2)` returns every tile within squared-distance 2 of the Core — that's exactly the Core's spawn range: the ring of tiles orthogonally or diagonally adjacent to its 2×2 footprint. We loop over those candidate tiles, and for each one ask `ct.can_spawn(pos)`: is it empty, in range, and can we afford a Builder Bot right now? The first tile that passes gets `ct.spawn_builder(pos)`, and we `break` so we only spawn one bot per round.

Almost every build action in the game follows this same `can_X()` / `X()` pairing — check first, then act. The `can_*` checks never raise; the action methods (`spawn_builder`, `move`, `build_harvester`, ...) raise a `GameError` if you call them somewhere illegal, so checking first keeps your bot from crashing mid-match.

## Try it

Replace `bots/starter/main.py` with the code above, then:

```
fcode run starter starter
fcode watch replay.replay26
```

What you should see: a Builder Bot appears next to each Core in round 1 and just sits there (we haven't given it a `run()` branch yet, so it does nothing). The unit count in the match summary should read 1 or more per side.

Next: make that Builder Bot actually move.
