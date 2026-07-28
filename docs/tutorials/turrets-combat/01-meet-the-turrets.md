# Building an Army: Turrets & Combat · Step 1 of 5

Source: https://game.code.florent.vc/tutorials/turrets-combat/01-meet-the-turrets

## Meet the turrets

Turrets are stationary buildings that attack automatically once built — no CPU time spent aiming or deciding when to fire. There are three:

| Turret | HP | Cost | Damage | Ammo/shot | Reload |
|---|---|---|---|---|---|
| Gunner | 40 | 10 Ti | 10 | 2 | 1 round |
| Sentinel | 30 | 30 Ti | 18 | 10 | 3 rounds |
| Launcher | 30 | 20 Ti | — (repositions a Builder Bot instead) | — | 1 round |

The Gunner is what you'll build first: cheap, fast-firing, good for holding a corridor. It fires a narrow ray straight ahead in its facing direction — anything in that line, friend or foe, blocks and can be hit. The Sentinel fires the same single-tile-wide line, but reaches much further and can't be blocked by anything standing in the way — trading a much higher cost and a 3-round reload for that reach and extra damage per hit; it's a defensive anchor, not something you spam early. The Launcher doesn't deal damage at all — it picks up a friendly Builder Bot within range and throws it to a target position, which is a repositioning tool, not a weapon.

> **Correction vs. the official docs.** The published page says here that "ammunition is a team-wide balance, not something a turret carries — and it starts at 0," fixed by having the Core convert titanium into ammunition. **There is no team-wide ammo balance and no Core conversion step** in the installed `fcode` engine — confirmed by enumerating the real `Controller` object at runtime (`convert_ammo`, `can_convert_ammo`, and `get_global_ammo` don't exist; calling any of them raises `AttributeError`). The real mechanic: **each turret holds its own ammo (titanium) locally**, and you have to deliver it via Conveyor, same as feeding any other resource-consuming building. A freshly built Gunner won't fire until titanium actually reaches it — that's still the entire subject of the next two steps, just with a different fix.

Next: build one and see this for yourself.
