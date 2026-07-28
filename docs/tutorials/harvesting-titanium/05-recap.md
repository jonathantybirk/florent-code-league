# Harvesting Titanium · Step 5 of 5

Source: https://game.code.florent.vc/tutorials/harvesting-titanium/05-recap

## Recap & checkpoint

You now have a bot that:

- Reads the team's shared titanium balance with `ct.get_global_resources()`
- Seeks out visible ore using `Environment.ORE_TITANIUM`, `pos.distance_squared()`, and `pos.direction_to()`
- Builds a Harvester on an orthogonally adjacent ore tile with `ct.can_build_harvester` / `ct.build_harvester`
- Reads scaling costs with `ct.get_scale_percent()` and `ct.get_*_cost()`

But it still ends this tutorial with zero mined titanium reaching its balance, no matter how many Harvesters it builds. That's not a loose end we forgot — a Harvester's income is physically stranded unless something routes it to a sink. That "something" is a Conveyor.

Next up: [Logistics: Conveyors & Splitters](../conveyors-logistics/01-why-routing-matters.md) — finally get that titanium moving.
