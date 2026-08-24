# Lattice

A modular, memoryless bot for fcode 2.3.6, built from the engine rather than from
the existing lineage. **The architecture goal is met; the win-rate goal is not.**
Measured numbers are below and they are not good yet.

## Status: 0.411 against the panel, target was 0.90

fcode 2.3.6, 5 official maps, both seats, 10 games per opponent, 90 games total.

| opponent | rate |
|---|---|
| `common/starter` | 0.900 |
| `jon/fair/tempest_fast` | 0.800 |
| `lucas/strat1` | 0.700 |
| `jon/fair/casemate` | 0.700 |
| `bench/gobbleglitch` | 0.200 |
| `bench/steward` | 0.200 |
| `bench/vidar` | 0.100 |
| `bench/odin` | 0.100 |
| `jon/fair/vanguard` | **0.000** |
| **total** | **0.411** |

It beats the starter and the older `jon/fair` line, and it is comprehensively
beaten by the current frontier. Every loss to `vidar` and `odin` is a Core
destroyed between turn 59 and turn 107 -- this bot loses the opening, not the
long game.

Reproduce with:

```sh
uv run python tools/bench.py jon/lattice --panel bench/vidar,bench/odin --maps 5 --jobs 8
```

(`bots/bench/` is gitignored; it is populated by `git archive` from `x/luc` and
`elias_dev` -- see the benchmark section below.)

## What the engine actually says

Derived from `GameConstants` on 2.3.6, not inherited:

* **Killing a Core costs ~280 Ti of ammunition** whichever turret does it
  (500/18 = 27.8 Sentinel shots x 10 ammo; 500/7 = 71.4 Gunner shots x 4). The
  Sentinel is merely faster: 84 rounds against 143.
* **Healing beats shooting 2.2 to 1.** A Builder restores 4 HP for a flat 1 Ti;
  a Sentinel deals 18 for 10 ammo. Both heal and ammo are *immune to cost scale*
  -- only construction is taxed.
* **A tended Core does not die.** One mender absorbs 4 of a Sentinel's 6 HP/round.
  Two menders out-heal a two-Sentinel battery outright.
* **So most games should reach the round-1000 tiebreak**, which is decided by
  titanium *collected* -- stacks that physically landed on a Core tile. Passive
  income does not count. Delivery is the scoreboard.
* **A trunk is a pipe with a fixed bore.** A conveyor holds one stack and moves it
  one tile per round; a Harvester emits one per four. Four Harvesters saturate a
  trunk exactly.
* **Cost scale is the master currency.** +20% per Builder *and* per turret, +10%
  Launcher, +5% Harvester, +1% per conveyor. It is a live census, refunded on
  death. Five turrets alone is +100%, which doubles the price of the economy.

The bot is built around the last two. It plays for delivery, defends what
delivers, and shoots the enemy's supply rather than their guns.

## Architecture

One module per concern; nothing reaches across.

```
config.py         every tunable, each with the reasoning for its value
geom.py           pure geometry; keeps the 4-neighbour / 8-way split explicit
comms.py          the 16-slot store as a named schema
world.py          perception, terrain memory, symmetry inference, threat map
nav.py            reverse BFS on the Builder's cardinal graph
econ.py           delivery model: what is connected, how full the pipe is
roles.py          warden / field split -- the one fact that must persist
kernel.py         scores behaviours, runs the best
bhv_guard.py      answer an enemy on our doorstep
bhv_mend.py       heal; the cheapest titanium in the game
bhv_siege.py      seat a turret that shoots their economy
bhv_route.py      connect a Harvester to the Core
bhv_harvest.py    put a Harvester on ore
bhv_secure.py     deny enemy-side ore with 3 Ti barriers
bhv_explore.py    the floor: convert a spare round into map knowledge
core_brain.py     spawn policy and ammunition
turret_brain.py   firing policy
```

**Memoryless.** Builders keep no state machine. Each round every behaviour
re-scores from current knowledge and the highest scorer runs, so a Builder cannot
persist a plan the board has already invalidated. The only carried state is a
per-unit route cache and the role, and both are revalidated before use.

**Adding a capability** means writing one `bhv_*` module and adding it to
`kernel.BEHAVIOURS`. **Retuning for a new meta** means editing `config.py` --
including `CEILINGS`, which is the entire priority order. Neither requires
touching the kernel. That property is real and was exercised repeatedly during
development (the turret-cap sweep below is a one-line config edit).

## What is measured, and what is still a guess

Measured on 2.3.6:

* Turret caps. Swept `MAX_SIEGE_TURRETS` x `MAX_GUARD_TURRETS` over
  {0,1,2}x{1,2} against vidar and odin, 6 games each: every cell landed between
  0.000 and 0.083. **Turret count is not the lever**, which is itself worth
  knowing -- it rules out the most obvious explanation for the losses.
* `mend` priority. The first version healed anything damaged by 1 HP and ran on
  24 of 35 rounds, because the opponent keeps everything lightly damaged; the bot
  healed scratches forever and never built. Restricting the walk-home to the Core
  and turrets, and raising `MENDER_MIN_DAMAGE` to 4 (one heal's worth), moved
  vidar 0.000 -> 0.125.
* Counter-battery. Shooting enemy turrets that threaten our Core, overriding the
  scale-refund rule, measured **flat**. Kept on the survival argument, but it is
  not carrying anything and should be re-tested.
* The warden role measured **flat** (0.333 before and after). Kept because the
  reasoning is sound and the sample is small, but it is unproven.

Not measured, i.e. guesses: `OPENING_BUILDERS`, `HARVESTERS_PER_TRUNK`,
`MAX_TRUNK_LENGTH`, every ammunition constant, and every number in `CEILINGS`
except the `mend` tiers.

## Why it loses, as far as the evidence goes

Instrumented at round 70 against vidar: `ammo=21 ti=164 scale=274 units=9`.

Cost scale at 274% means every build costs 2.74x, which is why the bot finishes
games with 5-7 buildings against vidar's 15. Yet in an early version it
*out-mined* vidar (480 to 470) while losing -- so the economy engine works and the
spending does not.

The losses are all early Core deaths, so the gap is the opening. Three candidates,
in the order I would test them:

1. **The opening is too slow to contest anything.** vidar emplaces a Sentinel near
   our Core by turn ~40 and this bot has no answer that arrives in time. A real
   opening plan -- who walks where, in what order, with what build -- is the
   largest missing piece and is not written yet.
2. **`bhv_siege` almost never fires.** The behaviour tally over 35 rounds showed
   `mend 24, guard 6, route 3, harvest 2` and no siege at all. It only considers
   seats on the four tiles orthogonally adjacent to the Builder, which is far too
   restrictive; it should search seats around the *target* and walk to them.
3. **Scale discipline.** Nothing ever calls `destroy()` or `self_destruct()`, so
   spent Launchers and dead-end conveyors are taxed forever. The cost-scale census
   is refunded in full and immediately on removal -- this is free titanium that
   the bot currently declines to collect.

## Benchmark

`tools/bench.py` plays every pairing on both seats, because the first-spawning
team has a real advantage and a single-seat score is not a measurement. The panel
lives in `bots/bench/` (gitignored) and is populated from the other branches:

```sh
mkdir -p bots/bench
for b in vidar odin steward heimdall vigil prospect janus; do
  git archive origin/x/luc bots/luc/$b | tar -x --strip-components=2 -C bots/bench
done
for b in gobbleglitch autistimusprime; do
  git archive origin/elias_dev bots/elias/unfair/$b | tar -x --strip-components=3 -C bots/bench
done
```
