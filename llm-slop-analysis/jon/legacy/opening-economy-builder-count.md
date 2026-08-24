# Opening economy: one to four initial Builders

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

Research/model pass: 31 July 2026.

> **Superseded in part by
> [`opening-economy-revision.md`](opening-economy-revision.md)**, an independent
> engine-backed rebuild. It corrects the route-timing model, the cardinal-only
> ownership metric, and the choice of *stored* rather than *delivered* titanium
> as the ranking metric, and it finds trunk capacity to be the dominant opening
> constraint.
>
> **Timing correction:** the comparative results below were produced before a
> direct `fcode 2.2.0` probe established that Builders can build on their own
> tile, build diagonally, move diagonally, and build plus move in one round.
> The old alternating-round formulas are not implementation guidance. The
> current engine-backed planner is `analysis/econ/planner.py`, and the measured
> rules are recorded in `../meta/mechanics-audit.md`.

This analysis asks how many Builders should be bought immediately if the goal
is to connect the uncontested ore on the 15 bundled maps. It is backed by the
reproducible model in `scripts/analyze_opening_economy.py`; raw results live in
`analysis/opening-economy/`.

## Executive result

One Builder is not universally optimal.

Under a perfect-map-information benchmark that connects every strictly
own-side ore with an independent shortest conveyor line:

| Initial Builders | Avg stored, r100 | Avg stored, r250 | Avg stored, r500 | Avg stored, r1000 |
|---:|---:|---:|---:|---:|
| 1 | 1,141 | 3,157 | 6,991 | 14,658 |
| 2 | 1,127 | 3,407 | 7,239 | 14,905 |
| 3 | 1,123 | **3,426** | **7,256** | **14,923** |
| 4 | 1,071 | 3,373 | 7,204 | 14,871 |

Three Builders are the best average long-lived opening in this benchmark, but
the margin over two is small. One Builder retains slightly more immediately
spendable titanium around round 100. Four Builders mine the most by every
reported horizon but usually fail to recover their higher purchase and scaling
cost in stored titanium.

When the target set is restricted to safe ore visible from the Core at round
zero, one Builder has the highest cross-map average stored titanium at every
reported horizon. It wins 13 of 15 individual maps at round 250; Pinch and
Quarry favor two. Only one to four safe ores are initially visible on any
bundled map. Extra Builders must therefore explore or perform another role
quickly; buying them merely to service known ore is usually wasteful.

This distinction is central:

> Builder count should follow the number and distance of credible parallel
> jobs, not be a fixed opening constant.

## Exact early cost of Builder count

The team begins with 500 Ti. Builder Bots cost 30 Ti at base and each adds 20
percentage points to the shared scale.

| Builders bought | Marginal cost | Total Builder spend | Scale afterward | Next Harvester before belts | Next Conveyor before other builds |
|---:|---:|---:|---:|---:|---:|
| 1 | 30 | 30 | 120% | 24 | 3 |
| 2 | 36 | 66 | 140% | 28 | 4 |
| 3 | 42 | 108 | 160% | 32 | 4 |
| 4 | 48 | 156 | 180% | 36 | 5 |

The fourth Builder is not just another 48 Ti. It makes every subsequent
Harvester, conveyor, turret, and Builder more expensive. Conversely, parallel
construction can bring several 10-Ti-per-four-round income streams online much
earlier, which is why additional Builders win on ore-rich maps.

## Map definition and route math

An ore is classified as safe/uncontested when its shortest cardinal passable
path distance to our Core ring is strictly less than its distance to the enemy
Core ring. Equidistant center ores are excluded.

For an independent shortest line with `L` conveyor tiles:

- Builder `i` is spawned on round `i`;
- engine validation shows its first action occurs on round `i + 1`;
- it builds outward from the Core, alternating build and movement rounds;
- the Harvester is built on round `start + 2L`; and
- its first 10 Ti reaches the Core on `start + 3L`.

Thus, for the first job of Builder `i`:

```text
first delivery round = i + 1 + 3L
```

After finishing a line, a Builder returns along it to a Core-side staging tile
before beginning another. For one Builder with route lengths `L1..Lk`, the r-th
delivery begins at:

```text
spawn_round + 3 × sum(L1..Lr) + (r - 1) + 1
```

An adjacent interchange argument proves that ascending route length minimizes
the sum of first-delivery rounds. The script therefore enumerates every
assignment of ores to 1–4 Builder ids (at most `4^8 = 65,536`) and orders each
Builder's assigned routes shortest-first. It separately optimizes aggregate
ramp and all-lines-online makespan.

The titanium simulation includes:

- the initial 500 Ti;
- 10 passive Ti on rounds divisible by four;
- exact floored live-scale costs for every Builder, conveyor, and Harvester;
- one 10-Ti Harvester delivery every four rounds after first arrival; and
- construction delays when the shared balance cannot afford a planned build.

Four-Builder perfect-information schedules actually hit resource delays on
Aurora, Longship, Quarry, and Runestone, confirming that earned income and
build ordering matter rather than being cosmetic additions to the calculation.

## Results by map

The table selects the Builder count with the greatest stored titanium at round
250 under the fast-income schedule. `Safe/visible` is total strictly own-side
ore versus how many of those deposits the Core can see initially. Line lengths
are independent shortest conveyor counts.

| Map | Safe/visible | Line lengths | Best Builders | First delivery | All safe lines delivering | Stored r250 | Total opening capex |
|---|---:|---|---:|---:|---:|---:|---:|
| atoll | 3/2 | 2, 2, 9 | 1 | 7 | 42 | 2,695 | 155 |
| aurora | 7/2 | 3, 3, 6, 9, 13, 14, 17 | 3 | 10 | 72 | 4,039 | 771 |
| crossfire | 2/2 | 2, 2 | 1 | 7 | 14 | 2,239 | 91 |
| duel | 2/2 | 1, 2 | 1 | 4 | 11 | 2,262 | 88 |
| fjord | 6/3 | 1, 2, 2, 12, 13, 15 | 3 | 4 | 50 | 3,914 | 586 |
| hive | 4/1 | 3, 8, 8, 9 | 2 | 11 | 50 | 3,011 | 319 |
| longship | 8/2 | 3, 3, 6, 6, 9, 9, 9, 11 | 4 | 12 | 49 | 4,683 | 867 |
| pinch | 5/3 | 3, 5, 6, 7, 12 | 2 | 10 | 54 | 3,489 | 381 |
| quarry | 8/4 | 5, 6, 6, 7, 14, 15, 15, 15 | 4 | 19 | 78 | 4,157 | 1,093 |
| runestone | 8/2 | 4, 4, 7, 7, 10, 10, 11, 11 | 3 | 13 | 69 | 4,517 | 813 |
| skerry | 5/3 | 1, 2, 3, 9, 11 | 2 | 4 | 42 | 3,645 | 345 |
| sprint | 3/3 | 3, 3, 3 | 1 | 10 | 30 | 2,723 | 137 |
| strait | 6/2 | 3, 3, 6, 12, 14, 17 | 3 | 10 | 62 | 3,699 | 651 |
| twins | 6/3 | 3, 3, 4, 11, 16, 18 | 3 | 10 | 65 | 3,732 | 648 |
| vault | 4/2 | 2, 2, 15, 15 | 2 | 7 | 54 | 2,991 | 349 |

At round 250, the map-specific winners group naturally:

- **1 Builder:** Atoll, Crossfire, Duel, Sprint.
- **2 Builders:** Hive, Pinch, Skerry, Vault.
- **3 Builders:** Aurora, Fjord, Runestone, Strait, Twins.
- **4 Builders:** Longship, Quarry.

This is not simply a small/large map split. Fjord has three extremely close
ores plus three long routes, making three-way parallelism valuable. Quarry has
four initially visible safe ores plus four long routes; a four-Builder
map-aware opening pays once the Builders have distinct assignments and enough
income to avoid prolonged build stalls.

## Strategy implications

### When one Builder is viable

Prefer one initial Builder when:

- only one credible ore target is known;
- there are only two or three safe deposits in total;
- the safe lines are short enough that one Builder can finish them rapidly;
- preserving liquid titanium for defense matters before round 100; or
- the other Builders would duplicate exploration or wait without a task.

Atoll, Crossfire, Duel, and Sprint fit this profile in the benchmark.

### When two Builders are viable

Two is a strong robust default when:

- two distinct safe ores are visible immediately;
- at least four deposits are likely on our side;
- one Builder can establish the first short line while the other explores or
  begins a second branch; and
- we want redundancy against harassment without accepting 160–180% starting
  scale.

Hive, Pinch, Skerry, and Vault favor two in the map-aware benchmark.

### When three Builders are viable

Three becomes attractive when:

- the map has six or more safe deposits;
- several medium/long routes can be constructed in parallel;
- each Builder receives a disjoint exploration sector and task lease; and
- the bot commits to rapid economic expansion rather than keeping a large
  early defense reserve.

Three is the best cross-map average by round 250, but only narrowly beats two.
That small margin means a generic three-Builder opening must have substantially
better discovery and coordination than a two-Builder opening to realize the
model's advantage.

### When four Builders are viable

Four is specialized rather than generally optimal. It is justified when:

- the map is confidently identified as ore-rich;
- four useful non-overlapping jobs are already known or can be found quickly;
- long routes make parallel construction especially valuable; and
- temporary resource starvation and 180% scale are acceptable.

Longship and Quarry are the clear bundled examples. Four Builders mine more on
average, but their capex prevents that from becoming the most stored titanium
on most maps.

## Recommended adaptive opening for Jonbot

A fixed six-Builder opening is unsupported by these results. A fixed one-Builder
opening also leaves significant value on large maps. A principled policy is:

1. Spawn Builder 1 immediately.
2. If the Core sees at least two distinct safe ore targets, spawn Builder 2;
   otherwise make Builder 1 scout while preserving the option.
3. Spawn Builder 3 only after map identification or reports imply roughly six
   safe targets/long routes and the first two Builders have distinct leases.
4. Spawn Builder 4 only for a Longship/Quarry-like state: at least four credible
   parallel tasks and enough forecast cash flow to avoid a damaging build stall.
5. Never spawn a Builder without assigning a non-duplicated initial sector or
   concrete objective.

The important practical comparison is probably **two versus adaptive-three**,
not one versus four. Two pays only 66 Ti and leaves the scale at 140%; it can put
one Builder on the first income line and one on discovery. A third can be bought
after reports arrive, accepting its then-current scaled price only when the map
has demonstrated enough work to repay it.

## Limits and next modeling steps

The reported optimizer is exact for its stated independent-shortest-line model,
not for every possible Florent construction network.

It currently assumes:

- full knowledge of target ore and terrain in the `all_safe` scenario;
- optimally chosen legal spawn/staging positions;
- independent lines rather than merged conveyor trees;
- no Builder collision or enemy interference;
- no conveyor congestion; and
- a Builder returns to the Core before starting its next line.

Independent lines are intentionally conservative and executable in principle.
They can cost more than a shared tree, while shared trunks have a throughput
limit of one 10-Ti stack per round and therefore safely support at most four
10-Ti-per-four-round Harvesters. A stronger second model should optimize a
capacity-constrained directed conveyor forest and simulate exact Builder paths
on that forest.

Fog-of-war is the largest strategic gap between the perfect-information and
initial-visibility scenarios. The next implementation should therefore make
map identification and deterministic sector exploration part of the economy
policy rather than assume that every safe ore is known.

## Validation

The cost/timing simulator was checked against the installed engine on Duel with
one Builder, one length-1 conveyor line, and one Harvester:

- Builder spawned: round 0;
- conveyor built: round 1;
- Harvester built: round 3;
- first delivery: round 4; and
- final balance: `500 + 2,500 passive + 2,490 mined - 57 capex = 5,433`, exactly
  matching the engine summary.

The passive-income model independently matches a 1,000-round do-nothing game:
`500 + 250 × 10 = 3,000`.

## Reproduction

Run:

```sh
uv run python scripts/analyze_opening_economy.py
```

Outputs:

- `analysis/opening-economy/ore-distances.csv`
- `analysis/opening-economy/opening-results.csv`
- `analysis/opening-economy/opening-results.json`
