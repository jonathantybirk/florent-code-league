# Steward

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

`warden` — the highest raw win rate in the field — plus one fix: **the Core
replaces Builders it has lost.**

## The bug

`core.py` gates respawning on `has_live_builder`, which reads the shared
heartbeat slot. That slot only proves *one* Builder is alive. A team that loses
two of its three therefore never replaces them, and just keeps mining into a
bank nothing is left to spend.

Measured on sweden against `ragnarok_fair`:

```
T15  Ti=154  builders=3
T30  Ti=154  builders=2
T45  Ti=139  builders=1
T90  Ti=298  builders=1     dies on T103 holding 358 titanium
```

It lost to an opponent that mined **nothing at all**, while sitting on 358
banked titanium and one Builder that could not spend it.

## The trigger

A live headcount is not available: comms writes are invisible to other units
until the next round, so a per-round bitmask never accumulates. But the bank
itself is the signal — a working three-Builder team converts income into
Harvesters and turrets as it arrives, so a large idle bank *means* the
workforce cannot keep up. `REPLACEMENT_BANK_THRESHOLD = 110`, with a 12-round
cooldown so a bad stretch cannot spiral.

The +20% cost scale a replacement adds was already refunded when the Builder it
replaces died, so this restores the intended composition rather than inflating
past it.

Same game after the fix: survives to T138, mines 360 instead of 150, bank down
to 86.

## Why this one matters

Every previous change traded one matchup for another along a fixed frontier —
capping Launchers gains against Launcher-heavy bots and loses by about as much
against bots that wall us out. This is the first change that is **off** that
frontier:

| build | vs prospect | vs ragnarok_fair | total |
|---|---|---|---|
| warden | 30 | 18 | 48 |
| aegis (conditional cap) | 27 | 20 | 47 |
| warden_walk (blanket cap) | 26 | 24 | 50 |
| **steward** | **31** | **21** | **52** |

Against the two Nash-core agents it also improves on its base: 23/42 vs
`ragnarok@79582fc` (warden 21) and 23/42 vs `vigil@e267eeb` (warden 24, inside
noise), taking the worst per-target map rate from 5% to 19%.

Timing: 0 turns over 10 ms.
