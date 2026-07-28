# Building an Army: Turrets & Combat · Step 4 of 5

Source: https://game.code.florent.vc/tutorials/turrets-combat/04-healing-and-sabotage

## Healing and sabotage

Builder Bots have two more combat-adjacent abilities worth knowing, and both are narrower than they might sound at first — though not in the same direction.

`ct.heal(pos)` repairs damaged friendly entities on a tile, for 4 HP at a cost of 1 titanium. It heals a building and a Builder Bot standing on it in the same call if both are friendly and damaged. Use `ct.can_heal(pos)` first — it checks range, cooldown, titanium, and that there's actually damage to repair.

> **Correction vs. the official docs.** The published page restricts `heal` to an orthogonally adjacent tile, never diagonal and never the Builder Bot's own tile. **Verified against the running engine — it's actually broader than that**: any tile within the Builder Bot's action radius works, including diagonals *and* its own tile (e.g. healing itself and a damaged building it's standing on in one call).

```python
for d in Direction:
    target = ct.get_position().add(d)  # includes the bot's own tile via Direction.CENTRE
    if ct.can_heal(target):
        ct.heal(target)
        break
```

`ct.fire(pos)` is more restrictive than it looks — and in the opposite way from `heal`. It's not a way to attack a nearby enemy unit — for that, you'd need a turret. And it's not even a way to attack an *adjacent* building.

> **Correction vs. the official docs.** The published page says `fire` targets an orthogonally adjacent tile. **Verified against the running engine — a Builder Bot's `fire` only ever works on the tile it's currently standing on**, confirmed with a real target sitting on every adjacent tile (cardinal and diagonal) and getting `can_fire() == False` for all of them, then `True` once standing on the target itself. What it's actually for is sabotage: since Conveyor and Splitter tiles are walkable by either team, walk onto an enemy's logistics chain and fire on your own position to damage whatever's under you. Two titanium per hit, same as the cost of the shot itself.

```python
pos = ct.get_position()
if ct.can_fire(pos):
    ct.fire(pos)
```

One more method you'll see referenced elsewhere: `ct.self_destruct()`. Older material (including some in-game documentation) describes it as dealing area damage when you blow up — that's no longer how it works. Self-destructing a Builder Bot today deals zero damage to anything nearby; it just removes the unit. Its only real use is freeing up your 50-unit cap or retreating a doomed bot before it gets picked off for a bounty — it is not a weapon.

## Try it

You don't need a full match to see these work — try building a Conveyor, walking onto it, firing at your own position a couple of times to damage it, then healing it back up:

```python
pos = ct.get_position()
if ct.can_fire(pos):
    ct.fire(pos)
elif ct.can_heal(pos):
    ct.heal(pos)
```

What you should see: the Conveyor's HP drop by 2 each time you fire, then climb back by 4 each time you heal, in the replay's building-health display.

Next: recap, and putting a full economy-plus-defense bot together.
