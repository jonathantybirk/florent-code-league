# Engine 2.2.0 -> 2.3.3: what changed

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

*LLM-generated.* Method: both versions installed side by side, every shipped
Python file diffed, then each behavioural claim verified against the running
engine with probe bots rather than trusted from a docstring. The 2.2.0
docstrings were wrong about several rules, so nothing here rests on prose alone.

## Scope of the diff

Only two shipped files carry game-relevant changes: `_types.py` (the typed
Controller stub) and `data/starter_bot.py`. `api.py`, `__init__.py`,
`compat.py` and the `commands/` tree changed only in CLI/HTTP details -- the
one user-visible CLI addition is `--json` on the results commands.

`data/docs/spec.md` and `data/maps/` are **no longer shipped** with the
package. Our copy of the 2.2.0 spec in `docs/` is now the only local reference,
and it is out of date on ammunition.

The engine itself is a compiled `.so`, so a byte diff proves nothing about
behaviour. Everything below was therefore probed.

## 1. Ammunition is global (the big one)

| | 2.2.0 | 2.3.3 |
|---|---|---|
| model | per-turret; a 10-Ti stack physically delivered by conveyor or adjacent Harvester | one shared team pool |
| `get_ammo_amount()` / `get_ammo_type()` | present | **removed** |
| `get_global_ammo()` | absent | present |
| `convert_ammo()` / `can_convert_ammo()` | absent | present |

The Core converts titanium to ammunition **1:1, at most once per team per
turn**, it does not consume the Core's action cooldown, and the ammunition is
usable the same turn. Verified: `convert_ammo(100)` moved the balance from 0 to
100 and titanium from 468 to 368.

Costs are unchanged -- `GUNNER_AMMO_COST` 2, `SENTINEL_AMMO_COST` 10.

**This deletes the central premise of everything we have built.** Under 2.2.0
the binding constraint was *logistics*: damage was 5x the titanium physically
delivered into Gunners, which is why forward Harvesters, parasitism (Gunners
beside enemy Harvesters), conveyor taps and splitter batteries all mattered.
Under 2.3.3 a Gunner anywhere in range fires as long as the team has ammunition
in the pool. The constraint is now simply titanium.

## 2. Builder actions are orthogonal-adjacent only

Every build method, plus `heal` and `fire`, now documents "position must be an
orthogonally adjacent tile to this builder bot (not diagonal, not this builder
bot's own tile)". `GameConstants.ACTION_RADIUS_SQ` (was 2) has been **removed**,
consistent with adjacency replacing a radius.

Probed on 2.3.3 from an empty tile:

```
BUILD conveyor  orth: True   diag: False   own tile: False
```

The change to `fire` is an outright **inversion**. In 2.2.0 a Builder could
only damage the building on *its own tile*; in 2.3.3 it can only damage an
orthogonally adjacent tile and **not** its own. Any code that walks onto a
Conveyor and fires -- belt cutting, clearing a tile to take a firing position --
is now doing the one thing that is illegal.

`heal` moved the same way: from an action radius of sqrt(2) (diagonals included)
to orthogonal-adjacent only, and no longer the Builder's own tile.

## 3. Builder movement is cardinal-only

Probed directly:

```
MOVE  cardinal: [True, True, True, True]   diagonal: [False, False, False, False]
```

In 2.2.0 all eight directions worked, which our own mechanics audit recorded
after finding the tutorials wrong about it. 2.3.3 restores the documented rule
and adds two helpers for it: `Direction.is_cardinal()` and
`Position.cardinal_direction_to()`.

Any pathfinding built on an 8-connected grid now measures distances the engine
cannot walk -- diagonal shortcuts do not exist, so a diagonal step costs two
moves, and every distance estimate is short.

## 4. Smaller additions

- `can_act()` -- equivalent to `get_action_cooldown() == 0`.
- Round numbering doc corrected: "starts at 1" was wrong; it is 0-indexed.
- `Direction` gained a docstring pinning the compass convention: (0,0) is the
  northwest corner, NORTH is (0,-1).

## 5. What did *not* change

Every numeric constant is identical. Probed the full `GameConstants` and the
per-turn cost getters: Builder 30, Conveyor 3, Splitter 6, Harvester 20,
Barrier 3, Gunner 10, Sentinel 30, Launcher 20; Core 500 HP, Gunner 40,
Sentinel/Launcher/Harvester/Barrier 30, Conveyor 20; Gunner 10 damage on a
1-round cooldown, Sentinel 18 on 3; vision radii, `MAX_TEAM_UNITS` 50,
`MAX_TURNS` 1000, `STACK_SIZE` 10, `STARTING_TITANIUM` 500, passive 10 per 4
rounds. No rebalance -- only rule changes.

## What this means for our bots, concretely

Measured, not predicted. On 2.3.3, `vanguard` versus `common/starter` goes from
30-0 to **6-6**, and Vanguard, Undertow and Jonbot all lose to `starter` on
maps where they previously won outright. Every match is a 1000-round tiebreak
with **`ammo=0.0` on both sides**: no shot is fired all game.

1. **No bot on this branch converts titanium, so no turret can fire at all.**
   Every Gunner, Sentinel and battery any of them builds is decoration. This is
   the single largest effect and it applies to all three bots equally.
2. **All the parasitism machinery is now pointless.** Placing Gunners beside
   enemy Harvesters, forward Harvesters as feeders, `_extend_feed`, conveyor
   taps -- these solved a supply problem that no longer exists. They still cost
   titanium and Builder rounds.
3. **Belt cutting and tile clearing are broken, not merely worse.** They stand
   on the target tile and fire, which 2.3.3 forbids outright.
4. **Repair is weakened.** The crew positions itself on 8-adjacent tiles; the
   diagonal ones can no longer heal.
5. **Pathing is systematically wrong.** Distance fields are 8-connected, so
   every route is costed short and the movement fallback quietly converts one
   intended diagonal into two cardinal steps.
6. **Cheap defences are unaffected.** Barrier rings still block Gunner rays,
   Sentinels still pierce, and Launchers throwing enemy Builders needs no
   ammunition at all -- that last one gets relatively *stronger*, since it is
   now the only weapon that works without a Core conversion.

The obvious first move, whenever we do repair the bots, is a Core that keeps
the ammunition pool topped up. As a one-line experiment it took Vanguard from
14-16 down to 24-6 up against Undertow, purely by being the only bot on the
branch whose turrets could shoot. That experiment was reverted; it is recorded
here as a measurement, not as a change.

## Have all the changes been found?

For the Python surface, yes: every shipped file was diffed and the only
game-relevant deltas are listed above. For the engine, **no guarantee is
possible** -- it is a compiled binary. What can be said is that every rule the
stub documents as changed was verified against the running engine, and every
numeric constant was read back and matched. A silent change to something with
no constant and no docstring -- resource round-robin order, conveyor throughput,
turret targeting priority -- would not show up in either check.
