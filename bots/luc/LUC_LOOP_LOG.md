# Loop log — bot iteration toward rank 1

Running log for the `/loop` session started 2026-08-08 05:22 CEST. One section
per iteration: hypothesis, build, local numbers, internal numbers, online
numbers, next step.

Starting position: **rank 15 of 109, rating 1748**, active submission
`v34 = steward_hardened_reinforced@f1f2bda`, last 10 series 4W 6L.

> Note: `bots/luc/luc_LOG.md` and `bots/luc/freyr/` belong to another agent
> working this checkout concurrently. Nothing here touches either.

---

## Iteration 1 — a stalled siege is not free

### Where the ladder actually stands

`live.json` per-opponent, pooled over every `steward_hardened_reinforced` build
(games for / total):

| opponent | games | our game win rate |
|---|---|---|
| **Besvikomat** | 380 | **24%** |
| not adgato | 410 | 32% |
| The Flotte Experience | 350 | 38% |
| O(1) | 340 | 44% |
| Pivot | 505 | 44% |
| Pantheon | 470 | 44% |

Besvikomat is rated within a few points of us and takes three quarters of the
games. The last four series on 2026-08-08 were 0–5, 0–5, 0–5, 0–5; a day
earlier the same matchup was 3–2 and 2–3, so this is recent.

### False start, recorded so it is not retried

`steward@e55aab5` showed the highest expected Elo of any build in the feed —
1876 [1806, 1941] over 261 matches, against the flagship's 1794 — and the farm
was not promoting it. It looked like we were running the wrong flagship.

It was a coverage artifact. `steward` had never faced "not adgato" or "The
Flotte Experience" and had farmed Klarum at 91% over 160 games; its
`matchup_dispersion` was 1.0 purely because there was nothing to correct
against, and `elo_settled` already said 1802. Three rounds queued via
`test_next` on `x/ladderfarm` to settle it. After the first round: estimate
**1876 → 1827**, dispersion **1.0 → 4.58**, settled 1802 → 1778. Inflation
confirmed. Not the flagship.

Worth keeping as a method note: the farm nominates challengers from the top
three of the *internal* v3 leaderboard, which is entirely this lineage, so a
build with a strong online record but a weak internal rank is invisible to UCB
and can only be re-measured by hand.

### Hypothesis

Decoding the 0–5 sweep (`match 3eab9d19`) says one thing five times: **our
damage is reversible and theirs is not.**

| map | rounds | their Core, lowest seen | their Core at end | our Harvesters | theirs |
|---|---|---|---|---|---|
| nordkap | 624 | 226 (r52), 421 (r208), 247 (r364) | **500** | 4 | 10 |
| eider | 445 | 245 (r37) | **500** | 9 | 20 |
| antler | 320 | — | **500** | 5 | 7 |
| lighthouse | 191 | **27 (r75)** | **500** | 1 | 4 |
| jackpot | 1000 | — | 500 | 2 | 17 |

On lighthouse we had their Core at 27 of 500 and it healed to full while ours
bled out. On nordkap we broke it down three separate times and it was repaired
every time. We are out-mined roughly 2:1 in every long game.

`constants.py` already knew half of this: one siege Sentinel deals 6 HP/round
into two menders restoring 8, and raising `SIEGE_SENTINEL_TARGET` to 2/3/4
measured *worse* (0.581 vs 0.590) — "the ceiling is delivery, not permission."
So a bigger battery is already a closed question. The remaining move is to stop.

The compounding part, which appears to be new: `_stand_down_if_pointless`
retires idle turrets specifically to hand back their cost scale, but a Gunner
besieging a mended Core **is never idle** — it fires every round at a target
that heals back to full. So it never retires and never refunds the +10%. We put
up 19 Gunners on nordkap. They did not just fail to kill the Core, they
multiplied the price of every Harvester for the rest of the game. That is a
mechanism connecting the stalled siege directly to the 4-vs-10 economy gap.

### Built: `bots/luc/steward_relent`

Fork of `steward_hardened_reinforced@6b39ebbe3`. Two changes, both no-ops in the
games this build already wins:

1. **Gunner siege-stall detection.** A Gunner that can *see* the Core it is
   firing at counts rounds where the HP does not fall; after
   `GUNNER_SIEGE_STALL_ROUNDS = 20` it stops firing, which lets the existing
   quiet-rounds path rotate it onto something real or retire it and refund the
   scale. Vision-gated, so a turret shooting a remembered Core it cannot see is
   never called stalled on no evidence. This is the Sentinel's
   `SIEGE_STALL_ROUNDS` logic, which the Gunner never had.
2. **A late game.** Past `LONGGAME_ROUND = 300` the Builder ceiling goes from
   `ECON_MAX_TOTAL_BUILDERS = 6` to `LONGGAME_MAX_TOTAL_BUILDERS = 10`. A game
   still running at 300 is one the siege did not finish, and the win condition
   has become the round-1000 titanium tiebreak — which we lose. Raising the cap
   *unconditionally* is the change already measured and rejected; this is gated
   so short Core kills are played exactly as before.

Neither is a re-tune of an existing constant on the steward line — six of those
landed inside the noise floor.

### The same mechanism, second opinion

Decoding an O(1) loss (`match 2c88dd84`, 1–4) shows it is not a Besvikomat
quirk. Per game, Core damage *we* dealt against Core damage *they* dealt:

| game | we dealt | we killed? | they dealt | they killed? |
|---|---|---|---|---|
| 1 | 1533 | no | 503 | **yes, r335** |
| 3 | 1547 | no | 1110 | **yes, r325** |
| 4 | 1176 | no | 508 | **yes, r168** |

We out-damage them two to three times over and lose, because their Core comes
back and ours does not. Two of our three worst matchups are the same disease.

### Local numbers, and a negative result worth the cycle

Duel suite, 21 maps × both seats × 3 opponents (126 matches):

| | vs flagship | vs vidar | vs odin | mean | floor |
|---|---|---|---|---|---|
| `steward_relent` | 0.500 | 0.619 | 0.667 | **0.595** | 0.500 |

0.500 against the flagship is no regression. But the mechanism check said the
build was very nearly a **no-op**:

| long games (≥300 turns) | relent | flagship |
|---|---|---|
| Gunners built | 10.06 | 9.83 |
| Harvesters built | 1.89 | 2.61 |
| Builders spawned | 5.17 | 5.00 |

Two separate reasons, both caught before pushing:

1. **The Gunner refusal did nothing.** `_enemy_on_the_line` runs on the raw
   attack pattern, so a besieging turret sees the enemy Core on its line every
   round forever and resets `quiet_rounds` to 0. Refusing the shot therefore
   bought the worst of both worlds — a turret that had stopped damaging
   anything and still charged its +10% on every later price. Fixed by making a
   Core this Gunner has given up on not count as "on the line", which is what
   lets the existing retirement path fire and hand the scale back.
2. **The Builder cap was never the binding constraint.** Long games spawn ~5
   Builders against a cap of 6, so raising it to 10 changes nothing; the
   binding constraint is `resources >= builder_cost + 60`, and `builder_cost`
   is inflated by exactly the cost scale the un-retired turrets are charging.
   Kept anyway — it should start to bind once (1) refunds that scale.

After the fix the suite came back **byte-identical on all 126 matches**, which
is itself the finding: instrumenting a scratch copy shows the stall probe is
reached often (231 hits on quarry, 173 on sprint) but `siege_stalled` peaks at
**3 and 7**, never the threshold of 20. Against our own lineage the enemy Core
HP keeps falling, so the counter correctly resets — the gate is doing its job,
and the local panel simply cannot produce the condition, because nothing in
this lineage out-heals us. On the Besvikomat sweep their Core rose from 226 to
500 over ~50 rounds, which clears 20 easily.

### `bots/luc/spar_mender` — a fixture for the matchup we lose

So the panel had to grow the opponent it was missing. `spar_mender` is the
flagship with no attacker, two miners, three home turrets that never retire, an
early raised economy ceiling, and the doctrine pinned to FORTIFY. It is not a
ladder entry and is not meant to be strong; it is meant to sit there mending.
It already reproduces the pattern — on jackpot it takes the flagship to round
1000 and wins on the titanium tiebreak, which is exactly how we lost jackpot to
Besvikomat.

It does **not** fully reproduce yet: over the pool the flagship still beats it
0.667 and still kills its Core in ~60% of games, and `steward_relent` also
scores 0.667 against it. The stall still does not trip. Recorded as a partial
asset rather than a working test — making it genuinely un-killable (dedicated
menders, not more miners) is the obvious next step.

### The strategic picture this turned up

Our live win rate is **not monotone in opponent rank**:

| opponent | rank | our game WR | series |
|---|---|---|---|
| Besvikomat | 11 | **0.242** | 10–66 |
| not adgato | 4 | 0.317 | 15–67 |
| The Flotte Experience | 8 | 0.377 | 21–49 |
| O(1) | 13 | 0.438 | 24–44 |
| **Pantheon** | **1** | 0.445 | 38–56 |
| **sporks** | **2** | 0.565 | 51–29 |
| **Erebus** | **5** | 0.568 | 47–29 |

We do better against the top three than against a cluster rated below us. This
is a style counter, not a strength gap, and it is where the rating is: going
from 0.24 to even 0.45 against Besvikomat alone is worth more than anything
available against Pantheon. Two of the five are confirmed to be the same
mend-and-outlast mechanism.

### What shipped

Gunner change only. The economy half was cut after measuring it as a no-op —
the Builder cap of 6 never binds (long games spawn ~5), so raising it to 10
changed nothing. The real constraint is `resources >= builder_cost + 60` with
`builder_cost` inflated by the very cost scale the Gunner change is meant to
free, so it is worth revisiting only *after* this lands.

Final local panel, 21 maps × both seats, 42 games a cell:

| | vs flagship | vs vidar | vs odin | vs spar_mender | mean | floor |
|---|---|---|---|---|---|---|
| `steward_relent` | **0.500** | 0.643 | 0.667 | 0.667 | 0.619 | 0.500 |

- **CPU**: worst turn 2,515 us of 10,000; zero over. Gunner worst 77 us.
- **Determinism**: three identical runs agree to the last unit of titanium.
  Nothing added reads a clock — only HP, vision and round number.
- **Loads**: `fcode run` clean on bridge, quarry, jackpot.

### Note on the internal ladder

`index.json` `run_id` is still `auto-b10e94bd7fe6` from **2026-08-06**, and the
`botrankings-evaluator.timer` on this machine is `inactive` (the evaluator moved
to the PC on 08-07). No new internal run has published in two days, so the
internal ladder may not be a feedback channel this session — the live ladder
is. Not touched: the harness is another agent's.

### Next

Push to `x/luc`, queue on `x/ladderfarm`, read `live.json` after ~2 rounds.
Expect little from 15 matches; the Besvikomat matchup is the thing to watch.
