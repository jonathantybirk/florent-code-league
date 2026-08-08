# Syn — a shared "already harvested" set, in one store slot

`hlin@a72a7dc` plus a done-mask. **Not queued:** the mechanism works perfectly
and the win rate does not move.

## The problem it solves

Instrumented close reasons over three games:

    CLOSE built_harvester             6
    CLOSE found_existing_harvester   13    <- all 13 are our own Harvesters

**68% of mining arrivals confirm work already done.** Builders cannot tell each
other what they have finished — all 16 comms slots were allocated — so one walks
to a deposit another already worked. `var` tried keeping the claim on a finished
deposit instead and scored 0.474: a blocked slot costs more than a wasted walk.

## The mechanism

The store word is a full 32-bit int — probed by writing 2147483647 and reading
it back — so 31 deposits fit in **one** slot as a bitmask, leaving the claim
slots alone. Bought with one launch-request slot (`range(2, 6)` → `range(2, 5)`).

The index is a hash of the tile, not a position in a shared list: the atlas only
covers the 21 published maps and the ladder's pool is held out, so anything
atlas-indexed is dead where it matters. A hash collides — 12 deposits in 31
buckets is about two colliding pairs — so the mask is **advisory**: it reorders
preference and is ignored entirely when it would leave nothing to mine. A
collision costs a detour, never a deposit.

## It does exactly what it says

    syn:  CLOSE built_harvester 8,  found_existing_harvester 0

**The wasted arrivals are gone**, and Harvesters rise 2.75 → **2.97**.

## And it does not win

Four opponents, three map sets, 560 games:

| vs | on-pool | off-pool | combined | |
|---|---|---|---|---|
| `hlin` (parent) | 0.542 | 0.464 | **78/156 = 0.500 ±0.078** | 0.0 sd |
| `nanna` | 0.542 | 0.476 | 79/156 = 0.506 | +0.2 sd |
| `vili` | 0.458 | 0.590 | 82/155 = 0.529 | +0.7 sd |
| `spar_sentinel` | 0.596 | 0.512 | 52/93 = 0.559 | +1.1 sd |

Exactly level with its parent. This is the **fifth** time this session that a
Harvester increase has failed to move the win rate (`saga`, `syn`-the-ammo-build,
`gna`, `var`, and now this). The count is not the binding constraint in games
against our own bots; whether it is against the ladder — which finishes long
games on 10,045 titanium to our 20 — is a question only the ladder can answer.

Committed unqueued behind `lofn`, `hlin` and `nanna`.
