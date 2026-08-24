# Bastion

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

`steward` plus one change: **the second ring site is a Gunner, not a second
Launcher.**

## Why

Across 84 gate games, sorted by outcome:

| | our 1st home turret | enemy turret beside our Core | built at all |
|---|---|---|---|
| wins | median T14 | T10 | 32/46 |
| losses | median **T20** | T10 | **26/38** |

We lose the short games (mean 80 rounds against 119 for wins), we are six
rounds slower to put up home defence in them, and in **12 of 38 losses we never
build a home turret at all**. The enemy plants one beside our Core on round 10
either way. This is the same timing law the ladder replays showed at the start
of the session: whoever has turrets up before the other side's forward turret
lands, lives.

Home defence was purely reactive — `_defend_core` needs a *visible enemy* to
align with and only runs once the Core is already being hit, which is far too
late. The ring Builder is meanwhile standing next to the Core at exactly that
moment, building Launchers. A ring Launcher is a displacement screen that
cannot shoot; a Gunner is the building the timing says decides the game, at the
same +10% cost scale. So the pad stays (the attacker needs it) and the *next*
site becomes a Gunner.

It now lands on round 10 rather than 14-20.

Two implementation notes worth keeping: `_ray_direction` needs exact eight-way
alignment to the enemy Core, which a ring site essentially never has — using it
here disabled the guard permanently on its first attempt — so the facing is the
sign-wise compass direction instead. And `_compass_ring_targets` does not exist
in this lineage; ragnarok dropped it for `_launcher_ring_targets`.

## Measured

Against three opponents chosen as the poles of the cost-scale trade-off — the
matchup the Launcher caps most improve, and the two they most damage:

| build | vs prospect | vs ragnarok_fair | vs vigil@60d5afa | total /126 |
|---|---|---|---|---|
| warden | 30 | 18 | **31** | 79 |
| warden_walk (blanket cap) | 26 | 24 | 22 | 72 |
| **bastion** | 30 | **25** | 29 | **84** |

It is not free: it gives up 2 games against `vigil@60d5afa`, where warden takes
31. But it captures nearly all of the blanket cap's specialist gain against
`ragnarok_fair` (25 against 24) for a fifth of that cap's cost (which loses 9
games in the same column).

Against the two Nash-core agents: 24/42 vs `ragnarok@79582fc` and 23/42 vs
`vigil@e267eeb`, worst per-target map rate 29% against steward's 19%.

Timing: 0 turns over 10 ms.
