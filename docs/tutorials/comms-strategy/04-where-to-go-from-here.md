# Coordination & Strategy · Step 4 of 4

Source: https://game.code.florent.vc/tutorials/comms-strategy/04-where-to-go-from-here

## Where to go from here

You've now touched every major system in the game: movement and sensing, the titanium economy, conveyor logistics, turret combat, and team-wide coordination through the Global Communication Store. That's the whole rulebook — everything from here is strategy, not new mechanics.

The platform ships a more polished reference bot at `bots/starter_bot.py` (or `bots/starter/main.py` if you ran `fcode starter`). It's built from the same pieces you just used, organized a little differently, and its own docstring is honest about what it doesn't do yet:

> **Correction vs. the official docs.** The published page's second bullet reads "Tune the ammo buffer: convert more titanium when enemies are near, less when you'd rather grow the economy" — a holdover from the wrong team-wide-ammo model (see the corrections throughout [Turrets & Combat](../turrets-combat/01-meet-the-turrets.md)). The actual shipped starter bot's docstring says something different; the list below quotes it directly.

- Build full conveyor chains from distant Harvesters back to the Core
- Feed ammo to gunners via conveyors so they can actually fire
- Add sentinels or launchers for stronger defense
- Explore the map systematically instead of picking random targets
- Use more store slots to coordinate roles between builder bots

Notice that you already solved the second one in [Turrets & Combat, step 3](../turrets-combat/03-the-ammo-gap.md) — the shipped starter bot doesn't. That's not a coincidence; it's a genuinely open problem, and a reasonable place to start improving on the reference implementation rather than your own bot from these tutorials.

Some concrete next steps, roughly in order of effort:

- Read the full [Controller API Reference](../../api-reference/robot-api.md) — plenty of methods (`get_attackable_tiles`, `launch`, `can_fire_from`, ...) weren't covered here.
- Fix the "independent bots collide" problem from the previous step — use Store slots to assign roles (harvester vs. router vs. defender) instead of letting every Builder Bot run the same logic.
- Add real pathfinding — the two-axis walk from the logistics tutorial gets stuck on anything more complex than a simple wall.
- Layer in Sentinels and Launchers — a Gunner-only defense is predictable and easy to counter.

When you're ready to see how your bot holds up:

```
fcode submit bots/starter
```

Your bot gets queued for ladder matches automatically — check the Matches page to see results, and the Ladder page to see how you rank. Good luck.
