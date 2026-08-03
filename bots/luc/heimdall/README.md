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

The same panel with the atlas taken away, which is what this bot actually is.
Four directly comparable rows, and the one that ships is the last:

| build | atlas | guard | ferry on inference | total |
|---|---|---|---|---|
| `warden_walk` | yes | no | no | 118/168 0.702 |
| `ww_fair` | no | no | no | 96/168 0.571 |
| — | no | no | **yes** | 97/168 0.577 |
| — | no | **yes** | no | 119/168 0.708 |
| **`heimdall`** | no | **yes** | **yes** | **128/168 0.762** |

Two things to read off that. The guard is worth 14pp without the atlas and
17pp with it, so it is not an artefact of map knowledge. And ferrying on the
symmetry inference is worth *nothing* on its own (96 → 97) and +5pp on top of
the guard (119 → 128) — arriving early only pays if you are still alive at
home when you get there.

### Why this bot ferries at a guess when its ancestors would not

`FERRY_ON_INFERENCE` was measured off in the atlas-carrying ancestors at 17/42
against 21/42. That measurement does not transfer. With an atlas the `sighted`
flag is set on round 0 and the relay always runs, so the flag only governed the
handful of games where the lookup missed. With no atlas it governs every game:
a unit does not physically see the enemy Core until it has walked most of the
way there, and the relay it would then ask for is pointless. The flag was
throwing away the entire 20pp the relay is worth (`MAX_RELAY_LAUNCHERS = 0`
scores 0.506 against 0.702). Redone here at 168 games: 119 off, 128 on.

A wrong guess is cheap and self-correcting — the symmetry test strikes a
candidate the moment observed terrain contradicts it — and the farthest
surviving candidate is the truth on 28 of 42 published map-sides.

### The shipped build against the eight strongest bots in the field

21 official maps, both seats, 336 games:

| opponent | | |
|---|---|---|
| `casemate` | 42/42 | 1.00 |
| `vanguard` | 38/42 | 0.90 |
| `valkyrie` | 36/42 | 0.86 |
| `gobbleglitch` | 36/42 | 0.86 |
| `ragnarok` | 35/42 | 0.83 |
| `warden_walk` | 35/42 | 0.83 |
| `vigil` | 34/42 | 0.81 |
| `warden` | 34/42 | 0.81 |
| **total** | **290/336** | **0.863** |

**Every opponent is above 80%.** Getting there was not a new mechanic -- it was
re-measuring three constants that had been tuned on an earlier version of this
same bot and never revisited: the opening ferry (0.807 -> 0.839), the guard
radius (-> 0.857), and the guard's chase distance (-> 0.875 at its best).

The last of them is a deliberate trade. Guard cap 2 scores 294/336 = 0.875 but
leaves `warden_walk` at 0.76; cap 4 scores 290/336 = 0.863 and lifts the worst
matchup to 0.83. Four games of total for the minimum going from 0.76 to 0.83.

### The guard's allowance escalates on emplaced turrets, not on damage

A flat cap of two is the right shape while the enemy is *walking* to our Core
and the wrong one once they are building at it. Traced on `runestone`: the
guard answered their Builder on rounds 10 and 12, spent its allowance, then
watched two more Gunners go up on tiles none of our turrets could reach — a
Gunner fires along eight rays only, so a turret sited to hit a Builder that was
standing somewhere else frequently cannot engage what replaces it.

The escalation that already existed is `_defend_core`'s `1 + damage // 180`.
A Gunner three tiles out deals 10 a round for as long as it stands, so waiting
for 180 of them before allowing a second answer concedes eighteen rounds. The
emplaced turret is the signal; how much damage it has managed is not.
`_guard_allowance` therefore returns `MAX_GUARD_GUNNERS + one per live enemy
turret inside the guard radius`.

Found on a traced loss, then **pre-registered and replicated** on an
independent map set before shipping — the same discipline that killed the
counter-battery idea:

| | control | escalating |
|---|---|---|
| 30 generated maps (set 2) | 74/120 0.617 | **82/120 0.683** |
| 40 generated maps (set 3) | 99/160 0.619 | **108/160 0.675** |
| 21 official maps | 134/168 0.798 | 135/168 0.804 |

### The published enemy-Core guess is sticky

Every Builder runs the symmetry inference on its own vision and publishes its
own favourite to `SLOT_ENEMY_CORE`. Two Builders holding different rejection
sets therefore overwrote that slot with different answers, every round, for as
long as they disagreed.

Traced on `longship`: the published target alternated between the rotation
candidate `(24, 10)` and the x-mirror `(24, 8)` on *every single round*, and
the attacker paced between two tiles from round 19 to round 34 instead of
arriving. `warden_walk` — which has the atlas and so knows the answer on round
0 — emplaced at our Core on round 14 and won 37-0 on Core damage. With the
guess held steady it locks on at round 5 and sights the real Core at round 16.

The fix is one rule: an inference already published by another Builder is
authoritative until *this* Builder has actually disproved it. A sighting still
outranks everything.

Effect on score is small — 266/336 → 270/336 on the pool and +1 on 40 generated
maps, both inside noise — but a target that changes every round is worse than
either of the targets it alternates between, and that is not a tuning question.

### On terrain nobody has tuned against

24 random symmetric maps from `tools/generate_maps.py`, both seats, against the
two strongest bots in the field:

| bot | atlas | total | vigil | ragnarok |
|---|---|---|---|---|
| **`heimdall`** | no | **65/96 0.677** | 35/48 0.73 | 30/48 0.62 |
| `warden_walk` | yes | 46/96 0.479 | 24/48 0.50 | 22/48 0.46 |
| `valkyrie` | yes | 46/96 0.479 | 26/48 0.54 | 20/48 0.42 |
| `ww_fair` | no | 46/96 0.479 | 24/48 0.50 | 22/48 0.46 |

The three control rows landing on exactly 0.479 is the whole point: off the
published pool the atlas is inert, so an atlas bot and its atlas-free twin play
the identical game. The 11-13pp the oracle is worth on the pool is worth
nothing here — and the guard is worth twenty.

A second, independent set of 30 maps (`--seed 4242`) reproduces the size of the
effect exactly: heimdall 74/120 **0.617** against the same atlas-free no-guard
control's 50/120 **0.417**. Twenty points on both sets, drawn from different
seeds, against the two strongest bots in the field.

### CPU

Worst Builder turn 4,987 µs on `longship`, 0 turns over the 10 ms limit across
4,311 unit-turns. The cluster's hardware measured `valkyrie` at 5,944 µs where
this laptop said 3,993, so scale by ~1.5: ~7.5 ms worst case there. Inside the
limit, but not with much room.

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
