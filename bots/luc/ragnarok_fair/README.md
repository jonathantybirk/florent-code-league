# Ragnarok Fair

**Generated** from `bots/luc/ragnarok` by
`tools/build_ragnarok_fair.py` with the offline map atlas removed.
Do not edit these files; edit ragnarok and regenerate.

The best measured mechanic from every lineage in the repo, in one bot. Built
from the benchmark evidence in [`benchmarks/ANALYSIS.md`](../../../benchmarks/ANALYSIS.md),
which found that the lineages were each losing mechanics the others had
already solved.

`ragnarok_fair` is this bot with the offline map atlas removed. It is
**generated** by `tools/build_ragnarok_fair.py`, never edited by hand, so the
two cannot drift; the generator fails loudly if an `atlas` import survives.
Neither bot looks a map up at runtime — the doctrine reads the map dimensions
and its own Core position only.

## Where each part came from

| part | origin | measured |
|---|---|---|
| economy planner, ferries, breaker Gunners, turret rotation / stand-down | Luc `vigil`, `tempest_reinforcements` | the field's strongest chassis, 84% h2h |
| corner doctrine (`FORTIFY`) | Luc `prospect` | +5 games /120 |
| field Gunners, on closed maps only | Luc `prospect`, re-tuned | **+8 games /120** |
| lane rebuild-tanking under Core attack | Elias's exploit lab | **+5 games /120** |
| piercing-Sentinel siege, barrier-wrapped | Jon `casemate` | +2 games /120 |
| Core threat-zone seal | Luc `vigil` | +1 game /120 |
| economy-free blitz on short maps (`BLITZ`) | Jon `tempest`/`mistral`, conditioned | +6 games /252 |
| farthest-first enemy-Core inference, committed early | Elias `autistimusprime` | 66.7% correct vs 9.5% |
| Launcher retirement, second trunk, ore denial | Elias's lab, Luc | **0** — see below |

## The three doctrines

Chosen once, by the Core, on round 0, and published in the own-Core store slot
so every unit agrees (units do not share module globals — measured).

- **BLITZ** — enemy Core within 6 tiles. Nobody mines, nobody rings: three
  attackers. Economy is tempo spent, and on a map decided by round 21 the
  first delivered stack never arrives.
- **FORTIFY** — Core in a map corner. Two edges guard two approaches for free;
  the enemy must come down a lane, so a turret in that lane pays.
- **RUSH** — everywhere else. One miner, one attacker, one Launcher ring.

## Turn limit

Every unit fits the ladder's 10 ms budget with room to spare: worst measured
turn 2,995 µs across all 21 maps, against a limit where overrunning means the
unit does not act at all that round. Check before submitting:

```sh
uv run python -m benchmarks.timing --bot bots/luc/ragnarok --maps all
```

`CPU_SOFT_BUDGET_US` stops the widest optional search once a turn has spent
4 ms. The first build did *not* fit — 13,480 µs on longship — because
`_keeps_route_open` ran two map searches inside a 196-candidate loop.

## Honest notes

Three mechanics measured **exactly zero** — Launcher retirement, the second
conveyor trunk, and enemy-ore denial changed no game outcome across 120 games.
They are kept because each only fires in a long game (45 quiet rounds, round
120) and 89% of games end by round 60, but they are not improvements on this
evidence and should be the first things re-measured, not trusted.

`BLITZ_MAX_DISTANCE` was originally set to 8, where the map pool has a natural
gap. That measured *worse* than off (195 vs 197 / 252) because it swept in one
map that wants an economy. Six is the shipped value at 201. The gap in the
data was not the right place to cut, which is the general lesson.

## Reproducing

```sh
uv run python tools/build_ragnarok_fair.py          # regenerate the fair twin
uv run python -m benchmarks.ablate --run-dir benchmarks/runs/ab
```
