# Coordination & Strategy · Step 1 of 4

Source: https://game.code.florent.vc/tutorials/comms-strategy/01-the-global-communication-store

## The Global Communication Store

Every unit you've written so far has acted alone — a Builder Bot only knows what it can personally see. The Global Communication Store is a shared blackboard: 16 integer slots (indexed 0–15), readable and writable by every unit on your team.

```python
ct.write_store(0, 42)
value = ct.read_store(0)
```

There's one timing rule that matters more than anything else about the Store: writes are buffered. A write made this round isn't visible until the next round — not even to the unit that made it.

```python
# Core, round N:
ct.write_store(0, 42)
value = ct.read_store(0)  # still 0 -- this round's snapshot hasn't changed

# Any unit, round N+1:
value = ct.read_store(0)  # now 42
```

This is deliberate, not a quirk to work around: it guarantees every unit sees a consistent snapshot of the Store for the entire round, no matter what order units happen to execute in. Design your protocol around the one-round lag rather than fighting it — and give your slots names instead of leaving magic numbers scattered through your code:

```python
SLOT_ORE_X = 0
SLOT_ORE_Y = 1
```

Next: put the Store to work letting Builder Bots share what they've found.
