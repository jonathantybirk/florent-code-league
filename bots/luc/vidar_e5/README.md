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

## Where it stands

Same panel, same 336 games a cell:

| | odin | tyr | vigil | ragnarok | prospect | pantheon | steward | valkyrie | mean | worst |
|---|---|---|---|---|---|---|---|---|---|---|
| odin (baseline) | — | 0.548 | 0.714 | 0.738 | 0.548 | 0.738 | 0.405 | 0.690 | 0.626 | 0.405 |
| vidar2 (turrets only) | 0.571 | 0.524 | 0.714 | 0.786 | 0.524 | 0.738 | 0.595 | 0.762 | 0.652 | 0.524 |
| **vidar** | 0.667 | 0.571 | 0.786 | 0.786 | 0.548 | 0.714 | 0.571 | 0.762 | **0.676** | **0.548** |
| vidar, expansion off | 0.571 | 0.500 | 0.714 | 0.786 | 0.524 | 0.714 | 0.595 | 0.762 | 0.646 | 0.500 |

Late expansion is worth +3.0pp mean and +4.8pp on the worst matchup. The
constant sweep behind it (chase 2, guard cap 3, battery 3) found every
alternative equal or worse, so the shipped values are the measured ones.

Compliance: p75 807 µs, max 4,487 µs, zero timeouts and zero exceptions over
3,066 samples on 21 maps — inside the 10 ms limit with room, and a lower
maximum than odin's.

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
