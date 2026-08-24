# eitri

A modular, atlas-planned four-builder mining opening. Terrain identification,
network planning, crew assignment, Core spawning, pathfinding, and per-builder
execution are separate modules. `crew.assign(..., count)` supports every crew
size from one through four.

The executor builds each conveyor tree from the Core outward. Finished builders
clear unfinished construction immediately. They also reserve every crew
member's between-lane transit corridor and clear one only after seeing the same
friendly Builder stuck beside them for three rounds. That fixes permanent jams
without moving for ordinary passing traffic. Completed Harvester tiles are
permanent BFS obstacles, preventing repeated routes through buildings.

The network planner evaluates six cheap deterministic deposit orders (near,
far, both interleaves, and both coordinate sweeps) instead of trusting one greedy
Steiner insertion. Alternative orders must predict at least 300 Ti more than
the original two-order baseline, preventing plan churn for rounding noise.

Against `bots/common/donothingbot`, across all 53 atlas maps at 1,000 rounds:

- total collected titanium: 1,652,190, up from 1,469,620;
- execution: 96% of the planner's perfect schedule, up from 91%;
- planner quality: 90% of the capacity-aware ceiling, up from 85%;
- 35 maps improve and none regress;
- Sweden improves from 2,240 to 15,200 Ti (14% to 94% execution).
- Bridge improves from 9,500 to 14,140 Ti (66% to 98% execution).
- Archipelago improves from 24,490 to 38,800 Ti.
- Bifrost improves from 22,420 to 32,380 Ti.
- Duel improves from 12,160 to 14,580 Ti (83% to 99% execution).
- Crossfire improves from 16,890 to 21,470 Ti (77% to 98% execution).
- Lighthouse improves from 24,220 to 28,910 Ti (83% to 98% execution).

The benchmark separates executor quality from planner quality:

```bash
uv run python tools/openbench.py --bot bots/jon/eitri
```

The planner is not yet terrain-optimal: its chosen networks average 90% of the
throughput ceiling. That remaining gap is planner work, not hidden executor
optimality.
