# pantheon_replica_day3

Pantheon's opening (ladder #1, rating 1980) grafted onto ragnarok, rather than
rebuilt from scratch. Measured off **150 ladder replays** pulled 2026-08-03;
the replay analysis and the from-scratch attempt that preceded this are in
`tools/pantheon_analysis/` and `bots/luc/pantheon_clone/`.

## Why this is a fork and not a rewrite

The first attempt reconstructed Pantheon from the replays alone. It reproduced
the histograms — build order, throw range, gunner radii — and was still a bad
bot: **28.6%** overall and only **81%** against `starter`, because everything
the replays *don't* show (turret siting that preserves friendly firing lanes,
gunners that break blocking Launchers, BFS pathing, the core seal) had to be
reinvented badly. Matching summary statistics is not the same as playing well,
and chasing them further was not going to close the gap.

This bot starts from `ragnarok`, which already has all of that, and changes
only what Pantheon demonstrably does differently.

## Does it beat tempest_fast the way the real bot does?

Yes. This is the matchup with real ladder data behind it: Pantheon played our
own v5 `tempest_fast` three times on 2026-08-03 and took **14 of 15 games**.

| | win rate | median winning round |
|---|---|---|
| real Pantheon vs tempest_fast (15 ladder games) | 93% | ~38 |
| this bot vs tempest_fast (42 games, full pool, both seats) | **90.5%** | **37** |

### Per-map, against the real games

Same maps, same seats, replica in Pantheon's seat B:

| map | real Pantheon | replica | delta |
|-----|---------------|---------|-------|
| twins | WON r21 | WON r21 | **exact** |
| aurora | WON r43 | WON r43 | **exact** |
| longship | WON r27 | WON r27 | **exact** |
| vault | WON r33 | WON r35 | +2 |
| pinch | WON r16 | WON r18 | +2 |
| runestone | WON r26 | WON r29 | +3 |
| skerry | WON r29 | WON r36 | +7 |
| quarry | WON r43 | WON r39 | -4 |
| showdown | WON r42 | WON r34 | -8 |
| jackpot | WON r34 | WON r43 | +9 |
| bridge | WON (r1000 tiebreak) | WON r95 | — |
| duel | **LOST** | WON r26 | diverges, our way |
| sweden | WON r18 | WON r33 | +15 |

Outcome agreement 12/13, median timing delta +2 rounds, three maps matching the
real kill round exactly.

Two things came out of chasing the per-map gaps rather than the aggregate:

**Pantheon builds exactly one Launcher per game** — 151 across 150 replays —
and its raiders walk the rest. Ragnarok chains relay Launchers forward *and*
rings its own Core with three or four. On twins that built extra pads on r4,
r9 and r12, each 20 Ti and a permanent +10% on every later build, and pushed
the first Gunner from round 6 out to round 11: kill at round 44 instead of 21.
Capping to one pad and walking took twins to r24, then to r21 exactly.

**bridge needs the second pad.** A 21x8 corridor with the Core in the corner:
capped to one we lose the Core on round 50. The real Pantheon does not kill on
bridge either -- its win there ran the full 1000 rounds -- so closed maps keep
a second Launcher as the displacement screen (`PANTHEON_RING_SITES_FORTIFY`).

**The pad is placed for what it can deliver, not for where it is.** This was
sweden: Pantheon kills on round 18 and we took 212. Our Core is at (0,13) and
the nearest ring site, (0,11), lies flat against the west edge -- half its
throw disc is off the map, and the best tile it can reach is (2,8). One tile
inward at (1,11) the disc is whole and the same throw reaches (2,6), two tiles
nearer the enemy Core. That is where the real Pantheon puts it.

So ring sites are now ranked by the shortest *walk* from the best tile they can
throw a passenger onto to the enemy Core -- the same objective the throw itself
uses, lifted one level: choosing where to put the pad rather than where to
throw from it. It is general, not a sweden special case, and it costs nothing
anywhere else. **sweden 212 -> 33**, and twins, aurora and longship still match
the real kill round exactly.

Ranking by raw disc *area* was tried first and is a **measured failure**
recorded in the code (sweden 71 -> 68, twins 21 -> 27, aurora 43 -> 50): area
is only a proxy for delivery, and maximising it drags the pad off the line the
raid actually walks.

Getting there took two fixes, both found by asking why it *wasn't* matching:

1. **Two raiders was wrong for this matchup.** At `PANTHEON_RAIDERS = 2` it won
   83% at median round 42 — winning, but visibly slower than the real bot.
   Three raiders gives 90.5% at round 37, matching Pantheon's tempo, and
   recovers `longship` outright (a map plain ragnarok wins and the 2-raider
   version lost). Pantheon's throw *targets* are RREE, but a passenger thrown
   at ore still ends up fighting later, so the modal throw pattern overstates
   how many Builders stay on economy.
2. **Ragnarok's BLITZ doctrine contradicts the replays.** With Cores 6 apart
   (`showdown`) ragnarok drops the pad and every economy Builder and races;
   it loses its Core on round 21, and so did this bot. The real Pantheon does
   not branch on map size at all -- the same opening appears in 150 of 150
   games -- and on `showdown` it builds the pad on round 1, puts a Gunner on
   the enemy Core's doorstep by round 3 **and** Gunners around its own Core on
   rounds 6-9, winning on round 42. Close Cores now take FORTIFY, which keeps
   the pad and switches field Gunners on: `showdown` goes from a round-21 loss
   to a round-34 win.

The second one is the more interesting result: a doctrine branch that was
measured as correct for ragnarok is measurably wrong for a bot playing
Pantheon's opening, because it removes the home turrets the all-in raid
depends on to survive the counter-attack.

## What was changed from ragnarok, and what each change cost

Every row is the full map pool, both seats, against `ragnarok`, `vigil` and
`starter` (126 games).

| step | total | vs starter |
|------|-------|-----------|
| ragnarok fork, unchanged | 68.3% | 100% |
| four Builders spawned r0-r3, pad built by index 0 | 65.1% | 100% |
| pad Builder spawned onto the ring doorstep (pad up on r1) | 60.3% | 100% |
| Launcher self-destructs once its four passengers are away | 58.7% | 97.6% |
| Pantheon role order — the first two thrown raid | 49.2% | 100% |
| three raiders instead of two | 56.3% | 100% |
| close Cores take FORTIFY, not BLITZ | 54.8% | 100% |

Against `tempest_fast` specifically the last two rows go 83.3% -> 88.1% ->
90.5%, which is the number that matters for "does it play like the real bot".

The ladder is the point. **Pantheon's opening costs about 19 points against our
own bots**, in four independently measured steps, and none of it is a
reconstruction failure — the bot does what Pantheon does, and what Pantheon
does is worse against `ragnarok` and `vigil` specifically. That reproduces what
`bots/luc/NOTES.md` already recorded from the earlier port, from a different
direction and with the mechanism visible.

The last row is the expensive one. It is also the one that makes this Pantheon
rather than ragnarok-with-an-early-pad, so it stays; `PANTHEON_RAIDERS` in
`constants.py` is the single constant that reverts it.

## The opening, as measured

150 of 150 replays, every map, every opponent:

| round | action |
|-------|--------|
| 0 | Builder |
| 1 | Builder, **and** the round-0 Builder puts up the Launcher |
| 2 | Builder; throws passenger 1 |
| 3 | Builder; throws passenger 2 |
| 4 | throws passenger 3 |
| 5 | throws passenger 4 |
| 6 | **Launcher self-destructs** |

- Throw range is `dist_sq <= 26` from the *Launcher*, not the passenger, and
  353 of 581 throws land at 25-26 — it throws at maximum range.
- Landing sites minimise *walking* distance to the objective (72.9% BFS-optimal
  against 38.5% for straight-line); ties go to the farthest tile from the
  Launcher, 103 confirmations and no counterexample.
- Roles follow throw order: first two raid, last two go to ore (`RREE`, 81/150;
  `RR` prefixes every pattern observed).

**The self-destruct is the transferable idea.** A live Launcher is +10% on
every future build cost, and scale is a census of what is alive — so razing it
refunds the 10% immediately. 147 of 151 Pantheon Launchers live exactly five
rounds. Ragnarok retires field Launchers on a 45-quiet-round timer and never
retires ring ones. Worth testing on its own there.

## Where it still differs from the real bot

Current state: pad on r1 in most games, throws on r3-r5 against Pantheon's
r2-r5, enemy Core killed in 32 of 63 at median round 66 against Pantheon's
122/150 at round 38.

Against `ragnarok` and `vigil` it is still well behind (23.8% and 40.5%) --
that is the all-in opening meeting the two bots in the repo built specifically
to rush and hold, and it is the same finding NOTES.md already recorded.

Two things are known to be wrong and are the next work:

1. **Throws are a round late.** Pantheon's pad throws the round after it is
   built; here the later Builders spend a round reaching pickup range.
2. **The self-destruct rarely fires** (`survives` in 182 of 190 Launchers)
   because ragnarok builds a *ring* of Launchers and only the pad ever carries
   four passengers. The retirement rule needs to key off the pad specifically.

Also still open, and the thing to build next: Pantheon's turrets that sit well
away from the enemy Core are not badly placed — they are aimed at the enemy
turrets and Launchers standing in the raid's way. Ragnarok already has the
machinery for exactly that (`_build_launcher_breaker_gunner`,
`_block_firing_lane`, `_preserves_friendly_turret_lanes`); it is not yet driven
by Pantheon's siege pattern.

## Corrections to my own earlier analysis

Recorded because both produced wrong constants that were live for a while:

- "92 raiders built exactly four Gunners" was an artefact of truncating each
  Builder's build list to four entries. Counted over whole games a raider
  places median 3, mean 3.2, tail to 53 — there is no cap.
- "Pantheon builds an early Gunner when rushed" was a confound. All 49 early
  Gunners are on maps with Cores ≤12 apart and none on maps >12 apart: on a
  small map the raider simply lands in range on round 3. There is no reactive
  early-defence trigger, which is also why the strategy loses to a real rush.

Also worth knowing, both learned the hard way: **the Core is 2x2**, so tiles at
distance 1 are inside it and not spawnable; and `can_spawn` **raises** on an
off-map position rather than returning False, so one unguarded candidate aborts
the unit's whole turn.
