# Tyr

Mjolnir's 2.3.4 chassis with four changes, all of them aimed at things the
belt and the opening were measurably bad at rather than at the combat numbers
the patch repriced. Everything here was measured on fcode 2.3.4; nothing from
before the Aug 4 turret patch was assumed to still hold.

No map oracle, inherited from mjolnir: no atlas module and no import of one,
so this plays a generated map, the held-out set and the final the way it plays
the published pool.

## Why not steward

The brief was "build on steward with the newest innovations". Steward is
`warden` plus one fix — the Core replaces Builders it has lost, triggered off
a bank threshold because, in steward's own words, "a live headcount is not
available". Mjolnir's chassis has since found one: `SLOT_BUILDER_HEARTBEAT`
carries a round stamp and one bit per Builder, and the Core reads the previous
round's mask and counts exactly who answered. `MAX_LIVE_BUILDERS` then
replaces the dead directly instead of inferring them from an idle bank.

A diff of the two constant sets is the whole argument: steward has two
constants mjolnir lacks, both of them that superseded fix, and mjolnir has
twenty-nine steward lacks. Building on steward would have meant porting all
twenty-nine across a 1,070-line builder diff to arrive at mjolnir. So the base
is mjolnir and the four changes below are the new work.

## The four changes

### Belt line-of-sight

A conveyor inside an enemy turret's ray is destroyed about as fast as it is
rebuilt. `REPAIR_ATTEMPT_LIMIT` already capped the bleeding *after the fact* —
the traced `bridge` line was rebuilt 22 times for 66 Ti and 22% compounding
scale before the cap, three times and 9 Ti after it — but a written-off tile
is still a broken line and a replan.

`_route` now tries three plans in order:

1. out of every remembered enemy turret's current ray,
2. out of everything one 10 Ti rotation could put under fire,
3. anywhere at all.

The third pass is what keeps this from costing deposits: ore reachable only
through fire is still mined, just knowingly. The detour, when one exists, is
free.

The load-bearing part is *remembered*. `_enemy_turret_cover` reads live vision
and goes blind the moment a turret leaves sight — which is exactly the
condition the belt is laid under, since it runs across tiles nobody is looking
at. `_remember_enemy_turrets` now stores each turret's kind and facing as well
as its tile, and the cover set is rebuilt only when a turret is first seen or
seen to have rotated, because a per-call recompute is the shape that puts a
Builder over the 10 ms turn limit.

### Ore re-targeting

`_pick` ranked the deposits a Builder had seen and committed. Nothing
reconsidered, so a Builder that revealed a nearer deposit during a twenty-round
walk kept going to the one it chose at spawn and laid a longer belt to reach
it.

Re-picking is free until the first conveyor of the line is down — after that
the tiles already bought are sunk cost and abandoning the line also leaves a
stub on the map — so `p.current_route_tiles` being empty is the entire
precondition. Candidates are ranked on walk distance plus belt length and have
to beat the incumbent by `RETARGET_MARGIN`, which exists so a one-tile
improvement cannot make a Builder oscillate between two deposits and mine
neither.

### The Core's ore hints

The Core already knows where the nearest ore is: it sorts the deposits inside
its own vision on the first turn and picks the miners' spawn-ring tiles from
that list. It then kept the list to itself, leaving each Builder to rediscover
the same deposits a tile of fog at a time along an exploration lattice that
steps in strides of four.

`SLOT_BUILDER_TICKET` is a 32-bit slot carrying an 8-bit counter, so the two
nearest deposits now ride along in the spare bits at full 10-bit `pack_pos`
resolution: 8 + 10 + 10 = 28 bits of 32. The coarse 2×2 fallback that was
planned in case they did not fit was not needed — `pack_pos` tops out at 958
on the largest legal map.

Two details make it safe. The Builders increment the ticket through
`pack_ticket`, so incrementing carries the hints forward instead of wiping
them; and the Core writes the slot exactly once, on its first turn, because
rewriting it every round would reset the ticket and hand every Builder index
zero. Hints are advisory: a Builder claims a hinted deposit through the
ordinary `CLAIM_SLOTS` path and re-verifies it is really ore before building,
so a stale or contested hint costs one wasted look.

### The Launcher pad obeys the turret seats' rule

`COVER_TIER_SEATS` already refused to seat a turret where an enemy turret can
shoot it. `_launcher_ring_targets` sorted purely by distance to the enemy Core,
and with `RING_MAX_SITES = 1` that sort *is* the pad decision — so it
unconditionally preferred the enemy-facing tile, which is the tile an enemy
turret is most likely to be aimed at. It now sorts on cover tier first.

Harvesters get no such rule and cannot: a Harvester goes on the ore or
nowhere, so there is no alternative tile to prefer.

## Verification

Live, not just parsed. Ticket packing round-trips through three Builder
increments with hints intact and indices 0/1/2 distinct (traced on `sweden`:
the Core published `(2,6)` and `(3,6)` and all three Builders read them). The
re-target check reaches its candidate loop in play (traced on `aurora`). All
four bots pass the 10 ms turn limit with p75 ≤ 1.05 ms.

## Panel results

See NOTES.md. The combined bot lost to its own base on the first 42-game
head-to-head, and the four changes were then priced one at a time.
