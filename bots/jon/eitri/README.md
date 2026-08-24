# eitri

A modular, atlas-planned four-builder mining opening. Terrain identification,
network planning, crew assignment, Core spawning, pathfinding, and per-builder
execution are separate modules. `crew.assign(..., count)` supports every crew
size from one through four.

The executor builds each conveyor tree from the Core outward. Finished builders
track globally completed lanes and move only when they occupy a tile needed by
unfinished construction; they take one step off that work rather than walking
back through the active network. Completed Harvester tiles are permanent BFS
obstacles, preventing repeated routes through buildings.

Against `bots/common/donothingbot`, across all 53 atlas maps at 1,000 rounds:

- total collected titanium: 1,506,850, up from 1,469,620;
- execution: 94% of the planner's perfect schedule, up from 91%;
- nine maps improve and none regress;
- Sweden improves from 2,240 to 15,200 Ti (14% to 94% execution).
- Bridge improves from 9,500 to 14,140 Ti (66% to 98% execution).

The benchmark separates executor quality from planner quality:

```bash
uv run python tools/openbench.py --bot bots/jon/eitri
```

The planner is not yet terrain-optimal: its chosen networks average 85% of the
throughput ceiling. That remaining gap is planner work, not hidden executor
optimality.
