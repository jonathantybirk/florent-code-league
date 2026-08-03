# pantheon_clone

A reconstruction of **Pantheon** (ladder #1, rating 1980) from public replays,
built 2026-08-03 off **150 ladder games** (124 won) across 17 opponents and 18
map sizes, pulled with `fcode match list --team Pantheon` + `fcode match replay`.

**Status: reference implementation, not a candidate. Do not submit.** It loses
0-1 out of 42 to `ragnarok` and to `vigil`. Why, and why that is still worth
knowing, is at the bottom.

## How the replays were read

`.replay26` is protobuf. The full schema is a JSON blob in the bundled
visualiser (`fcode/data/visualiser/assets/main-DFlSC1w7.js`, search
`nested:{battlecode:`); extracted and parsed it decodes every placement, move,
throw, shot, HP delta and ammunition conversion.

Two things worth recording for next time:

- **Terrain rows are *packed* repeated enums.** Decoding them as one varint per
  field yields empty rows and silently breaks any terrain-aware analysis — the
  first pass at throw targeting scored 38% because of this, and 68% once fixed.
- Downloaded replays carry no stdout, and Pantheon draws no indicator overlays
  (0 `indicatorLine`/`indicatorDot` in 150 games). `execTimeUs` does survive:
  Pantheon samples 304-1,749 us against the 10 ms limit.

## What Pantheon actually does

**The opening is fixed. 150 games out of 150, every map, every opponent:**

| round | action |
|-------|--------|
| 0 | Builder |
| 1 | Builder, **and** the round-0 Builder puts up a Launcher |
| 2 | Builder; Launcher throws passenger 1 |
| 3 | Builder; throws passenger 2 (30/150 also build a Gunner here) |
| 4 | throws passenger 3 |
| 5 | throws passenger 4 |
| 6 | **Launcher self-destructs** |

- **Launcher site**: Chebyshev 2 (83) or 3 (67) from its own Core, always in
  the enemy-facing quadrant. Never radius 1, never 4+.
- **Throws**: exactly four in 122/150 games. Range is `dist_sq <= 26` measured
  **from the Launcher**, not from the passenger — the bot is picked up from an
  adjacent tile first, so total displacement reaches 6. 353 of 581 throws land
  at `dist_sq` 25 or 26, i.e. at maximum range.
- **Targeting**: of the legal landing tiles, minimise the *walking* distance to
  the objective — 72.9% land on a BFS-optimal tile against 38.5% for
  straight-line. Ties break toward the farthest tile from the Launcher, and
  that rule had **103 confirmations and no counterexample**.
- **Roles**: passengers 1-2 raid the enemy Core, passengers 3-4 go to distant
  ore. 81/150 games are exactly `RREE`; `RR` is the prefix of every observed
  pattern. Raiders then build 3-4 Gunners; economy passengers build
  harvester → conveyor → conveyor (101 built exactly that).
- **Ammunition**: 2 converted on round 0, then nothing until Gunners land, then
  a small pool (peak 8) refilled every round — ~139 converted over a game.

### The self-destruct is the clever part

A Launcher carries **+10% build-cost scale** while it lives. In 147 of 151
Launchers the lifetime is exactly five rounds — built r1, gone r6, the round
after the fourth throw. Nothing is adjacent when it goes and the removal lands
inside the Launcher's own turn, so it is `self_destruct()`, not a Builder
razing it. Pantheon rents the throw range for four rounds and hands the 10%
back for the remaining ~995.

### Pantheon does not play a long game

**Median game length: 41 rounds. 134 of 150 finish inside 150 rounds.** Median
titanium collected is 110. The harvester-and-conveyor throws are a hedge for
games that run long, not the engine. The engine is the raid: all Core damage in
the sample is turret fire, 10 per hit, against a 500 HP Core.

## Where this implementation stands

Aggregate profile over the full map pool, both seats:

| | Pantheon | this clone |
|---|---|---|
| opening r0-3 exact | 150/150 | 39/63 |
| throws at max range | 61% | 74% |
| Gunners at Core radius 2-4 | 72% | 83% |
| enemy Core killed | 122/150, median r38 | 12/63, median r114 |

**Do not trust that table.** Matching histograms is a weak test — it cannot
tell a faithful clone from one that merely has the right shape. The real test
is below, and it is much less flattering.

## The reproduction test, and what it found

The engine is deterministic, and Pantheon has played *us*: three ladder matches
(15 games) of our own v5 `tempest_fast` in seat A against Pantheon in seat B, on
maps that all resolve to the local pool. So rerun those games locally with
`pantheon_clone` in seat B against the same `tempest_fast` (extracted from
`origin/x/jon:bots/jon/fair/tempest_fast`) and diff seat B's actions round by
round. `tools/pantheon_analysis/repro.py` does this.

**Result: the clone diverges from the real Pantheon within 0-2 rounds on every
one of the 15 games. 17 of 180 rounds match before the first divergence.**

That is the honest fidelity number. Everything the aggregate table says is still
true and still useless for distinguishing this from Pantheon.

What the test bought, though, is three corrections the aggregate stats had
completely hidden:

1. **The Core's spawn radius is sqrt(8), not one tile.** Pantheon's round-0
   Builder sits at offsets like `(2,0)` and `(2,1)` — it uses the reach, putting
   the pad a tile further forward before anything has moved. The first version
   only ever considered the eight adjacent tiles.
2. **The Launcher goes one step further out than the Builder, along the ray from
   the Core.** The Launcher offsets are the Builder offsets shifted outward,
   count for count: Builder `(2,0)` 32 times → Launcher `(3,0)` 32 times;
   Builder `(1,1)` 62 times → Launcher `(1,2)` 40 and `(2,1)` 22. With this rule
   the round-1 Launcher position matches the real game **exactly on 7 of 7**
   maps that got that far.
3. **Only the round-0 Builder goes deep.** Every later Builder spawns at
   distance 1 from the Core, on a tile the pad can already pick up from.

The test also refuted a hypothesis. Pantheon is accurate at round 1, when the
enemy Core is far outside anyone's vision, which looks like map recognition —
so the clone was given the `ragnarok` atlas as an experiment. Rounds 1-2 tracked
much better (9 → 17 matching rounds), but round 0 got *worse* on five maps.
**Pantheon's round-0 tile is not aimed at the true enemy Core**, so whatever it
knows, it is not doing this lookup. `ATLAS_ENABLED` in `constants.py` toggles
it; it is an oracle, and anything fair derived from this must set it `False`.

## Why it loses anyway

Against `ragnarok` and `vigil`, **the clone's own Core is destroyed at median
round 28, earliest round 15** — in 79 of 84 games. It throws all four Builders
away by round 5 and has nothing at home. Our bots rush and hold; this one
cannot do either.

That is not a copying failure, it is the strategy meeting a bad matchup. It also
independently reproduces what `bots/luc/NOTES.md` already recorded from the
earlier port ("18/42 against 23/42 — do not spend more time porting Pantheon's
opening"), and the note that decided those games: *whoever has turrets around
their own Core before the enemy's forward turrets land, lives.*

Pantheon is 1980 because it wins the ladder-average matchup, where most
opponents do not rush it before round 28 — not because of some edge hidden in
the opening. The opening's *structure* is recovered above and it does not save
this bot against ours; the exact tile choices are not recovered, and the
reproduction test says so plainly.

**What a replay cannot give you** is the rest of the bot: how it retargets under
fire, what it does when the raid fails, how it defends, how it plays the round-
1000 tiebreak. Those never appear as events, only as consequences. 16 of the 150
games ran long and Pantheon won most of them, so that machinery exists — it is
simply not reconstructible from this data.

The reproduction test puts a number on that limit. Even after three measured
corrections, the clone parts company with the real bot inside two rounds. The
opening is recoverable; the bot is not.

## Reproducing any of this

```
tools/pantheon_analysis/decode.py     full-schema .replay26 decoder (schema.json from the visualiser)
tools/pantheon_analysis/analyse.py    per-game behavioural profile of a chosen team
tools/pantheon_analysis/fidelity.py   aggregate profile comparison (weak test)
tools/pantheon_analysis/repro.py      round-by-round diff against real ladder games (strong test)
tools/pantheon_analysis/sweep.py      strength over the map pool, both seats
```

## The one lever worth taking

The Launcher self-destruct is cheap, isolated, and independently testable
against our own bots: pay +10% scale for the four rounds a ferry is in use, then
raze it. `ragnarok`/`vigil` currently retire field Launchers on a quiet-round
timer (`LAUNCHER_QUIET_ROUNDS = 45`), which is far more patient than Pantheon.
That is a single-constant experiment, not a port.
