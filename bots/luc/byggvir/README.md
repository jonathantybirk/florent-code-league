# Snotra — choose a deposit by what it costs to deliver

`mimir@62df0ec` with one change in `_pick`: deposits are priced by the belt they
need, not by how far it is to walk to them.

## The defect

`_pick` sorted candidates by travel distance and then `break`s on the first
routable one:

```python
for ore in candidates:
    route = _route(p, ore)
    travel = _distance(p, me, _adjacent(p, ore))
    if route is None or travel is None:
        continue
    # Nearest-first is robust under fog; route length breaks ties. The
    # offline planner supplies the upper bound for later score tuning.
    best = (travel, len(route), ore, route)
    break
```

`len(route)` — the belt — is computed and never compared, exactly as the comment
concedes. A deposit three tiles away behind a wall, needing fifteen conveyors,
beats one five tiles away needing four.

## Why it matters

A conveyor is 3 Ti and **+1 on the team's cost scale** — measured with
`get_scale_percent`, not assumed: from base 100, a Builder takes it to 120, a
conveyor to 121, a barrier to 122, a Gunner to 142. Forty conveyors is roughly
120 Ti *and* a +40% tax on every price the team pays afterwards.

That is affordable in a 600-round game and ruinous in a 150-round one, and the
ladder is full of the latter. The Flotte Experience v38 swept us 0–5 on
2026-08-08 in games of 133–172 rounds:

| map | our belts | theirs | our Core damage | theirs |
|---|---|---|---|---|
| atoll | **47** | 8 | 203 | 657 |
| archipelago | **40** | 9 | 452 | 1,006 |
| hive | **36** | 17 | **0** | 733 |
| saga | 37 | 17 | 238 | 861 |

On hive we laid 36 conveyors, built one Gunner at round 114, dealt zero damage,
and died on 133.

## The change

At most `BELT_SCORE_CANDIDATES = 4` deposits are priced — the list is still
ordered nearest-first, so those are the ones worth pricing — and the winner
minimises `len(route) * BELT_TILE_WEIGHT + travel` with `BELT_TILE_WEIGHT = 3`.
A belt tile is permanent and taxed; a step of walking is one Builder-turn and
nothing more, so a belt tile is worth several steps. Bounded by work, so the
extra `_route` calls cannot cost a turn.

## Numbers

21 official maps × both seats, 42 games a cell:

| vs | | |
|---|---|---|
| `mimir` (current best) | 26/42 | **0.619** |
| `hodr` | 25/42 | 0.595 |
| `gefjon` | 22/42 | 0.524 |
| `vidar` | 29/42 | 0.690 |
| **mean** | 102/168 | **0.607**, floor 0.524 |

Independent second sample, 12 generated maps × both seats against `mimir`:
**14/24 = 0.583**. Pooled against mimir that is **40/66 = 0.606**, about 1.7
standard deviations above even.

Head to head against mimir on the pool, the mechanism shows up where it should:

| | snotra | mimir |
|---|---|---|
| conveyors | **11.00** | 12.62 |
| harvesters | 1.83 | 1.81 |
| turrets | 5.43 | 5.33 |
| Core damage dealt | 784 | 734 |

**Honest caveat.** On the generated maps the belt counts are nearly equal (7.42
against 7.58) and it still wins 0.583, so the conveyor saving cannot be the
whole story there — the change also alters *which* deposit is taken, not only
how much belt it needs. The mechanism is confirmed on the pool; on generated
terrain the win is real but unexplained.

CPU: worst turn 5,478 us against the 10,000 limit, zero over. Deterministic:
three identical runs agree to the last unit of titanium.

## Status

Committed, **not queued on the farm**. Both agents paused submissions pending
something with live-relevant promise, and this session established twice over
that a local edge of this size cannot be resolved in the 5–15 matches a queue
slot buys — while the farm's promotion rule will happily put a build on the
rated ladder on one favourable five-game series. Beating the current best on two
independent local panels is the strongest local result of the session, and it is
still only a local result.
