# Building an Army: Turrets & Combat · Step 5 of 5

Source: https://game.code.florent.vc/tutorials/turrets-combat/05-recap

## Recap & checkpoint

You now have a bot that:

- Knows the three turret types and their tradeoffs — Gunner (cheap, fast), Sentinel (expensive, hard-hitting), Launcher (repositions, doesn't damage)
- Builds a Gunner with `ct.build_gunner` and confirmed it does nothing without ammo actually delivered to it
- Feeds a turret's own local ammo stock with a Conveyor from a Harvester, and watched `ct.get_ammo_amount()` fill up and drop as the Gunner fires
- Uses `ct.heal()` to repair damaged friendly entities (buildings and Builder Bots alike) on a tile
- Understands `ct.fire()`'s real scope for Builder Bots — sabotaging whatever building you're standing next to, friendly or enemy — and that `self_destruct()` is a cleanup tool, not a weapon

> **Correction vs. the official docs.** The published recap credits "converting titanium at the Core (`ct.convert_ammo`)" and watching "`ct.get_global_ammo()`" for the working turret. Neither exists — see the corrections in [step 1](01-meet-the-turrets.md) through [step 3](03-the-ammo-gap.md). The bullet above reflects what actually made it work: a Conveyor delivering titanium directly to the turret.

The combination you built in this tutorial — a Harvester for income, a Gunner guarding it and fed by a Conveyor, and a Builder Bot that wired the two together — is a real, if small, piece of a competitive bot. Everything from here is about connecting more pieces like it and coordinating them.

Next up: [Coordination & Strategy](../comms-strategy/01-the-global-communication-store.md) — use the Global Communication Store to let multiple Builder Bots share information, and put together a bot that combines everything from all four tutorials.
