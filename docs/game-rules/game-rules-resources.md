# Game Rules — Resources

Source: https://game.code.florent.vc/docs/game-rules-resources

## Titanium

Titanium is the only resource in Florent Code League. It is a shared team balance — all your units draw from and deposit into the same pool.

```python
titanium = ct.get_global_resources()
```

## Income sources

### Passive income

All teams receive 10 titanium every 4 rounds passively, regardless of map control.

### Harvesters

Builder Bots can construct Harvesters on `ORE_TITANIUM` tiles to generate passive income — see [Harvester](game-rules-harvester.md) for full mechanics. There is no cap on the number of Harvesters (they're buildings, not units, so they don't count against the 50-unit cap either). Controlling more ore tiles compounds your income advantage over the match.

## Cost scaling

All build costs scale upward as you build more entities — not as a function of elapsed rounds. Each conveyor/splitter/barrier built adds +1% to your team's scale factor, each harvester +5%, each gunner/launcher +10%, and each builder bot/sentinel +20%; destroying an entity removes its contribution again. A team that builds nothing stays at scale 1.0 (100%) indefinitely, no matter how many rounds pass.

> **Correction vs. the official docs.** The published page's example comment reads `# 1.0 with nothing built`. **`ct.get_scale_percent()` returns a percentage, not a 0–1 fraction** — confirmed at runtime: with nothing built it returns `100.0`, not `1.0`.

```python
scale = ct.get_scale_percent()  # 100.0 with nothing built; rises only as you build
```

Query the current cost of any specific action:

```python
titanium_cost = ct.get_gunner_cost()
```

**Implication:** early expansion is disproportionately valuable. Units and buildings bought in the early game cost less than identical purchases later. Build aggressively early and consolidate your position before costs make expansion prohibitive.

## Economic strategy notes

- Harvesters on ore tiles pay back their build cost within a few dozen rounds at typical scale values.
- Destroying an enemy Harvester denies them income for the rest of the match.
- Movement itself is free — Builder Bots can walk over any open tile without building anything — so titanium can go entirely toward Harvesters, turrets, and other buildings.
