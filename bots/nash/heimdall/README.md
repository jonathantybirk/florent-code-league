# Heimdall

`warden_walk` with the offline map atlas removed and a **home guard**: the
Builder standing at our own Core answers an enemy that walks up to it on
*sighting*, instead of waiting for the Core to lose 50 HP first.

Fair by construction. There is no `atlas.py`, no `atlas_data.py` and no import
of either, so this bot plays a generated map, the held-out evaluation set and
the final exactly the way it plays the published pool.

## The change that matters

The lineage's home defence is `_defend_core`, gated on `SLOT_CORE_DAMAGED`.
The Core raises that alarm at `hp <= max_hp - 50` — five Gunner rounds *after*
the enemy turret went up. Traced on a lost `aurora` mirror: our Core took its
first damage on round 28, and the first defensive Gunner went up only after
that, by which point answering cost a turret duel rather than four shots at a
Builder.

Sighting is the cheaper trigger, and it is decisive because of how thin the
attack it interrupts is:

- The entire enemy attack is carried by **one** Builder. Their Core will not
  spawn a replacement while any of their Builders still answers the heartbeat,
  so a Builder killed on our doorstep is an attack that does not come back.
- A Gunner is 10 Ti and kills a 40 HP Builder in four rounds. An emplaced
  enemy Gunner costs 40 HP of shooting *and* whatever it has already put into
  the Core.

`_guard_home` runs before the Launcher ring and before the seal, for the ring
Builder only, and it is idle — free — on any map where nobody comes.

## Measured

21 official maps, both seats, against `valkyrie`, `vigil`, `ragnarok` and
`vanguard`; 168 games per row. Every row is the same chassis with one change.

| build | total | valkyrie | vigil | ragnarok | vanguard |
|---|---|---|---|---|---|
| `warden_walk` (control) | 118/168 **0.702** | 26/42 | 26/42 | 26/42 | 40/42 |
| + guard, r²=64, cap 3 | 142/168 0.845 | 39/42 | 29/42 | 36/42 | 38/42 |
| + guard, r²=36, cap 3 | 145/168 0.863 | 40/42 | 30/42 | 37/42 | 38/42 |
| + guard, r²=36, cap 2 | 147/168 **0.875** | 39/42 | 33/42 | 37/42 | 38/42 |
| + guard on every Builder | 137/168 0.815 | 34/42 | 32/42 | 34/42 | 37/42 |

The mechanism shows in the metrics as well as the score: opponent Builders
alive at round 100 fall from 2.65 to 2.27, and our own Gunners built rise from
5 to 7.

Both constants were measured, not chosen. Radius² 16/25/36/49 →
146/145/147/140; cap 1/2/3/4/6 → 139/147/145/146/145; chase 2/4 → 143/147.
Flat across a wide middle and falling off at both edges, which is the shape a
real effect has. At r²=49 it starts buying turrets for scouts that were never
going to emplace, and each one is +10% on every price paid afterwards.

Only the ring Builder guards: letting all three do it costs the belt the
economy Builder was laying and the ore the miner was walking to.

## Measured and rejected

Kept here so the next session does not re-run them.

- **Core shell** — barriers on all twelve tiles touching the 2×2 Core. The
  mechanic is real (a Gunner's ray stops at the first targetable tile, so a
  solid ring one tile out blocks every seat inside r²=13, and a Builder cannot
  reach the footprint to fire by hand either) but it does not pay: 126 games,
  78 → 67. It cannot be finished before round ~20, our Core takes its first
  damage on round 13, and the barriers come out of the ring Builder's mining
  (harvesters 2 → 1). Sealing the tiles they shoot *from* is the wrong side of
  the problem; killing the Builder that would have shot is the right one.
- **Piercing Gunner seats** — accept a seat whose ray reaches the Core through
  enemy buildings, since a Gunner clears its own line and only a WALL is
  permanent. The failure it fixes is real and was traced: beside a Core
  screened by the enemy's own conveyor line the attacker finds no legal seat
  and wanders. Scoring it is a wash to a small loss — 0.702 →
  0.673/0.690/0.679/0.679 at 0/1/2/4 blockers allowed. The rounds spent
  chewing belt are worth less than the seat.
- **Launcher knobs.** `MAX_RELAY_LAUNCHERS` 0/1/2 → 0.552/0.706/0.683 and
  `RING_MAX_SITES` 0/1/2/3 → 0.611/0.667/0.706/0.698 on a six-bot panel. Both
  were already on their maximum; there is nothing left in that vein.
