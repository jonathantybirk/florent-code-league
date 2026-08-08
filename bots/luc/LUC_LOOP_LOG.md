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

---

## Iteration 2 — the miner that was conscripted and never released

### Online, so far

- `steward@e55aab5` finished converging: **1876 → 1827 → 1808 → 1789 → 1715**,
  and the farm demoted it. The inflated estimate is fully settled and the
  question is closed. Cost: a few rounds of farm budget, and it corrected a
  number that would otherwise have kept looking like a better flagship.
- `steward_relent@7ed1acc`: first round in, **5 matches, elo 1842**. Above the
  flagship line (~1780) but a long way below the 25-game bar — five-game series
  swing hard and this is one of them. One more round queued.
- Team: rank 13-15 of 109, rating ~1744.

### A claim I made and had to withdraw

I found that the atlas (`atlas.py`) is a published-map oracle keyed on
dimensions plus Core position, covering the **old** pool — atoll, aurora,
bridge … vault — and that **nordkap, eider, antler and lighthouse are not in
it** (only jackpot is). The v3 pool replaced 15 maps on 2026-08-06 and the
atlas was never updated, so on most current ladder maps it misses and the ore
list falls back to "whatever the Core can see at round 0".

That part is true. The conclusion I drew from it was not: I claimed it
explained the economy gap, then measured atlas-hit pool maps and got **2.25
harvesters mean** — no better. The economy is small everywhere, so the atlas is
not the driver. Recorded because the atlas gap is real and worth someone's time
on its own (it also costs us the enemy-Core position), just not this.

### The actual mechanism

Generated maps are the useful instrument here — they are guaranteed atlas
misses *and* they produce long games, which is the ladder condition. Flagship
vs vidar on 8 of them: **0-3 Harvesters**, including **zero across a 321-round
game and zero across a 981-round game**.

`builder.py`'s `_pick` already documents the phenomenon and says the caps are
not the cause: "live Harvesters ran 1.80 at round 50 down to 1.42 at round 500
in games this bot won, and 1.69 down to 0.24 in games it lost … NETWORK_CAP_EARLY
6 was measured inert because permission was never the binding constraint."
Permission allows eight Harvesters. This bot builds two.

The cause is two lines in two different files:

- `core.py`: `repair_alert` latches True at 50 HP lost and clears **only** at
  `hp == max_hp`.
- `builder.py:348`: `if p.builder_index == 0 and alarm:` → mend or defend,
  return. Builder 0 is the *only* economy Builder in every doctrine
  (`_ROLES` is `(1, 1)` for RUSH, FORTIFY and BLITZ alike).

So one scratch that the menders never quite top up — 4 HP a round against a
Core that keeps getting chipped — takes our sole miner off ore **for the rest
of the game**. That is precisely "an economy that never grows and, when losing,
collapses to nothing", and it explains the ladder replays: our last Harvester
on nordkap is round 64 of 624, on eider round 90 of 445, on antler round 92 of
320, while Besvikomat keeps laying them to round 575, 431 and 256.

### Built: `bots/luc/njord`

`steward_relent` plus one change in `core.py`. "Under attack" becomes a Core
that is *losing* HP rather than a Core merely below full: the Core tracks
whether its HP fell this round, and releases the alarm after
`ALARM_RELEASE_ROUNDS = 40` calm rounds — but only while `hp > CRITICAL_HP`, so
a Core that is genuinely one push from dying keeps its mender.

The eager trigger is untouched, because triggering on damage rather than on a
death projection is the mechanic holding this build's floor (+11.0pp mean,
+16.6pp worst matchup). Only the way *out* changes.

### Numbers — and the hypothesis is refuted

Economy-over-time, each build vs vidar over 12 generated maps × both seats (24
games each):

| build | wins | mean rounds | Harvesters built | conveyors | alive @150 / @300 / @500 |
|---|---|---|---|---|---|
| flagship | 5 | 374 | 1.33 | 9.3 | 1.00 / **0.88** / 1.14 |
| `steward_relent` | 5 | 372 | 1.33 | 9.4 | 1.00 / **1.11** / 1.14 |
| `njord` | 6 | 372 | 1.33 | 9.4 | 1.00 / **1.11** / 1.14 |

`njord` is identical to `relent` on every economy metric. Instrumenting the
release confirms why: over three long games it fired **zero times**. The state
I predicted does not arise —

- on r04 the alarm raised at round 40 and cleared by the *original* rule at
  round 94, because the menders did restore the Core to full;
- on r05 the Core was chipped continuously from round 13, oscillating around
  300, so `calm_rounds` never reached 40 and `hp > CRITICAL_HP` was usually
  false. The miner was conscripted because the Core genuinely was under attack.

So the latch is real in the code and does not bind in play. **`njord` deleted
rather than pushed** — the same call as the economy-cap change in iteration 1,
and for the same reason: an unmeasurable no-op costs a ladder cycle and muddies
attribution.

One thing did come out of it: at round 300 `relent` holds **1.11 Harvesters to
the flagship's 0.88**. Small, and 24 games is not much, but it is in exactly the
direction the cost-scale argument predicts — retiring stalled turrets makes
Harvesters affordable again. That is a second, independent hint that the
iteration-1 change does something.

### Fixture revision

`spar_mender` now mends with *every* home Builder rather than only the ring
Builder (one mender at 4 HP a round could never hold a Core), leash 10 → 14, and
its attacker restored — with `(2, 0)` and no attacker it was simply overrun
before mending mattered. It now beats the flagship on aurora and jackpot but
still dies to a rush on quarry, vault, twins and hive. Still a partial asset.

### Next

`steward_relent`'s second online round is the live experiment; nothing else
should be pushed until it reports. Then: the economy is small because *known
ore* is small — `p.ores` only grows from tiles a Builder physically walks past,
and the economy Builder parks on its opening deposits. That is the constraint
the evidence keeps pointing at, and it is untouched.

---

## Iteration 3 — one miner is a single point of failure

### `steward_relent` online: inconclusive

Both rounds in: **10 matches, elo 1740 [1607, 1847]**. The 1842 after round one
was noise, as expected of a five-game series. 10 games against a 25-game bar and
a ±120 interval settles nothing in either direction. Note also that the whole
flagship line drifted up over the same window (`f1f2bda` 1784 → 1827), so
comparing across timestamps is confounded.

It cannot be retested automatically: the farm's UCB nominates only from the top
three of the internal v3 leaderboard, which is this lineage, and config
`test_next` de-duplicates on `name@commit` via `state["test_next_done"]` — so
re-queueing the same sha is a no-op and it would need a fresh commit.

### What actually binds the economy

Instrumented the economy Builder's state every 25 rounds on two long generated
games. This is the answer I had been guessing at for two iterations:

- **r05** (747 rounds, lost): `phase=goto`, `alarm=1`, from round 25 to round
  725. `seen` never leaves 82 — the Builder does not move for **seven hundred
  rounds**. `load=0`, zero Harvesters, no network at all. It is conscripted as a
  mender by `builder.py:348` (`p.builder_index == 0 and alarm`) and the Core is
  under fire all game, so it never comes back. njord's release was right about
  the mechanism and correctly declined to fire — the Core genuinely was under
  attack.
- **r04** (1000 rounds, won on titanium): `phase=scout`, `load=2` against
  `cap=8`, one or two known unclaimed deposits, from round 225 to round 900.
  Spare capacity, a free deposit, **675 idle rounds**.

Same root cause both times: **one economy Builder is a single point of
failure.** Pressure on the Core, or one Builder getting stuck, takes the whole
economy to zero for the rest of the game. That is why permission was never the
binding constraint.

### Built: `bots/luc/gefjon`

`steward_relent` with `_ROLES (1,1) → (2,1)` and `LAUNCHER_BUILDER_INDEX 2 → 3`.

The second constant is the load-bearing one. Indices below `economy_builders`
are miners, `ring_slot = index - LAUNCHER_BUILDER_INDEX` picks the ring, and
anything else that is not the ring is the attacker. Raising `economy_builders`
*alone* would have given `0=miner, 1=miner, 2=ring` and **no attacker** — the
exact `(2, 0)` reallocation `doctrine.py` already measured losing 2–12. At 3 it
gives `0=miner, 1=miner, 2=attacker, 3=ring`: a miner added, not taken. And
because the conscription reads `builder_index == 0`, the second miner keeps
mining while the first mends — the r05 failure, fixed directly.

### The two panels disagree

| panel | flagship | `steward_relent` | `gefjon` |
|---|---|---|---|
| generated maps, wins /24 | 5 | 5 | **10** |
| generated, Harvesters built | 1.33 | 1.33 | **1.75** |
| generated, Harvesters @150 | 1.00 | 1.00 | **1.71** |
| official pool, vs flagship | — | 0.500 | 0.452 |
| official pool, vs relent | — | — | 0.429 |

Twice the wins on generated maps; slightly behind on the official pool. On 42
games, 18/42 is about 0.9 sd below even, so the pool result is "no significant
difference" rather than a clear regression — but it is not an improvement
either. The generated maps are the closer analogue of the live condition (atlas
misses, long games), which is an argument for the live ladder settling it, and
also exactly the kind of reasoning that can be motivated. Recorded as a
disagreement rather than resolved by assertion.

### The check that nearly did not happen

First timing run reported **0 turns over the limit** — because `tail` had cut
aurora off the table. The full table:

| build | aurora worst | turns over 10 ms |
|---|---|---|
| `steward_hardened_reinforced` | 2,846 us | 0 |
| `steward_relent` | 3,657 us | 0 |
| `gefjon` (as built) | **11,237 us** | **9** |

A second miner tripled worst-case Builder CPU and put it over the platform's
10 ms kill threshold, which would have scored those turns zero however good the
strategy was.

The cost is `_pick`: it runs a `_route` **and** a `_distance` — two searches —
per candidate deposit, every round, per miner, and a second miner in longer
games multiplies that. Bounding it by work rather than by a clock
(`PICK_CANDIDATE_LIMIT`, nearest-first so the dropped tail is deposits a nearer
candidate would have beaten) puts it back:

| limit | aurora worst |
|---|---|
| unbounded | 11,237 us |
| 6 | 8,233 us |
| 4 | **2,426 us** |
| 2 | 2,853 us |

At 4 the worst Builder turn is **2,426 us with p99 1,482** — better than either
parent, since the bound helps regardless of miner count. (The values are not
monotonic in the limit because changing it changes the game; single runs on
different trajectories, not a clean curve.)

Re-measured with the bound in place: **identical** — 10 wins, 1.75 Harvesters.
On generated maps only about four deposits are ever known (`ores=4` in the
traces), so the limit never binds there; it bites only on ore-rich pool maps,
which is exactly where the spike was. The CPU fix is free.

Deterministic: three identical runs agree to the last unit of titanium.

### Pushed and queued

`gefjon@<this commit>` for 3 rounds — 15 matches, enough to matter alongside
relent's 10. Queued behind whatever else is in flight rather than replacing it;
two other agents are testing `freyr` and `vali` on the same budget.

### Next

Read `live.json` for gefjon. If the generated-map result transfers, the second
miner is worth more than either of the first two iterations' changes; if the
pool result transfers instead, it is a wash and the disagreement between panels
is the thing to understand.

---

## Iteration 4 — where the economy ceiling actually is

### Online

Team **rank 12–13 of 109, rating 1772** (session start: 15 at 1748).

| build | matches | elo | interval |
|---|---|---|---|
| `gefjon@f66a427` | 5 | **1850** | [1731, 2002] |
| `freyr@c2c0d3d` (other agent) | 10 | 1758 | [1669, 1849] |
| `steward_relent@7ed1acc` | 10 | 1749 | [1631, 1869] |
| `vali@d123262` (other agent) | 10 | 1622 | — |
| flagship `f1f2bda` | 330 | 1841 | [1804, 1875] |

gefjon leads the challengers after one round, but this is exactly the number
that fooled me last iteration — relent read 1842 at five games and 1740 at ten.
Two rounds still queued. Not a result yet.

### Two miners is the operating point, not three

`gefjon_m3` (three miners, `LAUNCHER_BUILDER_INDEX` 4): **9 wins of 24** against
gefjon's 10 — indistinguishable — with longer games (410 rounds vs 297) and
worse CPU (4,341 us vs 2,426). Harvesters built identical at 1.75, though more
survive late (1.56 @300 vs 1.33).

So the gain is in the step from **one to two**, and it saturates there. Deleted
rather than pushed; the bracket is the useful part.

### The real ceiling: `_route`, not ore knowledge and not permission

Jackpot is the clean case, and it refutes two of my own earlier candidates. It
is an atlas map, so every deposit is known; we took zero Core damage that game,
so there is no alarm; `load=2` against `cap=8`, so permission is spare — and we
held **exactly 2 Harvesters for all 1000 rounds** while Besvikomat went to 9.

Instrumenting `_pick` on a long jackpot game says why, and it is the same line
every time:

```
PICK r=200 idx=1 ores=14 claimed=4 load=1 cap=8 avail=10
   REJECT ore=(0,13) route=None travel=6
   REJECT ore=(1,4)  route=None travel=3
   REJECT ore=(0,14) route=None travel=7
   REJECT ore=(10,15) route=None travel=7
```

**Every candidate fails on `route=None`, while `travel` succeeds.** The Builder
can walk to these deposits; it cannot find a conveyor route to them. Fourteen
known deposits, ten available, and the belt planner rejects all of them.

I suspected the vision rule at `_route`'s line 909 (`if nxt not in p.seen`) —
the atlas supplies ore positions without ever having observed the ground
between, which would be a neat explanation. **It is wrong**: re-running the
search with the vision rule disabled still finds no route, on 12 of 12
candidates (`unseen_only=False`). The blockage is the `blocked` set itself —
`p.walls | p.foot | (p.ores - {ore}) | p.solids | rejected sites | launcher
hazards | non-joinable conveyors`.

The suspicious term is `(p.ores - {ore})`: **every other deposit is an obstacle
to routing**, so deposits in a cluster can enclose one another and become
permanently unbeltable. On jackpot that appears to be most of the map.

Whether that term is a real rule or a self-imposed one is **unresolved**. An
in-match probe of `can_build_conveyor` on ore tiles returned False on all four
directions, but only for tiles that already had a harvester (`empty=False`), so
it proves nothing; a probe restricted to genuinely empty ore never fired in 249
rounds, because our miners are never adjacent to a free deposit. The engine is a
compiled `.so` and does not expose the rule in strings. Settling it needs a
purpose-built probe bot that walks to a free deposit and tries — and note that
even if legal, a conveyor on ore would consume the deposit, so blocking it may
be correct design after all.

That is the honest state: the economy ceiling is precisely localised to
`_route`, and the one term that would explain it is not yet proven wrong.

### Next

gefjon's remaining rounds. Then either the `_route` question above, or the
cluster-level observation from the sweep — our Harvesters **peak early and
collapse** (eider 7→2, antler 1→0) while theirs **scale late** (jackpot 2→9
after round 300) — which is two different problems and gefjon only addresses
the first.

---

## Iteration 5 — the online test cannot measure what we are testing

### gefjon at 18 games

**1772 [1700, 1840]**, down from 1850 at five games — the same collapse
`steward_relent` showed (1842 → 1699). Flagship `f1f2bda` reads 1844. On the
estimate, gefjon loses.

### …except that comparison is an artifact

Pooling `matchups` per opponent and comparing **raw game win rates on the same
opponents** — which needs no model at all:

| | games | win rate |
|---|---|---|
| `gefjon@f66a427` | 90 | **0.49** |
| flagship line, same 16 opponents | 5,595 | **0.51** |

Level. Not 72 Elo worse. Worth noting inside that: gefjon went **5/5 against
Besvikomat**, the matchup this whole session is about and where the flagship
line sits at 0.25 — one series, so it is a hint and nothing more — and **0/5 vs
The Flotte Experience** and 4/15 vs Lorem Ipsum, which is its largest single
deficit.

### Why every challenger reads low

The estimate shrinks toward the team rating (1774), weighted by game count:

| build | games | shrinkage | elo |
|---|---|---|---|
| flagship `f1f2bda` | 333 | **0.114** | 1844 |
| `gefjon` | 18 | **0.373** | 1772 |
| `relent`, `freyr`, `vali`, `njord` | 10 | 0.48–0.63 | 1602–1755 |

Inverting `elo = (1-s)·raw + s·mean`: at 18 games a challenger needs a **raw**
strength near **1885** to tie the incumbent's 1844. A build genuinely 30 Elo
better than the flagship would estimate about 1837 — still below it, so
`maybe_promote` never fires.

**This is structural, and it explains the whole session's online results.** It
is not that relent, gefjon, freyr, vali and njord are all bad; it is that a 1–3
round test cannot distinguish them from the mean, and three agents testing in
parallel at that budget will all read below the incumbent whatever they built.

### What follows

1. **Stop reading the challenger estimate at low game counts.** Compare raw
   same-opponent win rates instead, as above. It is model-free and it disagreed
   with the estimator by 72 Elo here.
2. **Do not spend more farm budget on gefjon.** Resolving a build this close to
   the flagship needs on the order of 100+ games — about 20 rounds — and it is
   level on the honest comparison, so the information is not worth the budget
   while two other agents are queuing.
3. **Chase large structural changes, validated locally**, where 168-game panels
   cost minutes. The farm is a sanity check, not the instrument. This also
   follows from the goal: we are 12th and incremental gains cannot reach rank 1
   anyway.

Recorded in memory as `project-farm-cannot-resolve-small-gains`, since it
changes how anyone should use the farm.

---

## Iteration 6 — our own belt network walls off our own economy

Acting on the conclusion above: chase a large structural change, validated
locally. The `_route` ceiling from iteration 4 was the obvious candidate, and
resolving it took three attempts, two of which were wrong.

### First, an actual rule established

Wrote a minimal probe bot (`main.py`, ~70 lines) that walks a Builder to the
nearest **empty** ore tile and asks the engine directly. Result:

```
PROBE r=3 ore=(5,0) empty=True passable=True
      can={'NORTH': True, 'EAST': True, 'SOUTH': True, 'WEST': True}
PROBE BUILD_SUCCEEDED on ore tile
```

**A conveyor can be built on an empty ore tile.** So `_route` blocking
`(p.ores - {ore})` is a self-imposed restriction, not a game rule. That is worth
knowing on its own — earlier in-bot probes had only ever hit ore tiles that
already held a harvester, which proved nothing.

### …and it was not the cause

Built the fallback anyway (clean route first, through-ore only when that
fails). It changed **nothing** — identical harvesters, conveyors and outcome on
jackpot. Instrumenting it: `clean=None thru_ore=None` on every candidate. The
ore block was never what stopped us.

### What actually stops us

Rebuilt the diagnostic to drop each term of `blocked` one at a time and report
which unblocks the route:

```
RT ore=(5,0)  unblock->{'walls':True, 'rej':True, 'conv':True, 'ALL':True}
              nettiles=2 conv=7 load=1
```

Dropping `ores` alone never helps. Dropping **`conv`** does — and there is the
number that matters: **7 friendly conveyor tiles, of which only 2 count as
joinable.**

`p.network_tiles` is filled in `_done` from `p.current_route_tiles`, so it holds
the belts *this* Builder finished. Each Builder is a separate `Player` instance,
so it never contains a team-mate's work. Every other friendly conveyor therefore
falls into `blocked` and is routed around **as if it were a wall**. Our own
infrastructure encloses our own Core, and every further deposit becomes
unreachable.

That also explains iteration 3's puzzle: a second miner lays belt that walls the
first one in, which is why three miners scored no better than two.

### Built: `bots/luc/sindri`

`gefjon` with one line changed —
`joinable = set(p.conveyors) if p.network_load < 4 else set()`. `p.conveyors` is
friendly-only (`_sense` files enemy belts under `enemy_conveyors`) and the BFS
already refuses a head-on join, so this widens what we may connect to without
letting us join anything of theirs. The refuted ore fallback was **dropped** so
this is a single variable.

It works mechanically: deposits that reported `route=None` now report
`route=12`, and the near one `route=0`.

| | before | after |
|---|---|---|
| jackpot, ore (0,13) | `route=None` | `route=12` |
| jackpot, ore (5,0) | `route=None` | `route=0` |

Whether that converts into wins is a different question, and one jackpot game
went *worse* (183 rounds vs 249), which is one game and means nothing.

### Measured: the fix is real and the bot is worse

Generated maps (24 games each) — identical wins and Harvesters to gefjon, but
**fewer conveyors for the same economy** (7.2 against 8.0), which is exactly
what joining an existing trunk instead of laying a parallel one should look
like:

| build | wins /24 | Harvesters | conveyors |
|---|---|---|---|
| flagship | 5 | 1.33 | 9.3 |
| `gefjon` | 10 | 1.75 | 8.0 |
| `sindri` | 10 | 1.75 | **7.2** |

Official pool, 21 maps × both seats, where the deposits are dense enough for the
enclosure to bite:

| | vs flagship | vs gefjon | vs vidar | vs odin | mean |
|---|---|---|---|---|---|
| `sindri` | 0.381 | **0.405** | 0.524 | 0.786 | 0.524 |
| `gefjon` | 0.452 | — | 0.571 | 0.762 | 0.554 |

**Worse.** And the reason is in the same table: against the flagship `sindri`
averages **4.79 Harvesters** where it runs 1.75 elsewhere. It is claiming the
deposits it unlocked, and still losing.

The explanation is the warning `_pick` already carries: "A conveyor network
carries one stack/round: exactly four Harvesters at their 10-Ti-per-four-round
cadence. Do not create silently idle deposits." `network_load` is counted
**per Builder**, so two Builders feeding one shared trunk oversaturate it —
more Harvesters, no more throughput, and the extra ones are the silently idle
deposits the comment names. Sharing the network without sharing the load
accounting buys deposits that deliver nothing and cost +20% each.

Fixing that properly needs a team-wide network load, and that is exactly what
the store cannot carry: writes are buffered, so a per-round headcount never
accumulates (this is the same wall that capped `ECON_MAX_TOTAL_BUILDERS` by
spawns rather than by live count).

So `p.network_tiles` being per-Builder is a genuine defect **and** an accidental
guard. `sindri` deleted; the diagnosis is the value.

CPU, for the record: worst turn 4,896 us, zero over — safe, though up from
gefjon's 2,426 because the joinable set makes the BFS goal set larger.

### Next

Three structural candidates are now closed with evidence: the alarm latch
(inert), the ore block in `_route` (not the cause, though the rule it assumed is
genuinely wrong), and shared belt networks (real defect, measurably worse
without team-wide load accounting). The economy ceiling is understood and is
harder than one line.

The counter-cluster remains the biggest prize: `gefjon` went 5/5 against
Besvikomat in its one series there, where the flagship line sits at 0.25 over
390 games. That is a hint worth chasing with a fixture that actually reproduces
the matchup — which is where `spar_mender` stalled.
