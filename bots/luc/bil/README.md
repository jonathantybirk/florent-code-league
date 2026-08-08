# Bil — a team-wide turret ceiling, priced in cost scale

`lofn@86287ec` plus one refusal: no Gunner or Sentinel once
`get_scale_percent()` reaches `TURRET_SCALE_CEILING` (350).

**Not queued.** It is level with its parent locally and the hypothesis it tests
cannot be measured locally at all. It is here so it can be queued the moment
`lofn` has live data to compare against.

## The defect it targets

Every turret cap in this bot is per-Builder — `p.home_gunners_built`,
`p.field_gunners_built`, `p.attack_gunners_built`. So the *team* total is the
cap times the Builder count, and nothing anywhere caps the team.

Internally that is invisible: our own bots do not press us, so a game produces
**3.3 Gunners** and no cap of any kind binds. Decoded live ladder replays say
otherwise:

| | Gunners a game | Harvesters |
|---|---|---|
| **us, live** | **22.7** | 2.7 |
| Pivot (rank 7) | 11.6 | 7.6 |
| I Stone | 1.6 | 4.4 |

At +20 cost scale each, 22.7 Gunners is roughly **450 points of permanent tax**
on every price we pay afterwards — including the Harvesters those same replays
say we are short of. Pivot wins while building half as many.

The comms store is full so a shared headcount is impossible, but
`get_scale_percent` is global, exact and free, and it prices the thing that
actually matters. All seven `build_gunner` and three `build_sentinel` sites go
through the gate.

## Numbers

Three map sets, 156 games a cell:

| vs | combined | |
|---|---|---|
| `lofn` (parent) | 79/156 = **0.506 ±0.078** | +0.2 sd |
| `vili` | 90/154 = 0.584 | +2.1 sd |
| `spar_sniper` | 48/86 = 0.558 | +1.1 sd |

Gunners 3.26 → 2.94, so the ceiling does bind occasionally even internally, and
costs nothing when it does.

**Level with `lofn`, as expected.** A ceiling of 350 cannot matter in games that
build 3.3 turrets. The 22.7-Gunner game only happens live, so this is a live
experiment wearing a local safety check: the local number exists to prove it is
not a regression, not to prove it is an improvement.
