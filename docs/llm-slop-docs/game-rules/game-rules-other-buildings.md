# Game Rules — Other Buildings

Source: https://game.code.florent.vc/docs/game-rules-other-buildings

## Barrier

Barriers serve as defensive structures that obstruct movement and create strategic choke points to direct adversaries into concentrated attack zones.

| Property | Value |
|----------|-------|
| HP | 30 |
| Cost | 3 Ti |
| Effect | Makes the tile impassable |
| Blocks LOS | Yes |

### Key Constraints

Important placement restrictions apply: Barriers cannot be placed on wall tiles. Since hostile units can destroy these structures if they concentrate sufficient firepower, reinforcing them alongside turret installations is recommended for optimal defense.

### Implementation Example

```python
if ct.can_build_barrier(pos):
    ct.build_barrier(pos)
```
