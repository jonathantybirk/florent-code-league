# Logistics: Conveyors & Splitters · Step 4 of 5

Source: https://game.code.florent.vc/tutorials/conveyors-logistics/04-splitting-the-flow

## Splitting the flow

A plain Conveyor has exactly one output tile: whatever's directly in front of it. A Splitter takes input from directly behind it and can output to any of the other three cardinal sides — useful once you want one Harvester's income to reach more than one destination, like your Core and a turret cluster somewhere else. It doesn't split a stack across sides simultaneously: each delivery goes whole (10 Ti) to whichever connected side hasn't been used in the longest time, so with multiple destinations wired up, they take turns receiving stacks rather than all filling up at once.

`ct.build_splitter(pos, direction)` uses `direction` the same way `build_conveyor` does: it's the side the flow continues toward. The input side is automatically the opposite direction. So swapping the final segment of our chain from a Conveyor to a Splitter doesn't change how it feeds the Core — it just opens up two more sides for something else to tap into later.

```python
                if bid is not None and ct.get_entity_type(bid) == EntityType.CORE:
                    if ct.can_build_splitter(next_pos, d2):
                        ct.build_splitter(next_pos, d2)
                    self.chain_done = True
                    return
```

That's the only change needed to `_lay_conveyor_toward_core` from the previous step — everywhere else, `ct.build_conveyor(next_pos, direction)` becomes `ct.build_splitter(next_pos, direction)` and `can_build_conveyor` becomes `can_build_splitter`. Titanium still reaches your Core exactly as before; the difference is invisible until you actually build something on one of the Splitter's other two output sides.

We won't wire up that second output in this tutorial — a Gunner turret, which is exactly the kind of thing worth feeding from a Splitter, doesn't show up until the next one. Keep the idea in mind: a Splitter at the last junction before your Core is a cheap way to keep your options open, even before you know exactly what else you'll want to feed.

## Try it

```
fcode run starter starter
fcode watch replay.replay26
```

What you should see: the same delivery behavior as the previous step — titanium still reaches your Core through the Splitter exactly as it did through the plain Conveyor.

Next: recap, and what this tutorial sets up for combat.
