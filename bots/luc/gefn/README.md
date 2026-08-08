# Gefn — claims that expire

`syn@…` with a round-stamp packed into each claim slot, so any Builder can
release a stale claim without having to observe it.

**Not queued.** It fixes a real defect and wins nothing.

## The defect

`hlin` releases a claim when a Builder can *see* a finished Harvester on the
claimed tile. If nobody looks there again — the holder died, the tile is far,
vision moved on — the claim never comes back. Measured on `syn`:

    NOSLOT 178 in three games, holding [306, 174, 438, 364] every time

The same jam `freyja` (2 slots → 4) and `hlin` (recycle on sight) each partly
fixed, still there one level deeper.

The store word is a full 32-bit int and `pack_pos` uses about ten bits, so the
claim carries `round << 12` and `_expire_stale_claims` drops anything older than
`CLAIM_TTL_ROUNDS = 60`. Release now matches on the position half rather than
the exact value.

**After: NOSLOT 178 → 7.** The jam is gone.

## And it wins nothing

Four opponents, three map sets, 624 games:

| vs | on-pool | off-pool | combined | |
|---|---|---|---|---|
| `syn` (parent) | 36/72 | 42/84 | **78/156 = 0.500** | 0.0 sd |
| `hlin` | 39/72 | 39/84 | 78/156 = 0.500 | 0.0 sd |
| `nanna` | 39/72 | 40/84 | 79/156 = 0.506 | +0.2 sd |
| `vili` | 33/72 | 48/84 | 81/156 = 0.519 | +0.5 sd |

Harvesters 2.97 → **2.99**.

**The freed turns had nowhere better to go.** Every exit from `_pick` is now
instrumented and none of them is what caps the economy: not the slot count, not
the leak, not observation, not the network cap, not routing, not time per
deposit (median 8 turns), not miner survival (0 of 9 died). Three Harvesters is
simply what this bot does with a map, and the reason is not in the mining loop.

Committed because an immortal claim is a defect whatever it costs, and because
the next person to look at this should not have to find it a fourth time.
