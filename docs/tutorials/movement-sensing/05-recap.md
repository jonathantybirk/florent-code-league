# Your First Bot: Movement & Sensing · Step 5 of 5

Source: https://game.code.florent.vc/tutorials/movement-sensing/05-recap

## Recap & checkpoint

You now have a bot that:

- Dispatches on `ct.get_entity_type()` to handle each unit type separately
- Spawns a Builder Bot from the Core within its spawn range (`ct.get_nearby_tiles(dist_sq=2)`, `ct.can_spawn`, `ct.spawn_builder`)
- Moves that Builder Bot around with `Direction`, `ct.can_move`, `ct.move`
- Reads the map with `ct.get_tile_env()` to avoid walls and prefer open ground
- Debugs itself with `print()` and `ct.draw_indicator_dot()`

Every mechanic here — the `run()` dispatch pattern, the `can_X()` / `X()` check-then-act convention, and vision-based sensing — is used identically everywhere else in the game. Turrets, harvesters, and conveyors all build on exactly this foundation.

The bot from step 4 is your starting point for the next tutorial. Keep it around — you'll extend `_run_builder` rather than starting from scratch.

Next up: [Harvesting Titanium](../harvesting-titanium/01-the-titanium-economy.md) — put that wandering Builder Bot to work mining ore and growing your economy.
