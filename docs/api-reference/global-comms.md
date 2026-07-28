# Global Communication Store

Source: https://game.code.florent.vc/docs/global-comms

The Global Communication Store gives all your bots a shared blackboard: 16 integer slots that persist across turns. Use it to coordinate strategy without hard-coding locations.

## API

| Method | Returns | Description |
|--------|---------|-------------|
| `ct.read_store(slot)` | `int` | Read the value in slot `slot` (0–15). |
| `ct.write_store(slot, value)` | `None` | Write `value` to slot `slot` (0–15). |

```python
# Read what last turn's bots wrote
attack_x = ct.read_store(0)
attack_y = ct.read_store(1)

# Write a new value for next turn
ct.write_store(0, target.x)
ct.write_store(1, target.y)
```

## Slots

There are 16 slots, indexed 0 to 15. All values start at 0 and accept any non-negative integer. Reading slot 16 or above raises an error.

## Timing: writes are buffered

Writes are not applied immediately. They are committed at the end of the round, and the new values become readable for all your bots in the next round.

| Round | Event |
|---|---|
| N | Bot A calls `write_store(0, 42)` |
| N | Bot B calls `read_store(0)` → still reads 0 (last round's value) |
| N+1 | Bot B calls `read_store(0)` → now reads 42 |

This means every bot sees a consistent snapshot of the store for the entire round, regardless of execution order. Design your communication protocol around this one-round delay.

## Team isolation

Each team has its own store. Your writes are invisible to the opponent, and you cannot read theirs.

## Usage patterns

### Scouting target

Designate fixed slots for a shared attack target:

```python
# Any bot that finds the enemy core sets slots 0 and 1
if found_enemy_core:
    ct.write_store(0, enemy_pos.x)
    ct.write_store(1, enemy_pos.y)

# All bots read the target at the start of run()
target_x = ct.read_store(0)
target_y = ct.read_store(1)
if target_x > 0 and target_y > 0:
    move_toward(ct, Position(target_x, target_y))
```

### Unit census

Count units by type to decide when to expand:

```python
# Each Builder Bot increments a counter
current = ct.read_store(2)
ct.write_store(2, current + 1)  # buffered, so safe from race conditions
```

Because writes are buffered you need to be careful: `read_store(2) + 1` reads the last round's total, so you're incrementing from the previous turn's count. This is consistent and race-free — just account for the lag.

### Status flags

Use individual slots as boolean flags:

```python
SLOT_UNDER_ATTACK = 3

if enemy_nearby:
    ct.write_store(SLOT_UNDER_ATTACK, 1)

if ct.read_store(SLOT_UNDER_ATTACK) == 1:
    # enter defensive mode
    pass
```

## Tips

- Assign slot numbers as named constants at the top of your file to avoid magic numbers
- The one-round delay is a feature, not a bug — it guarantees every bot sees the same store state throughout a round
- There is no lock or mutex; the buffered write model makes concurrent updates safe by design
