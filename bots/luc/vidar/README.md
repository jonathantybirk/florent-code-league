# Vidar

A 2.3.4 bot. tyr's chassis (odin's machinery, no map atlas, no wall), rebuilt
around the fact that the Aug 4 balance patch changed which turret is efficient
and, through that, which win condition a game actually has.

Everything below was measured on fcode 2.3.4 against eight opponents over the
21 official maps in both seats — 336 games per cell. Nothing measured before
the patch is assumed to still hold.

## The one table this bot is built on

The whole lineage buys Gunners, and the reason is a number written into
`_build_siege_sentinel`'s docstring and repeated through constants.py: a Gunner
"pays 2.78x less per point of damage". That was exact under 2.3.3 — 10 damage
for 2 ammunition against 18 for 10 is 5.00 against 1.80, and 5.00/1.80 = 2.78.

Re-derived from the engine's own `GameConstants` under 2.3.4, every row but one
inverts:

| | Gunner | Sentinel | |
|---|---|---|---|
| build cost | 20 Ti | 30 Ti | Gunner, by 10 Ti |
| **cost scale** | **+20%** | **+20%** | **tied** |
| HP | 25 | 40 | Sentinel, 1.6x |
| damage / round | 3.5 | 6.0 | Sentinel, 1.71x |
| damage / ammunition | 1.75 | 1.80 | Sentinel |
| attack radius² | 13 | 32 | Sentinel, 2.46x range |
| blocked by terrain | yes | never | Sentinel |
| can rotate | 10 Ti | no | Gunner |

The load-bearing row is cost scale. Both turrets levy the same permanent +20%
on every price the team will ever pay, and that tax — not titanium — is what
caps how many turrets a game can hold. Once the count is fixed by the tax,
paying 10 Ti more per seat for 1.71x the damage, 1.6x the HP, 2.46x the range
and a line nothing blocks is free. 2.3.3's +10% Gunner against a +20% Sentinel
is exactly what made Gunner spam correct.

`67ed3ab11` applied this to the siege and stopped. Four other places still
hardcoded `build_gunner`, including the reactive home guard — the single
biggest mechanic in the record. The turret kind is now a parameter of the seat
search, the ray projection and the build call.

## What the panel said about that

1,680 games, four variants, one role group each:

| | odin | tyr | vigil | ragnarok | prospect | pantheon | steward | valkyrie | mean | worst |
|---|---|---|---|---|---|---|---|---|---|---|
| all roles Sentinel | 0.548 | 0.524 | 0.738 | 0.643 | 0.548 | 0.679 | 0.595 | 0.643 | 0.615 | 0.524 |
| guard + defend only | 0.476 | 0.476 | 0.786 | 0.857 | 0.452 | 0.690 | 0.560 | 0.857 | 0.644 | 0.452 |
| siege battery only | 0.381 | 0.440 | 0.702 | 0.714 | 0.440 | 0.762 | 0.500 | 0.714 | 0.582 | 0.440 |
| field + denial only | 0.405 | 0.417 | 0.690 | 0.667 | 0.571 | 0.595 | 0.548 | 0.667 | 0.570 | 0.417 |

Guard and defend carry it. Field and denial are the worst group of the four and
are **off** — a field turret is bought by an economy Builder on whatever it
happens to meet, and paying 30 Ti instead of 20 for a seat that exists to deny
one passing scout is the one place the extra reach buys nothing.

## The second, larger consequence

A Builder Bot restores 4 HP for a flat 1 Ti, unaffected by cost scale. A
Sentinel deals 6 damage a round for 3.33 Ti of ammunition. Defence is therefore
about 2.2x more titanium-efficient than offence: one mender cancels two thirds
of a Sentinel and two menders outlast a two-Sentinel battery outright.

So Cores mostly do not die, the median game reaches round 1000, and the
tiebreak order is titanium collected → live Harvesters → titanium stored. Two
things followed:

**Our Sentinels could not see the win condition.** `get_nearby_entities`
returns units; conveyors, harvesters and barriers are *buildings*. Every
Sentinel this lineage ever built simply held its fire whenever no unit stood on
its line. They now shoot the supply line — Harvester before splitter before
conveyor, and never turrets, because destroying a turret hands back its +20% of
cost scale and we would be paying 30–40 Ti of ammunition to make everything
they build cheaper. The same file gives up on a Core whose HP has stopped
falling under fire, which is a mender out-healing the battery rather than a
slow kill.

**Nothing funded the win condition.** Past the opening the Core only ever
replaced the dead. It now spawns Builders for income after round 200. This does
not overturn the headcount-of-three finding, which was about the *opening* and
still holds: an opening Builder levies +20% on the Launchers and Harvesters the
opening has not bought yet, where the same +20% at round 250 falls almost
entirely on conveyors at 3 Ti — 0.6 Ti a tile, against 2.5 Ti a round for the
rest of the match from every Harvester it connects.

## The third consequence: counting Builder-rounds

The economy sweep's harvester arm reproduced the baseline row *exactly*,
opponent by opponent — raising `NETWORK_CAP_LATE` from 8 to 12 and pulling the
second trunk forward changed nothing at all. That says the bot runs out of
Builder-*rounds*, not out of permission. So the rounds were counted rather than
theorised, with a probe tallying every Builder's turn by phase and by whether
it moved, acted or did neither. On quarry at round 750, out of ~750 each:

```
id=3    wait_lock:idle=555
id=152  wait_lock:idle=509
id=790  scout:move=549     built nothing all game
id=808  scout:move=528     built nothing all game
id=829  scout:move=543     built nothing all game
```

Four defects, none of them visible in any win rate:

**The construction lock could not name more than three Builders.** `owner` is
`builder_index + 1` in a two-bit field, so index 3 wrote owner 4 → `0b00` →
"nobody owns this", never matched itself, and rewrote the slot with a fresh
expiry every round. Units act in ascending entity id, so that late Builder's
write always landed after the early miner's claim and erased it — and the early
miner, the one actually laying belt, waited for a lock it could never be
granted. Four bits now.

**Two claim slots cannot employ seven miners.** `CLAIM_SLOTS` held one
`pack_pos` each, sized for a three-Builder team with one miner. A claim is 10
bits and a slot is 32, so three fit and the two slots now cover six.

**Unemployment was treated as a personal fact.** The harass fallback keys on the
Builder's *own* `network_load`, zero for one spawned late, so a miner with
nothing to mine never reached it.

**A no-op step was treated as a completed turn**, in three places. `_step`
returns False without acting when the Builder already stands at its goal, so a
harasser walked to the nearest enemy deposit, arrived, and stood on that tile
for the rest of the game. All three now fall through.

Plus a bound rather than a fix: a Builder lays without the lock after 40 rounds
of waiting, because serialising long routes is an optimisation and starving on
it is not.

## Spending is the cost: what the parked attacker generalised to

Once the parked Builder had shown that *not spending* beats spending, the same
question was put to every discretionary item this bot buys. Cost scale is a
permanent multiplier on every later price, and under 2.3.4 the median game is
decided by titanium collected at round 1000, so each of these is a mortgage on
the win condition. Three of the four had been tuned before the patch.

| item | scale | was | now | effect |
|---|---|---|---|---|
| relay Launchers | +10% each | 2 | **0** | +1.2pp mean, floor unchanged |
| ring Launcher | +10% | 1 | 1 | removing it: -1.5pp mean, +4.75pp floor — a trade, kept |
| denial turret | +20% | 1 | **0** | **+2.7pp mean and +4.8pp floor** |
| siege battery | +20% each | 2 | 2 | battery 1 is +1.2pp mean, -2.4pp floor — a trade, kept |
| guard turrets | +20% each | 2 | 2 | 1 is -4.0pp, 3 is -6.4pp — confirmed from both sides |
| Harvester cap | +5% each | 6 | **4** | **+1.2pp mean and +2.4pp floor** |

The denial turret is the clearest case. It shipped three commits before the
patch and its own note is its epitaph: *"a ray is a wall that costs 10 Ti and
never has to fire."* 2.3.4 made that wall 20 Ti and +20% permanent scale — the
same tax as a Sentinel — for a turret bought explicitly never to shoot anyone.

`NETWORK_CAP_EARLY` is the second: 6 came from mjolnir and was measured with
the twelve-tile wall on, which is the one mechanic from that bot that was ruled
out. Four is also where the arithmetic says a trunk saturates — a conveyor
carries one stack a round and a Harvester makes one every four.

Note how many of these are *interactions*. Dropping the ring was worth +4.75pp
of floor on the relay-2 base and nothing on the relay-0 base. Every arm here is
therefore cut on the shipping base rather than the base it was invented on.

## Where it stands

Same panel, same 336 games a cell:

| | odin | tyr | vigil | ragnarok | prospect | pantheon | steward | valkyrie | mean | worst |
|---|---|---|---|---|---|---|---|---|---|---|
| odin (baseline) | — | 0.548 | 0.714 | 0.738 | 0.548 | 0.738 | 0.405 | 0.690 | 0.626 | 0.405 |
| + turret work only | 0.571 | 0.524 | 0.714 | 0.786 | 0.524 | 0.738 | 0.595 | 0.762 | 0.652 | 0.524 |
| + late expansion | 0.667 | 0.571 | 0.786 | 0.786 | 0.548 | 0.714 | 0.571 | 0.762 | 0.676 | 0.548 |
| + 7 Builders | 0.714 | 0.619 | 0.786 | 0.786 | 0.548 | 0.714 | 0.595 | 0.762 | 0.690 | 0.548 |
| **+ the four defects** | **0.738** | **0.714** | 0.786 | 0.786 | 0.571 | 0.690 | 0.571 | 0.762 | **0.702** | **0.571** |

Then the scale-tax sweeps above took it to **0.750 / 0.643**, against odin's
0.626 / 0.405 — +12.4pp of mean and +23.8pp of worst matchup.

Against odin as the baseline the four-defect row is +7.6pp on the mean and
+16.6pp on the worst matchup. Headcount re-measured on the fixed base: 5 → 0.676, 7 → 0.702,
9 → 0.693, so seven is shipped. On the *pre-fix* base 7 and 11 produced
identical rows, which is what a cap that never binds looks like.

The two remaining weak matchups are prospect and steward, both at 0.571.

## And off the pool, which is the arm that decides whether any of it is real

82 generated maps, both seats, 164 games a pair — 1,312 games a row:

| | odin | tyr | vigil | ragnarok | prospect | pantheon | steward | valkyrie | mean | worst |
|---|---|---|---|---|---|---|---|---|---|---|
| **vidar** | 0.659 | 0.698 | 0.402 | 0.555 | 0.573 | 0.677 | 0.530 | 0.540 | **0.579** | 0.402 |
| vidar, expansion off | 0.558 | 0.619 | 0.384 | 0.537 | 0.555 | 0.677 | 0.518 | 0.518 | 0.546 | 0.384 |
| odin | — | 0.509 | 0.439 | 0.424 | 0.476 | 0.591 | 0.445 | 0.460 | 0.478 | 0.424 |

Three things, and the first is the reverse of what this project usually finds.

**The gain is larger off the pool than on it**: +10.1pp over odin on generated
against +7.6pp on the 21 published maps. mjolnir's gains were pool-only and the
atlas was worth 12pp on the pool and exactly zero off it; this is not that
shape. And the mechanism generalises, not merely the package — late expansion
is +3.3pp on generated against +3.0pp on the pool, which is as close to a
pre-registered replication as this bot has.

**The pool flatters everything.** 0.702 there, 0.579 here, for the same bot.
Any number quoted from the published pool alone is an overstatement of what
happens on terrain nobody has seen, which is presumably what the final runs on.

**The worst matchup changes identity.** vigil is 0.786 on the pool and 0.402
off it, and odin swings the same way against it (0.714 → 0.439). That is a
property of vigil rather than of this bot, and it is now the binding constraint
on the worst-case goal.

Compliance: p75 807 µs, max 4,487 µs, zero timeouts and zero exceptions over
3,066 samples on 21 maps — inside the 10 ms limit with room, and a lower
maximum than odin's.

## The parked attacker: a visible defect whose repair loses 10 points

The one finding here that reverses the project's usual direction, and the
reason this bot ships with a Builder that visibly stands still.

Traced on `random-20260731-008-mirror-x` against vigil: the attacking Builder
walks to (10,8) by turn 11 and never moves again until the Core dies on turn
44 -- 33 of the game's 44 rounds -- with `path_failures` stuck at 0, which is
why `WRITE_OFF_STUCK_BUILDERS` never noticed. The cause is
`_build_siege_sentinel` returning True without acting from two exits, and
because it is the top branch of `_rush`, returning True means the Gunner search
and the harasser below it never run.

Fixing it costs 9.9pp of mean and 14.2pp of the worst matchup. Five repairs
were measured against it, 336 games each, and none reaches the version with the
bug:

| configuration | mean | worst |
|---|---|---|
| **parked (shipped)** | **0.696-0.702** | **0.548-0.571** |
| save 150 + Gunner guard + no attack Gunners | 0.677 | 0.429 |
| save 60 / save 150 | 0.670 | 0.548 |
| save 150 + no attack Gunners | 0.662 | 0.524 |
| save 25 + Gunner guard | 0.656 | 0.512 |
| save 25 | 0.646 | 0.524 |
| save 150 + Gunner guard | 0.641 | 0.476 |
| all three repairs | 0.603 | 0.429 |

The comparison is clean -- every opponent directory is byte-identical across
the compared commits, and the control reproduces 0.696 against the 0.702 it was
carried from.

Why standing still wins: **a Builder that never builds never raises the cost
scale.** Scale is a permanent multiplier on every price the team pays for the
rest of the match, the median game is decided on titanium collected at round
1000, and the parked Builder also sits inside vision of the enemy base holding
their Core sighted in the store for free. The save-length sweep is the
supporting evidence -- longer waits improve monotonically and saturate at
0.670, and only never-spending reaches 0.702.

It is not the same as having no attacker: `vidar_econwar`, which reassigns that
body to mining, scores 0.528 / 0.250. The body has to exist and has to not
spend.

## The guard turret: a result that changes sign with the chassis

Lucas's argument for Gunners on defence is mechanically correct -- `rotate` is
Gunner-only, a Sentinel's facing is frozen at build time, and a home guard
answers waves from different bearings across a thousand rounds. Measured on
three bases, one flag flipped:

| base | Gunner guard |
|---|---|
| all three attacker repairs | **+3.4pp** |
| save 150 | -2.9pp |
| **parked (shipped)** | **-4.7pp** |

So the Sentinel guard stays. The lesson is the ledger's: a mechanic is only
measured for the chassis that will carry it, and a main effect computed across
cells is not a substitute for the one-flag flip on the shipping build.

## Two measured rejections, kept because the reasoning was good

**`AMMO_TARGET` 120 → 200.** Ammunition is denominated in shots and the patch
repriced the shot, so 120 fell from sixty Gunner shots to twelve Sentinel ones.
Raising it costs 43% of the economy: on quarry against odin, target 200 mines
11,410 titanium and target 120 mines 20,180 in the same deterministic game.
`_keep_ammunition` converts everything above the construction reserve, so a
high target does not buy a stockpile out of surplus — it pins every Builder's
working bank at the reserve for the whole game. The Sentinel's appetite is a
*rate*, and the answer to a rate is income, not a buffer.

**Starving the enemy supply line** measured neutral: 0.676 against 0.679 with
it off, a three-game difference in 336. It stays on because a Sentinel holding
its fire with a legal target on the line is a defect whether or not the panel
can see it, but it is not a gain and should not be cited as one.

## What this bot does not do

No map atlas, inherited from tyr: no `atlas` module and no import of one, so it
plays a generated map, the held-out set and the final the way it plays the
published pool. No wall — `BULWARK_ENABLED` is off and stays off.
