# Game Rules — Resources

Source: https://game.code.florent.vc/docs/game-rules-resources

**Titanium** serves as the singular in-game currency in Florent Code League, functioning as a shared team balance. All units withdraw from and contribute to this collective pool.

To check your current titanium:

```python
titanium = ct.get_global_resources()
```

## Income Sources

### Passive Income

Every team automatically receives 10 titanium every 4 rounds regardless of territorial control.

### Harvesters

Builder Bots can construct Harvesters on ore tiles to generate ongoing income. These structures operate without a construction limit and don't consume the 50-unit cap. Greater ore tile control amplifies your economic advantage throughout the match.

## Cost Scaling

Build expenses increase as you construct more entities, scaling based on production volume rather than time. Each structure type contributes differently: conveyors add +1%, harvesters add +5%, combat units add +10%, and builder bots/sentinels add +20%. Destruction reverses these contributions.

Query current costs using:

```python
scale = ct.get_scale_percent()
titanium_cost = ct.get_gunner_cost()
```

**Key insight:** early expansion is disproportionately valuable. Early purchases cost significantly less than equivalent late-game acquisitions.

## Economic Strategy Notes

- Harvesters recover their construction cost within dozens of rounds.
- Eliminating enemy Harvesters eliminates their income generation.
- Movement is free—Builder Bots can traverse open terrain without expenditure, allowing resources to focus on structures and defense.
