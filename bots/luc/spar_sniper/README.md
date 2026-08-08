# spar_sniper — a fixture that reproduces the live counter

`mimir@62df0ec` with the siege forced to be Sentinels, early and plural. Not a
ladder entry. It exists because two earlier attempts at a sparring fixture
(`spar_mender`, and an unshipped massed-turret build) failed to reproduce the
matchup that actually beats us, and this one does.

## The thing it imitates

I Stone v22 swept us **0–5 twice** on 2026-08-08. Decoding one sweep
(`match 5d7ea43c`), their composition is nothing like ours:

| map | their Gunners | their Sentinels | Core damage they dealt | our Gunners | our damage |
|---|---|---|---|---|---|
| snowflake | **0** | **1** @r40 | **4,464** | 5 | 602 |
| saga | 3 @r168 | 3 @r25 | **5,616** | 4 | 105 |
| antler | **0** | **1** @r71 | 1,944 | 3 | 560 |
| jackpot | **0** | **1** @r36 | 846 | 7 | 0 |
| hive | **0** | **1** @r38 | 918 | 3 | 1,099 |

**One Sentinel, seated around round 36–40, grinds a Core down for the rest of
the game.** 18 damage every two rounds is 9 a round against the 8 our two
menders restore, so the Core dies on a clock: 9 × 500 rounds ≈ 4,500, which is
what snowflake shows. Our Core ended on 0 in all five.

We cannot answer it. A Sentinel's reach is r²=32, a Gunner's is 13, and a
Builder sees 20 — so the turret killing us is usually not even visible, which
`_note_incoming_fire` already says in as many words.

## What the fixture changes

`SIEGE_SENTINEL_TARGET` 1 → 3, `MIN_AMMO_FOR_SENTINEL` 40 → 10 so it can seat
them early, and `TURRET_QUIET_ROUNDS` raised out of reach so they never retire.

## It works

Against it over 21 maps in both seats, `mimir` takes 0.524 and ends with its
Core on a mean of **191 HP** — visibly ground down rather than killed outright.
That is the live pattern, reproduced locally, which is what two previous
fixtures could not manage.

## What it has already shown

Two answers were built against it and both failed, which is why the fixture is
worth more than either:

1. **"Only a Sentinel answers a Sentinel."** `_counter_sentinels` falls back to
   a Gunner when a Sentinel is unaffordable or unsited, which seats a 25 HP
   turret inside an 18-damage line — dead in two shots, needing six to kill —
   and then marks the Sentinel `countered` so it is never answered again.
   Removing the fallback measured **identical**: 22/42 either way, 0.07
   Sentinels built. The routine never fires at all, because the shooter is
   outside the Builder's vision.
2. **A third mender.** Their 9 a round against our menders' 8 flips if a third
   Builder mends (12 a round), and healing is the one answer whose price does
   not scale. Recalling the attacker on a "Core lost HP over 25 rounds" alarm
   measured **worse** — 0.405 against mimir's 0.524, with the Core *lower* at
   142.5. The trigger fires on ordinary skirmishing, so the attacker is
   recalled constantly and the offence is gutted.

The open problem is **localisation**: `hurt_tiles` already infers unseen
shooters from damage, but only to avoid them, never to answer them. Something
that turns "we are being shot from somewhere" into "seat a Sentinel on that
ray" is the missing piece, and this fixture is how to test it.
