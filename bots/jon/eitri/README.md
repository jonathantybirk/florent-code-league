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

The network planner evaluates five cheap deterministic deposit orders (near,
far, interleaved, and both coordinate sweeps) instead of trusting one greedy
Steiner insertion. Alternative orders must predict at least 100 Ti more than
the original two-order baseline, preventing plan churn for rounding noise.

Against `bots/common/donothingbot`, across all 53 atlas maps at 1,000 rounds:

- total collected titanium: 1,625,170, up from 1,469,620;
- execution: 95% of the planner's perfect schedule, up from 91%;
- planner quality: 90% of the capacity-aware ceiling, up from 85%;
- 35 maps improve and none regress;
- Sweden improves from 2,240 to 15,200 Ti (14% to 94% execution).
- Bridge improves from 9,500 to 14,140 Ti (66% to 98% execution).

The benchmark separates executor quality from planner quality:

```bash
uv run python tools/openbench.py --bot bots/jon/eitri
```

The planner is not yet terrain-optimal: its chosen networks average 90% of the
throughput ceiling. That remaining gap is planner work, not hidden executor
optimality.
