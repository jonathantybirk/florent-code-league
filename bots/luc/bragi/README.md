# Bragi — the Sentinel preference, extended to a path doctrine turns off

`snotra_h@6951e03` with `FIELD_TURRET_SENTINEL`, routing `_engage_with_turret`
through `_turret_kind` the way `_defend_core` already does.

## Why

Big O is rank 11 and our worst matchup on the ladder at **3/25 (0.12)**.
Decoded, all five games say the same thing:

| game | Big O | us |
|---|---|---|
| 1 | sentinel x2 @r4, harvester x2, conveyor x13 | gunner x3 |
| 2 | sentinel x2 @r32, harvester x3, conveyor x28 | gunner x4, launcher x1 |
| 3 | sentinel x2 @r31, harvester x1, conveyor x3 | launcher x3, gunner x1 |
| 4 | sentinel x2 @r9, harvester x1, conveyor x2 | gunner x4 |
| 5 | sentinel x2 @r20, harvester x2, conveyor x7 | gunner x2, harvester x5 |

Exactly two Sentinels every game, and a Gunner answer from us every game. A
Sentinel reaches r^2=32 and ignores obstacles; our Gunner reaches 13 and is
blocked by anything in the line, our own conveyor forest included. Two of those
games ended with **72–76 ammunition unspent** — shots we had paid for and had
no shooter in range to take.

`constants.py` already argued the Sentinel case for the home guard and
explicitly excluded the field path: *"the extra reach buys nothing."* Against a
Sentinel opponent that is the one claim the replays contradict, so this build
tests it.

## What it changes

`_engage_with_turret` picks its kind with `_turret_kind`, searches seats at
that kind's reach, and falls back to a Gunner when a Sentinel is unaffordable
or unseatable — the same three lines `_defend_core` has always run.

## Numbers, and why they are weak by construction

150 generated maps, both seats, 300 games a cell.

| vs | `snotra_h` | `bragi` | |
|---|---|---|---|
| `spar_sentinel` | 0.4300 | **0.4467** | +0.017 (+0.4 sd) |
| `undertow` | 0.6000 | **0.6000** | 0.000 |

Sentinels built per game went 0.28 to 0.58, so it does fire — but only on part
of the panel, and that is the finding worth keeping:

**`_FIELD_GUNNERS = {RUSH: 0, FORTIFY: 2, BLITZ: 0}`.** `_engage_with_turret`
returns immediately when the cap is zero, so on RUSH and BLITZ maps this build
is behaviourally identical to its parent. The change can only act on FORTIFY
maps, which is a minority of any panel, and a test on mixed maps therefore
cannot resolve it.

That is the third time in this session a mechanism has been patched into a path
some doctrine switches off (see `project_doctrine_disables_mechanics`). The
number above is not evidence that Sentinels do not help in the field; it is
evidence that this code mostly does not run. Anyone picking this up should
either test FORTIFY-only or raise `_FIELD_GUNNERS` under RUSH first.

Not queued.
