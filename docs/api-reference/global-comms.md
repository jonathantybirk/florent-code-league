# Global Communication Store

Source: https://game.code.florent.vc/docs/global-comms

The **Global Communication Store** provides a shared communication mechanism through 16 integer slots that persist across turns, enabling bots to coordinate without hardcoding values.

## API

| Method | Returns | Description |
|--------|---------|-------------|
| `ct.read_store(slot)` | `int` | Read the value in slot `slot` (0–15). |
| `ct.write_store(slot, value)` | `None` | Write `value` to slot `slot` (0–15). |

**Example usage:**

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

## Timing: Writes are Buffered

Writes are not applied immediately. They commit at round's end and become readable the following round. This ensures every bot observes consistent store state throughout the entire round.

| Round | Event |
|-------|-------|
| N | Bot A calls `write_store(0, 42)` |
| N | Bot B calls `read_store(0)` → reads **0** (previous round's value) |
| N+1 | Bot B calls `read_store(0)` → reads **42** |

## Team Isolation

Each team maintains its own separate store. Writes remain invisible to opponents, and opponent data cannot be read.

## Usage Patterns

### Scouting Target

Designate fixed slots for shared attack targets:

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

### Unit Census

Count units by type to decide when to expand:

```python
# Each Builder Bot increments a counter
current = ct.read_store(2)
ct.write_store(2, current + 1)  # buffered, so safe from race conditions
```

The buffering ensures consistency: the read reflects the previous turn's total, so increment operations remain race-free.

### Status Flags

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

- Assign slot numbers as named constants at the top of your file to avoid magic numbers.
- The one-round delay is a feature, not a bug — it guarantees every bot sees the same store state throughout a round.
- There is no lock or mutex; the buffered write model makes concurrent updates safe by design.
