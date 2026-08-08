# bulwark — steward_hardened_reinforced + a live headcount

A fork of the flagship with exactly one change, kept because the finding is
real even though the result is not.

## The finding

steward builds two mechanisms around a limitation that does not exist:

* `SLOT_BUILDER_HEARTBEAT`, which all Builders write the same value to, giving
  the Core a boolean "at least one Builder is alive";
* `REPLACEMENT_BANK_THRESHOLD = 260`, a bank size used as a *proxy* for "the
  workforce is too small to spend its income".

Both exist because of this, in the bot's own words:

> A per-Builder bitmask was tried and is impossible: the engine buffers store
> writes to the start of the next round, so every Builder in a round reads the
> same snapshot and ORs its bit onto it, and only the last writer's word lands.

> The cap is on total spawns, not on a live headcount, because buffered store
> writes make a live headcount impossible to publish.

The store claim is correct — I verified the one-round write latency
independently. The conclusion does not follow. `get_unit_count()` returns
"the number of living units currently on this unit's team, including the
core" straight to the Core, no store involved. **It is never called anywhere
in steward.**

The documented cost of the workaround is in its own comment: the heartbeat
proves only that ONE Builder lives, so a team that loses two of three never
replaces them and mines into a bank nothing is left to spend — "down to one
Builder by round 45 on sweden, dead on round 103 holding 358 titanium".

## The result: neutral

`bulwark` replaces the bank proxy with `get_unit_count() - 1` and spawns a
replacement on the real shortfall. Against an identical panel (vidar, odin,
ragnarok, vigil; 15 official maps, both seats, 60 games each):

| | wins | core hp at end | worst stall |
|---|---|---|---|
| steward | 49/60 | 285 | 82.5 |
| bulwark | **49/60** | 296 | 66.0 |

Head-to-head over 15 maps both seats: **6–6 with 3 draws**.

Identical win count. Marginally better core hp and a shorter worst stall,
neither large enough to claim. The mechanism is sound and the failure it
targets is real; it simply is not what is costing steward games, which means
the bank proxy was a good enough approximation after all.

Worth keeping because the reasoning error is likely repeated elsewhere: any
decision in this codebase that reads "the store cannot tell us X" should be
re-checked against the Controller API first.


## Also tried: rotation-invariant ore tie-break — no effect

The opening ore list was sorted `(distance, tile.x, tile.y)` — an ABSOLUTE
coordinate tie-break, which on a rotationally symmetric map points both seats
at the same map corner: behind seat A's Core, and across the board for seat B.
That looked like a clean explanation for a measured, systematic seat-B delay.

The seat gap is real and reproduces exactly:

| | seat A | seat B | gap | first harvester A / B |
|---|---|---|---|---|
| steward | 0.817 | 0.667 | +0.150 | 7.9 / 10.5 |
| bulwark | 0.817 | 0.650 | +0.167 | 7.9 / 10.5 |

Seat B is slower at everything downstream: first Gunner 26 vs 23, conveyors
11.3 vs 12.8, titanium 555 vs 619, Builders 3.5 vs 4.0.

Replacing the tie-break with a rotation-invariant one (rank by distance FROM
the enemy Core, which under 180-degree symmetry is identical for both seats)
moved first-harvester from 7.9 to 7.8 on seat A and **not at all** on seat B.
Reverted.

Why it does not bite: the ore list normally comes from `atlas.ores`, and
deposits are rarely at exactly equal distance, so the tie-break almost never
decides anything. The bias is real in the code and is not the cause.

**The seat gap remains unexplained.** It is worth more than anything else
measured here — 15pp against every opponent — and the cause is upstream of the
first Harvester, not in combat, which is why steward's own combat-side attempts
were all "inert". Next place to look: the spawn ring's tile ordering, and
whether seat A simply claims contested mid-map deposits first by acting first.
