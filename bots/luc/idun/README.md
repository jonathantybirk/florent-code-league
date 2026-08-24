# Idun — lift the economy ceiling, which turns out not to be what holds us back

`vidarr@bbfaa9c` with `CLAIM_SLOTS = (1, 8, 6, 7)` and
`LAUNCH_REQUEST_SLOTS = range(2, 6)`. Two constants, one file. Measured level
to negative; kept for the diagnosis, which is worth more than the build.

## The ceiling is real and it is exactly two

`CLAIM_SLOTS = (1, 8)` allows two simultaneously claimed deposits, so the team
can sustain about two Harvesters. Decoded from live ladder games, Harvesters
**alive** at round 50 -> 400:

| matchup | us | them |
|---|---|---|
| Besvikomat | 3.2 -> **0.3** | 2.2 -> **6.3** |
| Coreflood | 1.6 -> 1.5 | 1.6 -> **6.2** |
| O(1) | 2.4 -> 2.7 | 1.6 -> 3.0 |
| 0033 (our best of these) | 2.2 -> 1.5 | 1.8 -> 0.5 |

Their economy compounds; ours is pinned flat all game. The one opponent whose
Harvesters also decline is the one we score best against. `_pick`'s own comment
already recorded "an economy that never grows" and attributed it to claim
staleness — staleness was real, but two slots is a ceiling no freshness policy
can lift.

`freyja` and `hlin` had already widened this to four slots, taking 6 and 7 from
the launch-request range. Both carry `RING_AFTER_ECONOMY`, independently worth
-8.3 points, so the change had never been measured on its own.

## It fires, and it does not pay

150 ore-realistic maps, both seats, 300 games a cell, against its own base.

| vs | | Harvesters | conveyors | win rate |
|---|---|---|---|---|
| `undertow` | vidarr -> idun | 3.45 -> **3.97** | 20.28 -> **24.15** | 0.6533 -> 0.6333 (**-0.5 sd**) |
| `spar_sentinel` | vidarr -> idun | 2.93 -> **3.24** | 15.45 -> **19.17** | 0.4333 -> 0.4300 (-0.1 sd) |

+15% Harvesters, +19% conveyors, about three games in four changed — and no
wins.

## The obvious excuse, tested and refused

Local games are far shorter than live ones (median **103** and **82** rounds
against the ladder's 300-435), so "the extra economy has not had time to
compound" is the natural defence, and it is wrong. Split by game length it goes
the other way:

| rounds | vs `undertow` | vs `spar_sentinel` |
|---|---|---|
| 0-100 | +0.4 sd | +0.5 sd |
| 100-200 | -0.5 sd | -0.5 sd |
| 200+ | **-1.5 sd** | **-0.6 sd** |

`idun` is *better* in short games and *worse* in long ones — precisely the
opposite of a compounding payoff. The most likely reason is the tax it pays for
the extra economy: every Harvester adds +5% to Harvester prices and every
conveyor +1% to everything, and a Builder spending its turn on belt is not
defending.

**Not queued.** The ceiling is real, identified and lifted; lifting it is not
worth anything in this architecture. Anyone returning here should look at what
the extra income is *spent on* rather than at how much of it there is.
