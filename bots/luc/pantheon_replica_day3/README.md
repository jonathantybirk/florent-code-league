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
