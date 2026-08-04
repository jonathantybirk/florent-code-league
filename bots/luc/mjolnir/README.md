# Mjolnir

Odin's chassis, re-derived for the **fcode 2.3.4 turret balance patch** of
2026-08-04. Every number in this file was measured after that patch; nothing
from before it was assumed to still hold, and several things did not.

No map oracle. There is no atlas module and no import of one, so this plays a
generated map, the held-out set and the final the way it plays the published
pool.

## Why the flagship needed rebuilding, not tuning

The patch repriced combat and left economy alone:

| | before | after |
|---|---|---|
| Gunner cost | 10 Ti | **20 Ti** |
| Gunner HP | 40 | **25** |
| Gunner damage | 10 | **7** |
| Gunner ammo/shot | 2 | **4** |
| Gunner scale tax | +10% | **+20%** |
| Sentinel HP | 30 | **40** |
| Sentinel reload | 3 rounds | **2 rounds** |

Odin at commit `38e1456` scored 0.926 on the 336-game panel under 2.3.3. The
same bot, the same opponents, the same maps, on 2.3.4: **0.720**. It is the
most Gunner-dependent bot in the lineage and the patch was aimed squarely at
Gunners.

Turning the existing knobs does not recover it. A six-variant sweep over the
ammunition thresholds, the guard cap, the attacker cap and the siege barrier
moved the total between 234 and 248 against a 242 baseline — the whole spread
is inside the panel's noise floor of about 2pp. The problem is structural.

## The titanium table that decides everything

Per titanium spent, under 2.3.4:

| action | effect | HP per Ti |
|---|---|---|
| Barrier, as a wall to be shot | 30 HP for 3 Ti | **10.0** |
| Builder heal | 4 HP for 1 Ti | **4.0** |
| Sentinel fire | 18 damage for 10 Ti | 1.8 |
| Gunner fire | 7 damage for 4 Ti | 1.75 |
| Builder attack | 2 damage for 2 Ti | 1.0 |

Defence is now between two and ten times more titanium-efficient than offence,
and a barrier is the cheapest object on the board by a factor of six. A Gunner
needs five shots and 20 Ti of ammunition to break a barrier we replace for 3.

## What actually kills our Core

Measured, not assumed. 32 lost Cores over the five maps this chassis loses most
on, classified by the size of each damage event (2 = Builder attack, 7 =
Gunner, 18 = Sentinel):

```
gunner          20755 HP  (97.6%)  in 32/32 games
sentinel          504 HP  ( 2.4%)  in  5/32 games
builder-fire        0 HP  ( 0.0%)  in  0/32 games
```

Enemy Builder Bots never touch our Core. They emplace a Gunner near it and
shoot: 114 went up within four tiles of the footprint across those 32 games —
29 of them directly against it — and each lived a median of 34 rounds, which is
34 shots and 238 damage against a 500 HP Core. 79% of the Cores that die, die
before round 200.

## The bulwark

A Gunner's ray *"stops at the first targetable tile (a builder bot or a
building)"*. The Core is a 2×2 footprint, so every compass ray that reaches it
— from any range, orthogonal or diagonal — must first cross the ring of tiles
at Chebyshev distance 1. There are exactly twelve of those. Put **any** building
on all twelve and no Gunner anywhere on the map has a firing line into the
Core, for the rest of the match. Twelve barriers is 36 Ti and +12% scale.

Only a Sentinel, whose line is never blocked, still reaches — 2.4% of the
damage — and `_heal_core` answers that.

Three things about the implementation are load-bearing:

* **Any building counts.** A conveyor already on the ring closes it as well as
  a barrier does, and it is the income line, so it is left alone. The last-mile
  conveyor delivering into the Core lives on the ring by necessity.
* **The ring is a cardinal cycle**, and where the Core sits against a map edge
  there is no shell outside it to build from — the Builder has to stand on the
  ring to wall the ring. The first cut sorted targets by distance to the enemy
  Core, walked to the far side, and spent eight rounds circling because the
  tiles it kept standing on were the tiles it was trying to fill. It now builds
  the nearest one and checks, before each build, that walling it will not box
  the Builder in (`_stranding`).
* **`bulwark_done` keeps it from becoming a leash.** A tile seen covered stays
  covered in memory, so a Builder that has closed the ring is free to walk off
  and mine; only a tile it can currently see to be open pulls it home. A Core
  damage alarm clears that memory once, so a real breach is still noticed.

### Two measured corrections

**Eight tiles was the wrong wall.** The first version walled only the eight
*orthogonal* neighbours, reasoning that those are the only tiles an enemy
Builder can stand on to attack a 2×2 Core. That is true and irrelevant — enemy
Builders deal 0% of the damage. It scored 246/336 against a 242 baseline: what
a correct answer to a problem you do not have looks like.

**The wall does not outrank the guard.** `_guard_home` — meeting an intruder at
our own Core on sighting rather than on damage — is the largest single measured
win in this lineage, and the obvious 2.3.4 correction was to demote it, since
the Gunner it buys costs twice as much and does 30% less damage. Measured, that
is worth 236/336 against 246: the ring Builder spends its first twenty-five
rounds walling while their attacker emplaces unopposed. The guard answers the
intruder who is already here; the wall answers the shooter who gets past it.
Order: guard, then wall, then the Launcher pad.

## Spawn denial: sound, and off

A Core spawns Builder Bots only on passable tiles within spawn radius² = 2 —
which is exactly the same twelve-tile ring. Wall the enemy's and their Core can
never spawn again, can never be healed, and every Builder they lose is gone
permanently. `_run_spawn_denial` implements it and `SPAWN_DENIAL_ENABLED` is
**False**.

The reason is a measurement on the mechanism rather than on a win rate: traced
against vigil on jackpot and longship, their Builder Bots spawn on rounds 0, 1
and 2 and never again. Every bot on this panel, ours included, buys a fixed
opening of three Builders and only spawns more on a damage alarm. There are no
spawns to deny, and the attacker spent its rounds walking a ring instead of
shooting. The code stays because against an opponent that does replace its
losses it is decisive, and switching it on is one line.

## Inherited

Everything in Odin that the patch did not invalidate: vigil's turret meta and
economy planner, Prospect's corner doctrine, Casemate's walled piercing-Sentinel
siege as the no-lane fallback, GobbleGlitch's mender defence and cost-scale
hygiene, the capped Launcher relay warden_walk measured, Heimdall's repair cap
and tabu step, and Odin's Core-death projection and cover-tier seat discipline.
