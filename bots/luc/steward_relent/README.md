# Steward, relenting

`steward_hardened_reinforced` at `6b39ebbe3`, with one idea: **a siege that is
not working is not free.** Two changes, both of which only fire in games this
build is currently losing.

## The evidence

Our worst matchup on the live ladder by a distance. Pooled over every
`steward_hardened_reinforced` build in the CI feed, we take **24% of 380 games
against Besvikomat** — a team rated within a few points of us. On 2026-08-08 the
last four series were 0–5, 0–5, 0–5, 0–5, where a day earlier they had been 3–2
and 2–3.

Decoding that sweep (`match 3eab9d19`, five maps, five losses) says the same
thing five times:

| map | rounds | their Core, lowest seen | their Core at the end | our Harvesters | theirs |
|---|---|---|---|---|---|
| nordkap | 624 | 226 (r52), 421 (r208), 247 (r364) | **500** | 4 | 10 |
| eider | 445 | 245 (r37) | **500** | 9 | 20 |
| antler | 320 | — | **500** | 5 | 7 |
| lighthouse | 191 | **27 (r75)** | **500** | 1 | 4 |
| jackpot | 1000 | — | 500 | 2 | 17 |

We are not losing for lack of damage. On lighthouse we had their Core at **27 of
500** and it healed back to full while ours bled out. On nordkap we knocked it
down three separate times and it was repaired every time. Our damage is
reversible; theirs is not.

`constants.py` already knew half of this — one siege Sentinel deals 6 HP a round
into two menders restoring 8, and raising `SIEGE_SENTINEL_TARGET` to 2, 3 or 4
scored *worse* (0.581 against 0.590) because "the ceiling is delivery, not
permission." So the answer is not a bigger battery. The answer is to stop.

## What changed

**1. The Gunner learns the mender arithmetic.** The Sentinel has had
`SIEGE_STALL_ROUNDS` since it learned to besiege: a Core whose HP has stopped
falling is being held, not killed, so stop spending ammunition on it. The Gunner
never had it, and the omission compounds in a way that is easy to miss.

`_stand_down_if_pointless` retires a turret that has seen nothing for
`TURRET_QUIET_ROUNDS`, and the reason it exists is cost scale: destroying a
Gunner hands its +10% back and makes every later Harvester cheaper. But a Gunner
besieging a mended Core **is never quiet.** It fires every round, at a target
that is full again by morning. So it never retires, and never gives the scale
back. Nineteen of them went up on nordkap. They did not merely fail to kill the
Core — they multiplied the price of every Harvester we tried to buy for the rest
of the game. That is the mechanism that turns a stalled siege into a lost
economy, and it is why the Harvester columns above read 4 against 10.

Now a Gunner that can see the Core it is shooting counts rounds where the HP
does not fall, and after `GUNNER_SIEGE_STALL_ROUNDS = 20` it stops firing. The
rounds then count as quiet, so it rotates onto anything real within reach and,
failing that, retires and hands the scale back. Reading HP needs vision and
firing does not, so a turret shooting a remembered Core it cannot see is left
alone rather than called stalled on no evidence.

**2. A late game — built, measured, and cut.** The obvious companion change was
to lift `ECON_MAX_TOTAL_BUILDERS` from 6 to 10 past round 300, on the reasoning
that a game still running there has become the round-1000 titanium tiebreak,
which we lose. It was built and it did **nothing**: over 21 maps in both seats
the results were byte-identical, because the cap is not what binds. Long games
spawn about five Builders against a ceiling of six; what actually stops the
seventh is `resources >= builder_cost + ECON_EXPAND_RESERVE`, and `builder_cost`
is inflated by exactly the cost scale the un-retired turrets are charging. So
the reserve is the thing to revisit, and only once change 1 has freed that
scale. Shipping it anyway would have been dead code on a single-variable test.

## What this is not

Not a re-tune of a constant on the steward line — six of those landed inside the
noise floor. It is behavioural, it is gated on a condition that is false in
every game this build already wins, and it follows from one observation: this
lineage treats a stalled siege as a siege, and a stalled siege is a tax.

## Local numbers

21 official maps, both seats, 42 games a cell:

| | vs flagship | vs vidar | vs odin | vs spar_mender | mean | floor |
|---|---|---|---|---|---|---|
| `steward_relent` | 0.500 | 0.643 | 0.667 | 0.667 | **0.619** | 0.500 |

0.500 against the flagship is the point: no regression. The local panel cannot
show anything better, because the stall probe never trips against this lineage
— instrumented, `siege_stalled` peaks at 3 and 7 against a threshold of 20,
since our own bots' Cores do go down when we shoot them. On the Besvikomat
sweep their Core climbed 226 → 500 over roughly 50 rounds, which clears 20
easily. The condition this change exists for is only reproducible on the live
ladder.

CPU: worst turn 2,515 us against the 10,000 us limit, zero turns over; the
Gunner's own worst turn is 77 us. Deterministic: three identical runs agree to
the last unit of titanium.

## Status

Under test. Live-ladder results go in `bots/luc/LUC_LOOP_LOG.md`.
