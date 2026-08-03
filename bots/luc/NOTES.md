# Dev notes

Scratchpad for the next session. Not shipped doctrine — ideas to measure, not trust.

## 2026-08-05 — the home guard, and where the map hypothesis actually lands

### The gap was never the attack, it was when the defence wakes up

`_defend_core` triggers on `SLOT_CORE_DAMAGED`, which the Core raises at
`hp <= max_hp - 50` — five Gunner rounds *after* the enemy turret is already
emplaced. Answering then costs a turret duel. Answering on **sighting** costs
four shots at a Builder, and the difference is enormous because of how thin the
attack is: the whole enemy attack is one Builder, and their Core will not spawn
a replacement while any of their Builders still answers the heartbeat.

`_guard_home` in `heimdall`: the ring Builder — the one already standing at our
Core — puts an aligned Gunner on any enemy within r²=36 of the footprint,
before the ring and before the seal. 21 official maps, both seats, against
valkyrie/vigil/ragnarok/vanguard, 168 games a row:

    warden_walk (control)          118/168  0.702
    + guard r^2 64                 142/168  0.845
    + guard r^2 36                 145/168  0.863
    + guard r^2 36, cap 2          147/168  0.875   <- shipped
    + guard on every Builder       137/168  0.815

Against valkyrie alone it is 26/42 → 39/42. The mechanism is visible in the
metrics, not just the score: opponent Builders alive at round 100 fall from
2.65 to 2.27, and our own Gunners built rise from 5 to 7.

Tuning, same panel: radius 16/25/36/49 → 146/145/147/140; cap 1/2/3/4/6 →
139/147/145/146/145; chase 2/4 → 143/147. Radius and cap are flat over a wide
middle and fall off at the edges, which is what a real effect looks like.
r²=49 is where it starts paying turrets for scouts that were never going to
emplace.

Only the ring Builder guards. Letting all three do it is 137: the economy
Builder abandons the belt and the miner stops walking to ore.

### Correction: "ferrying on the symmetry guess is worse" does not hold off-atlas

The pool-era measurement (17/42 against 21/42, `FERRY_ON_INFERENCE` off) was
made on bots that *carry* an atlas. With one, `sighted` is set on round 0 and
the relay always runs, so the flag only ever governed the few games where the
lookup missed. On a bot with no atlas at all it governs **every** game: a unit
does not physically see the enemy Core until it has walked most of the way
there, and the relay it would then ask for is pointless. The flag was quietly
throwing away the whole 20pp the relay is worth (`MAX_RELAY_LAUNCHERS = 0`
scores 0.506 against 0.702).

Redone on the atlas-free chassis, 168 games against valkyrie/vigil/ragnarok/
vanguard: **119 off, 128 on**. It is now on in `heimdall`.

This is the general shape of the atlas problem and worth remembering: a flag
measured on a bot that has the oracle is not measured for a bot that does not.

### What fairness actually costs, separated from the guard

Same panel, 168 games a row, so the four rows are directly comparable:

    warden_walk         atlas, no guard    118/168  0.702
    ww_fair             fair,  no guard     96/168  0.571
    heimdall (v1)       fair,  guard       119/168  0.708
    heimdall + ferry    fair,  guard       128/168  0.762
    gd_r36_c2           atlas, guard       147/168  0.875

So on the **published pool**, against opponents that all carry the atlas, the
oracle is worth about 13pp without the guard and 11pp with it. The guard is
worth 17pp with the atlas and 14pp without. They are close to additive and
neither explains the other.

That 11-13pp is the price of fairness *on maps the atlas knows*. It is zero on
maps it does not, and the measurement is unusually clean. 24 generated
symmetric maps, both seats, against vigil and ragnarok:

    heimdall     (fair,  guard)   65/96  0.677
    warden_walk  (atlas, no guard) 46/96  0.479
    valkyrie     (atlas, no guard) 46/96  0.479
    ww_fair      (fair,  no guard) 46/96  0.479

Three controls landing on exactly 0.479 is the result: off the pool the atlas
is inert, so an atlas bot and its atlas-free twin play the identical game.
Whatever the oracle is worth on the ladder, it is worth nothing in the final,
and the guard is worth twenty points there.

A second, independent set of 30 maps (`--seed 4242`) reproduces the size of it
exactly: heimdall 74/120 (0.617) against the same control's 50/120 (0.417).
Twenty points on both sets, from different seeds.

### Measured and rejected — do not re-run these

- **Core shell.** Barriers on all twelve tiles touching the 2×2 Core. The
  mechanic is real and verified in the API docs — a Gunner's ray "stops at the
  first targetable tile", so a solid ring one tile out blocks every seat inside
  r²=13, and a Builder cannot reach the footprint to fire by hand either. It
  still loses: 78/126 → 67/126. It cannot be finished before round ~20, our
  Core takes its first damage on round 13, and the barriers come out of the
  ring Builder's mining (harvesters 2 → 1). Sealing the tiles they shoot *from*
  is the wrong side of the problem.
- **Piercing Gunner seats.** `_build_basic_gunner` demands `can_fire_from`, a
  line clear *this round*. That is too strict — a Gunner clears its own line,
  and only a WALL is permanent — and the failure is real: traced on aurora, the
  attacker stood beside a Core screened by the enemy's own conveyor line,
  found no legal seat, and wandered for 25 rounds with 40 Ti and 80 ammo in the
  bank. Fixing it does not pay: 0.702 → 0.673/0.690/0.679/0.679 at 0/1/2/4
  blockers allowed. The rounds spent chewing belt are worth less than the seat.
- **The Launcher knobs are finished.** On a six-bot panel, `MAX_RELAY_LAUNCHERS`
  0/1/2 → 0.552/0.706/0.683 and `RING_MAX_SITES` 0/1/2/3 →
  0.611/0.667/0.706/0.698. Both already sit on their maximum.
- **Replacing Builders the enemy killed is a large regression here.** The Core
  gates respawning on `has_live_builder`, which only proves *one* Builder is
  alive; widening the heartbeat slot to a round stamp plus one bit per Builder
  lets the Core count them and refill to three. It looks obviously right — the
  guard kills attackers, so both sides lose bodies — and it is not: on the same
  168-game panel, guard + refill scores **85/168 (0.506)** against the guard's
  147, and refilling to a ceiling of eight is worse still at 70/168. Every
  replacement is +20% on every price the team pays for the rest of the game,
  and an attrition war fought by respawning is lost on cost while being won on
  bodies. **Resolved** — see "the bastion lineage" below. The disagreement with
  `steward` was not a disagreement: refill is chassis-dependent, harmless where
  Builders rarely die and ruinous next to a guard that makes them die.

### The bastion lineage, settled

`warden` → `steward` (+ Builder refill) → `bastion` (+ a *static* home guard:
the second ring site becomes a Gunner facing the likely approach). It was
dropped mid-session without a verdict — never rated, since all three sat
deferred behind the evaluator queue. So it is worth one clean number. Standard
panel, 21 official maps, both seats, valkyrie/vigil/ragnarok/vanguard:

    warden        107/168  0.637   <- the correct control for steward
    steward       109/168  0.649   warden + refill          +2, noise
    bastion       110/168  0.655   steward + static guard   +1, noise
    warden_walk   118/168  0.702   Launcher caps
    heimdall      136/168  0.810   atlas-free + reactive guard

Three conclusions, all of them corrections:

1. **Refill is neutral on this chassis, not a regression.** 107 → 109. It is
   catastrophic only alongside the reactive guard (147 → 85), because that
   guard is what makes both sides lose bodies. Real interaction, not a
   contradiction.
2. **A static guard is worth nothing: +1 game.** The reactive guard is worth
   **+29** over the same control. Pre-placing a turret facing where the enemy
   probably comes from is not the same mechanic as answering the intruder you
   can actually see, and only the second one pays.
3. **"steward is off the trade-off frontier" was a narrow-panel artefact.** It
   was measured on three hand-picked opponents (prospect / ragnarok_fair /
   vigil@60d5afa), scored 84/126 against warden's 79, and the four-bot panel
   reverses the sign to noise. Two opponents chosen as poles of a trade-off are
   a probe, not a panel; do not draw a conclusion from one.

So bastion is correctly dead — not because it regresses, but because it is flat
where the chassis it was abandoned for is 26 games better.

### Everything else tried on the heimdall chassis, against 128/168

### Everything else tried on the heimdall chassis, against 128/168

Same panel, same 168 games, all built on the shipped atlas-free bot:

    BLITZ keeps a guard (2 attackers, not 3)   134/168  0.798   <- shipped
    guard leashed to ore within 8 of the Core  130/168  0.774
    counter-battery at the enemy Core          129/168  0.768
    RELAY_STOP_DISTANCE 7 -> 4                 127/168  0.756
    guard cap 3 instead of 2                   127/168  0.756
    ferry only on a *sole* surviving symmetry  121/168  0.720
    FORTIFY with two economy Builders          110/168  0.655

Only the first is a real effect. The BLITZ hole is worth understanding: that
doctrine was the one with no ring Builder, so it had no guard at all, on
exactly the maps where the enemy attacker arrives soonest.

The ferry row is worth reading twice: waiting until the symmetry inference has
only one surviving candidate before ferrying is *worse* than ferrying at the
farthest guess immediately (121 against 128). Being right early beats being
certain late, and a wrong guess self-corrects the moment terrain contradicts it.

The last row is the interesting negative. The FORTIFY role split was measured
at 2-12 long before a working defence existed, and the obvious hypothesis was
that a bot which cannot be killed should take the closed maps to the round-1000
economy tiebreak. It is still wrong, by more than the original margin.

### Counter-battery: a +11-game result that did not replicate

Worth writing down as a worked example of the trap this file keeps warning
about. `_engage_with_turret` is capped at zero field Gunners under RUSH, so
the attacker never answers the defender shooting its battery. Letting it build
two, but only within 6 tiles of the *enemy* Core (where a defender cannot walk
away from the turret, which is the measured reason field Gunners fail on open
ground), looked like a real find:

    30 fresh generated maps, vs vigil and ragnarok
      heimdall            74/120  0.617
      + counter-battery   85/120  0.708      <- +11 games, all of it ragnarok

Then it was replayed on the other, independent generated set and on the pool:

    24 generated maps (set 1)   65/96 -> 66/96    +1
    21 official maps            128/168 -> 129/168 +1

Then, because two sets disagreeing is not an answer, a third set of 40 fresh
maps was drawn and the prediction written down first: *counter-battery gains
against ragnarok and is level against vigil.* It failed.

    40 generated maps (set 3)   99/160 -> 101/160  +2 (ragnarok 55 -> 56)

Full ledger: +1, +11, +2 on three unknown sets and +1 on the pool -- 15 games
in 544, all of it one set. Not shipped. The mechanism is still sound and may
be worth revisiting with a sample that can resolve it, but "it worked on the
set I found it on" is not a measurement, and a pre-registered prediction is
the cheapest way to find that out.

Same story, smaller: leashing the guard's ore claims to within 8 tiles of the
Core (130/168 pool, 75/120 set 2, both +1 or +2) and rebuilding guard turrets
that have been shot off (76/120 set 2, +2). All inside noise.

### The guard's cap was the next real thing, and it replicated

Tracing a loss beat guessing again. On `runestone` the guard fired on rounds 10
and 12, spent its cap of two, and then watched valkyrie put two more Gunners on
tiles none of our turrets could reach. A Gunner has eight rays; a turret placed
to hit a Builder standing somewhere else usually cannot engage what replaces
it, and `_defend_core`'s own escalation needs `180` damage before it will allow
a second answer.

`_guard_allowance` = `MAX_GUARD_GUNNERS` + one per live enemy turret inside the
guard radius. Pre-registered before the replication ran ("beats 74/120 on set 2
by roughly +5pp"):

    30 generated maps (set 2)   74/120 -> 82/120   +6.6pp
    40 generated maps (set 3)   99/160 -> 108/160  +5.6pp
    21 official maps           134/168 -> 135/168  +0.6pp

Pooled over both unknown sets: 173/280 -> 190/280, +17 games. Shipped.

Tried at the same time and *not* shipped: falling back to healing the Core when
the guard has no firing solution (heal is 4 HP for a flat 1 Ti and needs no
alignment, so it looked like the natural partner). Pool 135/168, set 3 101/160
-- +1 and +2. A wash.

### A real bug: the published enemy-Core guess flip-flopped every round

`_update_enemy_core_inference` ends with each Builder writing *its own*
favourite surviving candidate to `SLOT_ENEMY_CORE`. Builders reject candidates
from their own vision, so two of them with different rejection sets overwrite
that slot with different answers on alternate rounds, indefinitely.

Instrumented on longship, heimdall vs warden_walk:

    RUSH  5 at (10, 9) target (24, 8)
    RUSH  6 at (11, 9) target (24, 10)
    RUSH  7 at (11,10) target (24, 8)
    ...
    RUSH 19 at (19, 7) target (24, 8)
    RUSH 20 at (19, 8) target (24,10)      <- pacing, not travelling
    ... to round 34

The attacker's BFS target reversed every round, so from round 19 it walked back
and forth between two tiles for fifteen rounds. warden_walk, which has the
atlas and knows the answer on round 0, emplaced at our Core on round 14; its
own Core took zero damage all game.

Fix: an inference another Builder has already published stands until *this*
Builder disproves it. Same trace afterwards locks on at round 5 and sights the
real Core at round 16. Worth +4/336 on the pool and +1/160 on generated maps --
inside noise both times, which is worth stating plainly: this shipped because a
target that changes every round is a defect, not because the score moved.

Worth checking the same class elsewhere. `SLOT_SYMMETRY_REJECT_START +
min(builder_index, 1)` gives three Builders two slots, so Builders 1 and 2
clobber each other's rejection masks -- benign only because each writes the
team OR it read, so bits re-propagate.

### A 918-round livelock that costs nothing, and the tool that found it

`benchmarks/pathology.py` counts Builder rounds spent stepping back onto the
tile just left. On the shipped bot across the pool it reports:

    bridge 31.3%   twins 27.6%   string 21.6%   runestone 14.3%   strait 13.3%

bridge, traced: the economy Builder spent **918 of 1000 rounds** alternating
between (10, 6) and (11, 6). The cause is in `_explore`'s fallback. Once every
stride point is explored it walks to the farthest of the four corners *from the
current position* -- and the two farthest corners are symmetric about the
Builder, so stepping toward one makes the other farther and it flips back next
round. A patrol of two tiles, forever.

Two fixes, both obviously more correct than the livelock, both measured on the
8-bot pool panel and 40 generated maps:

    shipped (livelock present)   270/336  0.804   110/160  0.688
    latch the chosen corner      268/336  0.798   110/160  0.688
    go home when idle            264/336  0.786   110/160  0.688

All three land on *exactly* 110/160 on the generated maps, which is the
cleanest possible statement of the result: off the pool the idle Builder's
behaviour makes no difference whatsoever.

The **attacker** livelocks the same way and it is not the idle case, so this
looked like the one that would pay. On generated `r18`, which we lost, the
attacker spent 81 of 193 rounds alternating between (22, 8) and (22, 7): it
reaches the enemy Core, `_build_basic_gunner` finds no legal seat, the breaker
and the Sentinel both decline, and the fallthrough is `_explore` -- which walks
*away* from the only target that matters and then paces. Replacing that
fallthrough with `_harass`, so it stays in their half shooting the belt and is
still standing there when a seat frees up, flips r18 from a loss at round 193
to a win at round 413 and takes its pacing from 30.7% to 0.9%.

    shipped                      270/336  0.804   110/160  0.688
    attacker harasses instead    268/336  0.798   111/160  0.694

Also neutral: -2 and +1 over 496 games. It does redistribute -- valkyrie and
warden each +1, vigil -3 -- but the total does not move.

### Posting the idle Builder as a picket -- the best of the five, still not enough

Suggested rather than derived, and the reasoning is better than "stop pacing":
the whole defence triggers on *sighting*, sighting needs vision, a Builder sees
r^2 20, and Builders block movement. So an idle body posted between the two
Cores buys the guard warning *and* plugs a tile. `_picket_post` picks the
enemy-facing, narrowest known tile 4-7 from our own Core, walks there once and
stands still.

    shipped                     270/336  0.804   110/160  0.688
    picket, 4-7 out             264/336  0.786   112/160  0.700
    picket, 6-10 out              --             112/160  0.700

It is the only one of the five idle behaviours that is **positive on unknown
maps**, and on bridge it is transformative: 9,480 titanium collected against 70
and the round-1000 tiebreak won, where the shipped build loses that map and
"go home" managed 7,240. It still costs six games on the pool.

"Stand *beside* the lane, not *in* it" was the obvious refinement -- our own
attacker and our own belt have to use the chokepoint, and a body in it blocks
them exactly as well as it blocks theirs. Three ways of asking, on the four
pool opponents (shipped 131/168) and the 40 generated maps (shipped 110/160):

    picket, narrowest tile           125/168   112/160
    prefer open tiles (tie-break)    125/168     --
    same, distance bucketed          126/168   112/160
    exclude our own _bfs_path,
      require adjacency to it        126/168   112/160

The first two tie-breaks never fired: the rank's leading term is the distance
to the enemy Core, which is unique per tile, and bucketing it does not help
because in open ground every candidate has four openings. Only the last one
actually moves the chosen tile, and it is worth **+1 game in 168**. The
hypothesis is right in direction and far too small to matter.

Two things the first pass did *not* test, and should have. The post was aimed
at the **inferred enemy Core** -- a symmetry guess -- not at where enemies were
actually seen, and it was **static**, not a patrol.

`_remember_threats` records every enemy unit seen within 12 of our own Core and
`_threat_bearing` aims the post along the mean *direction* of those sightings.
The direction, not the centroid: sightings are recorded near our Core by
construction, so their mean sits almost on top of it and the first version of
this collapsed to standing at home (bridge against vigil: 7,240 titanium
collected, exactly the "go home" number). Projecting the bearing back out past
the picket band fixes it (9,480, level with the shipped build's 9,490). `_picket_route` then spreads three posts >= 4 apart across
that sector and walks them in a cycle.

    shipped (paces)                     131/168  0.780   110/160  0.688
    picket at the inferred Core         125/168  0.744   112/160  0.700
    picket at the observed bearing      126/168  0.750   111/160  0.694
    patrol of three posts, observed     128/168  0.762   111/160  0.694

Aiming at evidence rather than at the symmetry guess is worth **+1 game in
168**. Patrolling rather than standing is worth **+2**. Both point the right
way; neither is close to the 6 games the whole family gives up on the pool, and
on generated maps all four sit inside one game of each other.

So the answer is not about how the post is chosen or whether the body moves.
The picket family costs about six games on the pool and gains about two on
generated maps, and every refinement of it lands inside noise.

**Five livelock and idle-behaviour fixes across two different Builders, and
only the picket is positive anywhere.** Take that
as the finding rather than as four failures: a Builder pacing is a Builder that
has run out of things worth doing, and giving it a tidier way to do nothing is
still nothing. The place to look for wins is what puts it in that state -- a
saturated economy with no reachable ore, or an enemy Core with no legal seat --
not the pacing itself.

**Neither is worth shipping.** Which is the finding: a Builder that has no ore
left to claim and no ground left to see has nothing valuable to do either way,
so the wasted rounds are a symptom rather than a cost. Pacing near the middle
of the map at least keeps vision there; walking home gives that up, which is
probably why it is the worst of the three.

The exception is real and worth remembering: on bridge alone, latching turns a
1000-round titanium *loss* into a win on round 400, and going home turns it
into 7,240 titanium collected against 70. Whatever the aggregate says, a
saturated economy on a corridor map is a case where those rounds do matter.

Revisit with the cluster's 4,000-game samples, where six games is not noise.
The detector is committed either way -- it is cheap, it found both of this
session's livelocks, and a healthy Builder sits at 0-2%.

### The ferry was throwing the wrong Builders, and never gave up

Five of the eighteen losses to `warden_walk` show **zero titanium collected**:
sweden in both seats, vase, sprint, and (against valkyrie) bridge. Not a small
economy -- none at all. Traced on sweden, and it is two separate defects in the
Launcher relay.

**The miner asks to be thrown.** `_move_cardinal_adjacent` calls `_step` with
`allow_launcher` defaulting on, so *any* Builder that fails to path once will
buy or request a throw. On sweden the economy Builder asked to be thrown **two
tiles** -- (2, 2) to (4, 2), (2, 1) to (3, 0) -- and the throws landed it off
the conveyor run it was laying, so it re-planned, walked back, and asked again.
It finished with fifteen conveyors, **zero Harvesters** and zero titanium, on a
map where the same chassis with an atlas has two Harvesters by round 19. Gating
the relay on `p.is_attacker` -- the ferry exists to carry one Builder across
the map, everyone else works on ground it can walk -- takes sweden seat a from
0 to 4,820 titanium and flips seat b and vase seat b from losses to wins.

**Nobody gives up on an impossible throw.** A Launcher can only throw to a
bot-passable tile within r^2 26 in the requested direction. Where that
direction is wall -- sweden's band -- there is no legal landing, the request is
silently ignored, and `_opening_ferry` re-armed its four-round timer on *every*
round, so it never expired. The attacker stood beside its own Launcher asking
to be thrown on every round from 30 to 999 and never attacked at all: 969
requests in one game. Counting consecutive unserviced rounds and walking after
four takes that to 19.

    shipped                        270/336  0.804   110/160  0.688
    + ferry for the attacker only  272/336  0.810   110/160  0.688
    + give up on a dead request    271/336  0.807   110/160  0.688

Both shipped. The score moves by one or two games -- these are 42-game cells --
but a Builder that lays fifteen conveyors and no Harvester, and an attacker
frozen for 970 rounds, are defects whether or not this panel can see them.
`warden_walk`, the worst matchup, goes 24/42 to 26/42.

**Still open: vase seat a.** With both fixes it still collects zero, and there
the belt *looks* right -- Harvester on (1, 7) at round 14, conveyors (1, 2)
through (1, 6), and the mirror-image opponent delivers 2,450 from the identical
shape. Something about that line does not carry. Next session starts there.

### vase seat a: a third zero-economy bug, diagnosed and NOT fixed

With both ferry fixes in, vase seat a still collects **zero** titanium over
1000 rounds against warden_walk's 2,450. Two distinct faults, both confirmed
from the replay and both resistant to the obvious repair:

**The belt loses its last tile and never gets it back.** The conveyor at
(1, 2) -- the one feeding the Core -- dies on round 7. The rest of the line
(1, 3)-(1, 6) and the Harvester on (1, 7) survive all 1000 rounds, so the ore
is mined into a dead end. warden_walk loses (9, 5) twice on the same map and
rebuilds it both times. Ours does not, because `_broken_network_tiles` skips
any tile not currently `is_in_vision`, a Builder sees r^2 20, and the miner
never goes back within sight of the Core.

**The miner is trapped in a pocket.** From round 20 it sits at (0, 8) --
row 8 is `.#.......#.`, a one-wide dead end -- and never moves again. `_explore`
picks a stride point it cannot reach, `_step` fails through to
`_move_while_stuck`, which chooses the neighbour nearest the target; that
choice reverses the moment it steps, so it oscillates. Worse, it calls
`_mark_progress("moved while blocked")` every round, so `p.last_progress_round`
is always fresh, `_report_stall` never fires and `_write_off` never retires it.

Three attempted fixes, all measured on vase both seats and all failing:

    walk the belt when idle              still 0 -- the miner is never idle,
                                         it explores forever
    walk the belt every 50 rounds        still 0 -- `_explore` is reached but
                                         the miner is stuck before it matters
    explore only reachable stride points still 0 in seat a, and seat b went
                                         from a win to a loss

So the diagnosis is solid and the cure is not. The next attempt should probably
start at `_move_while_stuck`: a move that oscillates should not count as
progress, and a Builder that has not changed tile in N rounds should be treated
as stuck no matter what it reports. That interacts with `_write_off`, which
retires the Builder for good because the Core only replaces one when *every*
Builder is dead -- so it likely needs the reinforcement path too, and that
measured -30pp when tried on its own.

### Three washes, and the point at which to stop

Traced a `heimdall` loss on a generated map (`random3/r10`, 30x10, RUSH): vigil
put three turrets on our Core on rounds 12, 14 and 15, and our first guard
Gunner went up on round 22. Ten rounds late. The obvious culprit is price --
`_keep_ammunition` converts the bank down to `EMERGENCY_RESERVE` (10 Ti) every
round the ammunition floor is unmet, and a scaled Gunner is ~20, so the guard
can be priced out of the turret that ammunition exists to feed.

Never converting below one Gunner's price:

    40 generated maps   99/160 -> 102/160   +3
    21 official maps   134/168 -> 131/168   -3

Net zero. So the price is not what made the guard late in that game, and the
fix does not ship despite being the tidier code. Same shape for turning
`FERRY_ON_INFERENCE` off on generated maps (+3 there, -9 on the pool) and for
the guard leash (+1, +2).

Three independent ideas all landing at plus-or-minus three games in 160 is the
signal that this chassis is out of reach of a 168-game gate. The next real step
needs either the cluster's 4,000-game samples or a different mechanism, not
another knob.

### Two latent bugs worth knowing about

- `warden_walk` (and everything built from it) calls
  `_keeps_route_open(p, choice[1], ...)` in `_build_basic_gunner`. `choice[1]`
  stopped being the spot when the `AVOID_ENEMY_RAYS` key was prepended to the
  tuple, so it has been passing an int; `spot not in baseline` is then always
  true and the self-blocking guard has been dead. Restoring it is worth 0
  games (117/168 against 118), so it is a correctness fix, not a lever.
- `_build_siege_sentinel` picks a seat without checking it can pay for the
  turret. On aurora the attacker walked fifteen rounds to a Sentinel seat with
  30 Ti against a 76 Ti scaled cost and then stood on it for the rest of the
  game. Adding the affordability check is also ~0 games (145/168 against 145).

### Where the map-adaptive hypothesis actually lands

Honest answer: **the geometry does not predict the levers, and only one map in
the pool has terrain worth adapting to.** Manhattan detour ratio (true walking
distance from Core ring to Core ring, over |dx|+|dy|) across the 21 maps:

    sweden 3.08 | runestone 1.17 | pinch 1.08 | bridge 1.05 | everything else <= 1.0

So the Launcher relay is not buying a way *around* walls — there are almost no
walls to go around. It buys raw tiles on open ground, which is a tempo/scale
trade, not a map question. Per-map win rates for relay 0/1/2 and ring 0/1/2/3
were also read off the cluster's 194-game-per-map cells: no ordering with walk
distance, area, corner-ness or detour survives.

Two things *are* map effects and both are worth the next session:

1. The farthest-symmetry guess for the enemy Core is **wrong on exactly the two
   maps where the Cores share an edge** — sweden (guess cheb 23, truth 13) and
   vase (14 vs 9) — and sweden is warden's worst map in the whole pool at
   0.737. Ranking surviving candidates by travel distance instead of Chebyshev
   does not fix it at round 0 (both candidates are far when the map is unknown)
   but should fix it a few rounds in. Untested.
2. The guard makes games *long* (median 47 → 57 turns) and pushes the remaining
   losses into round-1000 titanium tiebreaks, which cluster on closed maps —
   4 of our 12 losses to vigil are 1000-turn economy decisions on bridge,
   skerry and sweden. That is the map effect that is left: on a map where
   neither Core can be reached, the game is an economy game. The FORTIFY role
   split was measured at 2-12 *before* a working defence existed and deserves
   re-testing now.

### Why the generated maps are harder than the pool, in exactly one respect

The farthest-symmetry guess is right **28/42 (0.67)** on the official pool and
**60/184 (0.33)** on the generated maps. That is not the bot behaving worse; it
is one number showing up twice. Of the three candidates, the farthest is always
the 180-degree rotation wherever they differ, so "farthest-first accuracy" *is*
"the share of maps built by rotation":

    official pool     rotation 14, x-mirror 3, y-mirror 4     -> 0.67
    generated (94)    rotation 32, x-mirror 31, y-mirror 31   -> 0.33

The pool's designers prefer rotation two to one. `generate_maps.py` draws the
three symmetries uniformly on purpose, so it is a faithful test of everything
except this convention, where it is deliberately pessimistic. The final is
presumably drawn by the same people as the pool, so the convention probably
holds there and the generated-map scores understate the bot by whatever the
guess is worth.

Which is: on the pool, ferrying at the guess is +9 games in 168. On 40
generated maps it is **-3 in 160** — ferry-off scores 102/160 against
ferry-on's 99/160. Both are inside noise on their own, but they point opposite
ways and the mechanism explains why. `FERRY_ON_INFERENCE` stays **on**, betting
on the convention; if that bet looks wrong later, turning it off costs 9 games
on the pool and buys 3 on uniform terrain.

A margin rule was tried and is impossible: for a Core at (cx, cy) the rotation
candidate's Chebyshev distance always ties the larger of the two reflections,
so the margin is 0 on 184 of 188 map-sides and carries no signal.

What does *not* depend on the guess is the outcome. Splitting all 376 generated
games by whether the guess was right: 0.664 when right, 0.617 when wrong. The
symmetry test strikes a wrong candidate quickly enough that the bot recovers.

### `tools/generate_maps.py`

Draws random symmetric maps to `maps/random/` from the rules the pool obeys
(8×8–30×30, two Cores, connected), in equal parts 180° rotation, x-mirror and
y-mirror. Round-trips `aurora` byte-identically, so the encoder is right. Use
it for anything that claims to be about unknown terrain — a test set of only
rotations would score a bot that always guesses rotation as though it were
correct.

## 2026-08-04 — turret fights

When pushing turrets into a fight (field Gunners, lane pressure, anything
offensive rather than the Core seal), score candidate sites with two priorities
ahead of raw coverage:

1. **Stay out of enemy rays**, ideally also far from their current rotation.

## 2026-08-03 — reading the ladder's replays

`.replay26` is protobuf. The full schema is embedded as a JSON blob in the
bundled visualiser (`fcode/data/visualiser/assets/main-DFlSC1w7.js`, search
`nested:{battlecode:`) — extract it and the whole match decodes: every
placement, move, throw, shot, HP delta and ammo conversion.

**Downloaded replays carry no stdout.** The `BotOutput` message survives, but
only its `id` and `execTimeUs` fields: across 20 ladder replays, 0 stdout
events and 0 `tled` flags. Locally (`fcode run`) stdout *is* recorded, which is
how our own `PLAN_FAILED` lines come back out of a replay — the fastest way
there is to debug an opening. Do not expect to read anyone else's prints; the
schema has the field but the server strips it.

What downloaded replays *do* give away is `execTimeUs` per unit per round —
the opponent's real CPU time. Pantheon samples at 304-1,749 us, so the top of
the ladder is nowhere near the 10 ms limit.

Pull replays with `fcode match replay <match-id>`; `fcode match list --team
<id>` finds top-vs-top games (widen with `COLUMNS=250` to get full IDs).

### What the top three actually do

- **Pantheon (#1)** plays one fixed opening on every map: Builder round 0,
  Launcher round 1 on the enemy-facing side at radius 2, one throw per round on
  rounds 2-5, Launcher razed round 6. Two throws carry raiders at the enemy
  Core, two carry economy Builders to distant ore. Throws cross walls, so it
  ignores chokepoints — on `pinch` it throws over a two-tile wall band and kills
  the Core on round 24.
- **Erebus (#2)**, one rating point behind, builds **no Launcher at all** and
  takes two of five off CtrlAltDefeat on the round-1000 titanium tiebreak.
  There is more than one viable top strategy.
- **The rush is answered by surviving it.** All three games CtrlAltDefeat won
  against Pantheon ran long (1000, 867, 470). The pattern across 20 decoded
  games: whoever has turrets around their own Core before the enemy's forward
  turrets land, lives; a tie goes to the attacker.

### We are already ahead on delivery

Ragnarok's attacker chains Launcher hops and puts a Gunner beside the enemy
Core on **round 12** of aurora, against Pantheon's 32 and CtrlAltDefeat's 43.
The obvious "copy the leader" move is a downgrade — measured 18/42 against
23/42. Do not spend more time porting Pantheon's opening; the gap to close is
elsewhere.

### The atlas silently disables the relay off-pool

`_opening_ferry` began `if p.atlas is None: return False`. The atlas only
recognises the published pool, so on a generated map, the held-out set, or the
final, the entire relay switched itself off and the attacker walked. This is
most of why `ragnarok_fair` sits five places below `ragnarok`. Fixed in
`valkyrie` by gating on *knowing* the Core (atlas or actually seen).

Ferrying at the symmetry **guess** was also tried and is worse — 17/42 against
21/42 atlas-free. The old gate was right to refuse a guess and wrong only about
what counts as knowing.

### The cluster is the instrument, and it is cheap

`git push` to x/luc schedules the bot on DTU HPC automatically: 3,900-odd
matches against the whole rated field, collected in about three minutes, plus a
compliance stage. Do not grind the 252-game panel locally -- it put this laptop
at load 24 for a worse answer. Read results with
`git show origin/x/tournament:tournament/runs/<run>/matches.csv`.

Cluster numbers for valkyrie@d181312 over the **complete** 3,906-match run
against 94 opponents: **89.7% overall**. Per-matchup, on full 42-game samples:

    ragnarok_fair@79582fc     17/42  40%   <- the only real losing matchup
    ragnarok@79582fc          21/42  50%
    vigil@e22eda8             23/42  55%
    vigil@e267eeb             24/42  57%
    vigil@18b749d             24/42  57%

**Do not read a partial run.** At 10 games the same matchup showed 2/10 against
vigil@e267eeb and I concluded the ragnarok line loses to the vigil line. It
does not -- the full sample is 57%, and it agrees exactly with the local gate.
A run is partial until `matches.csv` reaches the planned count; check it.

The genuinely interesting result is the last line of that table inverted:
**ragnarok_fair beats valkyrie 25/42 while ragnarok itself only draws 21/42.**
The atlas-free twin of the same bot is the stronger opponent, which says the
offline map oracle is not paying for itself against this bot and may be
actively costing it. Worth chasing, and it matters doubly if the final is
played on a map the atlas has never seen.

The opening headcount is settled, in ragnarok's favour. A fourth Builder is a
regression in *both* directions -- valkyrie_atk2 (second attacker) 83.6% and
valkyrie_econ2 (second miner) 83.4%, against valkyrie's 89.7%, and 12/42 and
1/4 respectively head-to-head. The +20% scale per Builder really does outweigh
either a second battery or a second belt. Pantheon opens with four anyway; that
is a difference in what the rest of the bot does, not a lever to copy.

vigil's own tip was a regression and is now fixed (c71a543fc): commit 64e40cba4
("Place the ring on the real threat boundary, and turn it on") flipped
RING_COVER_SHELL to True and left the paragraph arguing against it standing.
With it on, vigil loses **15/42** to vigil@e267eeb, its own previous commit;
with it off the same comparison is 21/42 and every one of the 21 maps splits
1-1 -- an exact mirror, so the shell was the whole regression.

### The one lever that has moved anything: stop buying Launchers

Every Launcher is +10% on every price the team pays for the rest of the game,
and the bill lands on the only two things that win: Gunners and Harvesters.
Both changes that moved the map metric are this same observation applied twice.

Found by chasing an anomaly rather than by tuning: `ragnarok_fair` beats
`valkyrie` 25/42 where `ragnarok` itself only draws 21/42. The fair twin is the
same bot with the atlas removed, and `_opening_ferry` is gated on the atlas, so
it *cannot ferry* -- it is forced to walk, and that handicap is why it wins. On
aurora the chaining bot ends with 6 Launchers, 1 Harvester and 4 Gunners; the
walking bot ends with 3, 2 and 7.

Both caps are non-monotonic, so neither "chain" nor "walk" was the right answer
(worst-target map rate, 21 maps x both seats vs the two Nash-core agents):

    MAX_RELAY_LAUNCHERS   0:14%   1:29%   2:24%   uncapped:5%
    RING_MAX_SITES        1:24%   2:33%   3:29%   8 (all):29%

5% -> 33% overall. The first relay hop clears the Builder out of its own half
while the map is empty and is worth 20 Ti; hops after it are not. Two ring
sites are the throw pad plus one approach; below that the screen covers
nothing, above it the sites are bought with the turrets that kill Cores.

Things checked at the same time and left alone, all on the same metric against
33% for the shipped build: the siege Sentinel earns its +20% (off is 29%),
FORTIFY's field Gunners earn theirs (off is 24%), and the attack-Gunner cap
does not bind above seven (5 -> 7 is +1 game; 7 and 10 are identical). So the
scale-discipline vein is mined out at the two Launcher caps -- every other
spender in the bot is already paying for itself.

The caps also bought CPU headroom, which was not the point but matters: fewer
Launchers means fewer launcher hazards to path around, and the worst Builder
turn drops from 4,198 us to 2,994 us. Worth having, because the cluster's
compliance stage measured valkyrie at 5,944 us where this laptop said 3,993 --
cluster hardware is materially slower and the 10 ms limit is enforced there.

### The goal is both mElo and *sole* Nash support, and they pull apart

Specialising is easy; dominating is not. warden_walk earned Nash support at 0.5
by capping Launchers, and paid for it with the lowest mElo of the top seven.
Broken down per opponent the blanket cap is two effects added:

    gains                    losses
    ragnarok_fair  +14pp     vigil@60d5afa      -24pp
    valkyrie       +12pp     vanguard_oracle    -19pp
    ragnarok       +10pp     casemate_oracle    -12pp

It beats Launcher-heavy bots, which overspend on scale once we stop, and loses
to bots that wall us out, where the chain is the only way through. It sells
40/42 matchups to buy 21/42 ones -- exactly the trade that earns Nash support
and costs mElo.

**The trade is a frontier, and the "am I stuck" signal does not break it.**
aegis caps only the routine ferry and leaves the stuck-recovery Launcher
uncapped, on the theory that being walled out is distinguishable from routine
chaining. Measured, it just slides along the same line:

    build                       vs prospect   vs ragnarok_fair   total
    warden                         30              18             48
    aegis (conditional cap)        27              20             47
    aegis, stuck threshold 5       26              23             49
    warden_walk (blanket cap)      26              24             50
    steward (replace losses)       31              21             52

### What is off the frontier: unspent titanium

steward is the first change that improves both columns instead of trading them,
and it is not a strategy change at all. `core.py` gates respawning on
`has_live_builder`, and that heartbeat proves only that *one* Builder is alive,
so a team that loses two of three never replaces them:

    T15  Ti=154  builders=3
    T45  Ti=139  builders=1
    T90  Ti=298  builders=1     dies T103 holding 358 titanium

Beaten, on sweden, by an opponent that mined nothing at all. The bank is the
trigger, because a live headcount is not available -- comms writes are
invisible to other units until the next round, so a bitmask never accumulates,
while a working team spends income as it arrives and therefore never banks
much. After the fix the same game runs to 138 and mines 360 against 150.

That failure mode is now closed: across 38 gate losses, **zero** end holding
100 titanium or more. The remaining losses are genuine.

The lesson to carry: look for resources the bot fails to convert before looking
for tactics it fails to execute. Trades between matchups are usually a
frontier; waste is usually free.

### The Launcher caps made a new Nash pillar, not a better bot

Full ledger, auto-f11bf027e3d4: 98 bots, 285,183 matches.

    rank  bot                    melo    win rate   nash prob
    1     vigil@18b749d          457.0   0.8731     0
    2     vigil@e22eda8          456.0   0.8832     0.500001
    3     vigil@e267eeb          452.0   0.8824     0
    4     warden@3318ffd         451.5   0.8851     0
    5     ragnarok@79582fc       451.1   0.8839     0
    6     valkyrie@d181312       450.0   0.8834     0
    7     warden_walk@3318ffd    435.1   0.8698     0.499999   (rank_delta +6)
    13    ragnarok_fair@79582fc  347.0   0.7899     0          (rank_delta -5)

**The Nash support is now {vigil@e22eda8, warden_walk} at 50/50.** The capped
build displaced ragnarok *and* ragnarok_fair from the core outright.

Read that carefully, because it is not the win it first looks like.
warden_walk has the *lowest* mElo and the *lowest* win rate of the six bots
above it. It is not a better bot on average; it is a strategically distinct one
-- it beats things the others cannot, which is exactly what earns Nash support
and exactly what mElo discounts. Capping Launchers did not collapse the cycle,
it added a pillar to it.

For "beat everything on 70% of maps" the bot to build on is **warden**, which
carries the highest raw win rate in the entire field (0.8851) at rank 4 --
though warden, ragnarok and valkyrie sit within 0.2 points of each other over
4,074 games apiece, which is inside the noise. The honest summary is that the
ragnarok line has four bots statistically tied at the top and one specialist
that is half of the equilibrium.

### Cluster verdicts, full samples only

    valkyrie@d181312   89.7%  (3906)
    warden             89.0%  (4029)   repair + write-off ported from vigil
    vigil, shell off   88.7%  (4032)   was losing 15/42 to its own last commit

warden draws valkyrie 21/42 -- an exact split. **The vigil port is neutral.**
The capability gap is real (ragnarok genuinely cannot mend a belt and never
calls self_destruct) but it does not pay in this field, where the median game
is short and belts are rarely shot. At 2,407 of 4,029 matches it read 90.5% and
looked like a win; that was the partial-run trap for the second time in one
session, and the only reason it was not reported as a result is that the
hedge was made explicit.

The vigil fix is confirmed the other way: 21/42 against vigil@e267eeb on the
cluster, exactly the mirror the 84-game local gate predicted. So the local gate
is a trustworthy *screen* when an effect is real -- it just cannot see small
ones, which is how it called the 25-game pad-first regression noise.

### Measured failures worth not repeating

- **Pad-first spawn order** (Launcher-ring Builder first, Pantheon-style):
  -25 games in 252. Pushes the miner from spawn index 0 to 2; first Harvester
  round 7 -> 9, delivered titanium 696 -> 470.
- **Reserving the first Harvester's cost against ammo conversion**: 24/42 ->
  15/42 against vigil@e267eeb. The bug it fixes is real -- on bridge ragnarok
  loses both seats and mines *zero* titanium, because combat opens on round 4,
  the COMBAT_AMMO_FLOOR override converts down to EMERGENCY_RESERVE every round
  after, and a scale factor of 2.4x puts a 47 Ti Harvester out of reach forever
  -- but turrets that cannot fire cost more than the Harvester is worth. The
  bridge economy failure is still unsolved and still worth solving another way.
- **`except Exception` around ammo conversion hides fatal typos.** A missing
  import made `_keep_ammunition` raise NameError every round; the bot kept
  playing with 0 ammunition and scored 1/42 without ever crashing. Always grep
  a fresh replay for `PLAN_FAILED .* reason=NameError` before trusting a run.

### Still open

- The `vigil` lineage overruns 10 ms in real matches (~0.3 TLE unit-rounds per
  game at `--tle 10`); the `ragnarok` lineage measures 0 on the same scan. Any
  further work belongs on ragnarok's chassis, and vigil's timing is worth a
  look before that lineage is used again.
- Nothing in `valkyrie` beat ragnarok by more than noise on 42 games. 42 games
  cannot resolve these differences — the 3,780-game tournament is the only
  instrument here that can.
- Untested idea from the Pantheon replays worth its own experiment: they throw
  **economy** Builders to ore that is fifteen rounds' walk away. We only ever
  ferry attackers.
