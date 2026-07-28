# Game Rules — Turrets

Source: https://game.code.florent.vc/docs/game-rules-turrets

Turrets are stationary combat buildings constructed by Builder Bots. Like every other unit, each turret runs its own instance of your bot code once per round.

> **Correction vs. the official docs.** The published page describes ammo as a team-wide pool produced at the Core (`convert_ammo()` / `get_global_ammo()`) that turrets draw from. **That is not how the installed `fcode` engine works** — those methods do not exist (confirmed by enumerating the real `Controller` object at runtime; calling any of them raises `AttributeError`). The paragraph below is rewritten to match the actual engine.

Gunners and Sentinels consume **ammo (titanium) held inside each individual turret** — there is **no team-wide ammo balance** and no titanium→ammo conversion. Each turret simply stores titanium which acts as ammo as a physical resource, and you must **deliver titanium to it via conveyors**. Each shot deducts its ammo cost (2 for a Gunner, 10 for a Sentinel) from **that turret's own stock**; a turret with empty ammo cannot fire. Launchers use no ammo. Check a turret's own supply with `ct.get_ammo_amount()` and `ct.get_ammo_type()`.

Gunners have a facing direction set at build time and adjustable with `ct.rotate()` — Sentinels also face a fixed direction set at build time, but cannot rotate afterward. The Launcher has no facing direction at all.

> **Additional detail, not on the official page** (from the engine's bundled [spec](../engine-spec.md)): a turret can hold at most one stack of ammo, and only accepts a new stack once it's completely empty — it doesn't top up partially. Feeding conveyors must approach from any side other than the turret's facing direction; a turret facing a diagonal direction can be fed from all four cardinal sides. If a tile has both a building and a Builder Bot on it and gets hit, only the Builder Bot takes damage.

## Gunner

A rapid-firing turret that fires a narrow forward ray.

| Property | Value |
|---|---|
| HP | 40 |
| Cost | 10 Ti |
| Damage | 10 |
| Ammo per shot | 2 |
| Fire pattern | Forward ray (single tile width) |
| Reload | 1 round |
| Vision / attack radius² | 13 |

The line stops at the first targetable tile (a builder bot or a building) in its facing direction; empty tiles don't block it, but walls do (and aren't themselves targetable). It is cheap and effective at controlling corridors, and is the only turret that can rotate after being built.

## Sentinel

A defensive turret that fires a long, obstacle-piercing line.

| Property | Value |
|---|---|
| HP | 30 |
| Cost | 30 Ti |
| Damage | 18 |
| Ammo per shot | 10 |
| Fire pattern | Single-tile-wide straight facing line (same width as Gunner, but longer and unblockable) |
| Reload | 3 rounds |
| Vision / attack radius² | 32 |

Sentinels hit a single tile-wide line along their facing direction, just like a Gunner's shot — but the line reaches much further (vision/attack r²=32 vs. Gunner's 13) and, unlike a Gunner's, is never blocked by walls or units in the way. They're expensive per shot and slow to reload, but excel at reaching deep into a lane the enemy thinks is safe. Facing is fixed at build time; Sentinels cannot rotate.

## Launcher

A utility turret that picks up and throws Builder Bots.

| Property | Value |
|---|---|
| HP | 30 |
| Cost | 20 Ti |
| Action | Picks up an adjacent (including diagonal) friendly Builder Bot and throws it to any bot-passable tile in range |
| Pickup radius² | 2 (adjacent, incl. diagonal) |
| Throw radius² | 26 (measured from the Launcher, not the bot) |
| Reload | 1 round |

The Launcher does not deal direct damage and needs no ammo. Its value is rapid redeployment — it can throw a Builder Bot up to `sqrt(26)` tiles away in one action, enabling surprise attacks or fast base expansion. It has no facing direction and cannot rotate.

## Rotating turrets

Only the Gunner can rotate after placement:

```python
if ct.can_rotate(Direction.WEST):
    ct.rotate(Direction.WEST)
```

Rotation costs exactly 10 Ti and triggers a 1-round action cooldown. Sentinels and Launchers have no `rotate()` — their orientation (or lack of one) is fixed for their lifetime.
