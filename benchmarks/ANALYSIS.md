# Are the bots going in circles? A mechanic-level benchmark of every lineage

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

Date: 2026-08-02. Data: `benchmarks/runs/field-20260802` — 1,944 matches, zero
errors, seed 1, TLE off (deterministic). 23 bots pinned across all five
branches: Luc's tempest line (`tempest_reinforcements`, `vigil`, `prospect`),
Jon's current fair line (`casemate`, `vanguard`, `undertow`, `tempest`,
`mistral`, `jonbot`) and ancestors (`vg_v1/v5/v7`, `titanium_v1`, `frontier`,
`riptide`, `turtle`), Elias's `autistimusprime`/`gobbleglitch`, Viktor's
`green`, and `starter`.

**The hypothesis under test:** bots beat each other on strategy while
individual mechanics regress — the winner has superior strategy but its
harvesters are bad, or its builders freeze when they cannot path, on problems
an earlier bot had already solved.

**Verdict: confirmed, in every lineage, and in a stronger form than posed.**
Newer bots do not merely carry weaker versions of solved mechanics — three of
the four current lineages each *deleted* an entire solved mechanic on the way
to a higher win rate.

## Method

Five suites, all replay-decoded to per-round events (`benchmarks/replay.py`
reads harvester build rounds, per-builder movement gaps, and Core HP deltas
straight out of the `.replay26` protobuf):

- **econ** — subject vs an idle probe, 5 maps. Measures pure expansion:
  first-harvester round, harvesters at checkpoints, delivered titanium, and
  time-to-kill an *undefended* Core (routing + siege tempo with zero
  opposition).
- **stress** — subject vs a `denier` probe that barriers the subject's ore,
  shoots its belts, and parks bodies on its spawn ring, but never attacks the
  Core. Any loss here is lost on mechanics alone.
- **breach** — subject attacks two fortress bots (`casemate`, `turtle`).
- **defense** — subject defends against two rushers (`mistral_fast`,
  `prospect_rushonly`).
- **h2h** — the 12 lineage tips, round-robin, 10 maps (5 closed / 5 open),
  both orders: 1,320 games.

## The headline table (h2h, 220 games per bot)

| bot | score | | bot | score |
|---|---|---|---|---|
| tempest_reinforcements | **84%** | | undertow | 48% |
| vigil | 77% | | mistral | 46% |
| prospect | 73% | | jonbot | 37% |
| gobbleglitch | 59% | | casemate | 9% |
| autistimusprime | 58% | | green | 4% |
| vanguard | 54% / tempest_jon 52% | | | |

89% of games end in a Core kill; of the 146 that reach round 1000, 125 are
decided on `titanium_collected` — the tiebreak is economic, and it is the
*delivered-to-Core* number, not stored wealth.

## Evidence, lineage by lineage

### 1. Jon's tempest/mistral line deleted the economy entirely

`mistral` built **0 harvesters in 138 benchmarked games**. `tempest_jon`
built **1**. Every ancestor of these bots had a working economy — `vg_v5`
delivered 5,722 titanium vs the idle probe, `riptide` 5,284, even 2026-07-28's
`starter` managed 2,980. The pure-rush descendants deliver **0**, always.
That is a coherent gamble at 46–52% h2h — they win by kill or not at all —
but it forfeits all 146 tiebreak games by construction and is exactly the
regression the hypothesis predicted: the mechanic wasn't tuned down, it was
removed, and the win rate hid it.

### 2. Jon's *defensive* lineage defends worst of anyone

Against the two rush specialists, the bots built explicitly as
defenders/macro bots go **vanguard 2/10, undertow 1/10, casemate 0/10**,
while the rush bots themselves go 7/10 (`tempest_reinforcements`, `vigil`).
The defensive lineage's defense regressed below the attackers' incidental
defense. Nobody in the field holds a rush reliably: in the entire defense
suite, **zero games ended with the defender surviving to round 1000**.
Elias's lab proved months of this meta wrong — healing restores 4 HP for a
flat, scale-free 1 Ti, so two menders out-heal a Gunner (10 dmg/round) and
cancel a Sentinel (6 dmg/round) titanium-positive — and that mechanic is in
**nobody's** shipped bot.

### 3. Casemate: a new weapon strapped to pre-2.3.3 legs

`casemate` (Jon's newest, 9% h2h) proves the piercing-Sentinel siege works —
it kills fortresses no Gunner can reach. Everything else regressed to
already-solved states:

- **Pathfinding**: its BFS expands 8-connected neighbours and ranks D8 moves
  — the 2.2.0 movement model, half-ported to 2.3.3's cardinal-only rule.
  Against the denier probe its builders stall **868–975 consecutive rounds**
  (worst in the modern field by 40x); vs an *idle* opponent it failed to
  kill the undefended Core on 2 of 5 maps inside 1000 rounds, and needed
  337–424 rounds on the rest. Vigil kills the same idle Core in 21–34
  rounds on every map. Vanguard's launcher-relay line solved robust
  cross-map routing a week earlier.
- **Delivery**: `titanium_collected = 0 in every one of its 40 benchmark
  games` — its walk-home belt trick never lands a stack on the Core, so its
  23 turtled draws all convert to tiebreak losses. The starter bot solved
  belt delivery in July.

### 4. The ancestors solved things the tips have lost

The legacy bots are terrible opponents (they lose h2h badly) but several of
their *mechanics* remain unmatched by any modern bot vs the idle probe:

| mechanic | best ancestor | best current tip |
|---|---|---|
| harvesters by round 100 | vg_v5: **3.8**, undertow 3.6 | prospect 3.0, vigil/tempest_reinf 2.2 |
| delivered by round 1000 | turtle: **5,874**, vg_v5 5,722 | vanguard 1,618, prospect 114 |
| first harvester round | titanium_v1: **2** | casemate 5–6, tempest line 7 |

The tips don't need economy to win a 30-round game — but 10% of top-tier
games go the distance, and there the tips are running on fumes. (The
ancestors, in turn, stall catastrophically: 970+-round builder freezes once
their opening script runs out — the stall problem the tempest line solved.)

### 5. The two lineages solved disjoint halves of the map pool

This is the hypothesis in its purest form. Per-map h2h scores (out of 22
games per bot per map, vs the whole 12-bot field):

| map | core-to-core | tempest_jon (no economy) | tempest_reinf (economy) |
|---|---|---|---|
| showdown | 6 | **21** | 12 |
| sprint | 6 | **21** | 17 |
| duel | 8 | 14 | 18 |
| vase | 9 | 9 | **18** |
| string | 10 | 9 | **20** |
| jackpot | 14 | 7 | **19** |
| quarry | 18 | 6 | **20** |
| bridge | 19 | 6 | **19** |

Jon's economy-free tempest is the *best bot in the entire field* on the two
maps where the Cores are six tiles apart, and among the worst everywhere
else. `mistral` shows the same shape (showdown 19, duel 19 / bridge 4,
quarry 4, jackpot 4). Neither lineage carries both behaviours, and the split
is not subtle — it is ±9 games out of 22.

The mechanism is plain once stated: economy is tempo spent, and on a map
that is decided by round 21 the first delivered stack never arrives. It is
also computable at round 0 by a fair bot, from dimensions and its own Core
alone. Ragnarok adds it as a third doctrine, `BLITZ`.

### 6. Assorted regressions found while reading the code

- `prospect` packs its doctrine into bit 10 of the own-Core store slot, but
  its `gunner.py`/`launcher.py` still `unpack_pos` the raw slot — under
  FORTIFY (the corner maps the doctrine exists for) home-guard turrets
  compute a garbage home position, so the "never stand down at home" and
  "throw enemies away from home" rules silently break.
- `undertow`'s picket knowledge (avoid Launcher pickup rings when seating
  attackers) exists in Luc's line as `_launcher_hazards` but was re-derived
  independently — the two lineages have solved the same problem twice with
  different bugs.
- Elias's ground truths (tiebreak order, scale-is-a-census, sentinel
  piercing, turn order = global spawn id) are in `llm-slop-analysis` and in
  no other branch's code.

## Cross-check: every borrowed mechanic was ablated, not assumed

Each candidate mechanic was played as the shipped bot with exactly that one
change reverted, against a 6-bot panel (`vigil`, `tempest_reinforcements`,
`prospect`, `mistral`, `vanguard`, `gobbleglitch`), 10 maps, both orders —
120 games per variant, 1,080 games total (`benchmarks/ablate.py`).

| variant | score /120 | delta | what it removes |
|---|---|---|---|
| **shipped** | **92.0** | — | — |
| no field Gunners | 84.0 | **−8** | answering enemies with turrets on closed maps |
| no lane blocking | 87.0 | **−5** | rebuild-tanking a Gunner's firing lane |
| always RUSH | 87.0 | **−5** | the corner (FORTIFY) doctrine |
| no siege Sentinel | 90.0 | −2 | the piercing no-lane fallback |
| no Core seal | 91.0 | −1 | the barrier threat-zone perimeter |
| no Launcher retirement | 92.0 | 0 | handing back a spent ferry's +10% |
| no second trunk | 92.0 | 0 | lifting the harvester cap late |
| no ore denial | 92.0 | 0 | barriering enemy-half ore |

Two results are worth stating plainly because they overturn earlier calls in
this repo:

- **Field Gunners are the single biggest win (+8)** — and `vigil` shipped
  them switched *off* (`MAX_FIELD_GUNNERS = 0`) after measuring them at −3.
  Both measurements are right: averaged over the whole pool they lose, and
  conditioned on a closed map where the enemy must come down a lane they
  win big. Averaging over maps hid a real effect, which is the same failure
  mode as the rest of this document.
- **Lane blocking is worth +5**, confirming in real games what Elias's lab
  measured in isolation (a Core took zero damage through 201 rounds of
  Gunner fire for ~1 Ti/round) — a mechanic that had been documented for a
  day and shipped in nothing.

The three zero-delta mechanics changed no game outcome at all on this panel.
They are kept because each is correct behaviour that only fires in a long
game (retirement at 45 quiet rounds, the second trunk at round 120) and 89%
of these games end by round 60 — but they are recorded here as measuring
nothing rather than presented as improvements.

## What follows (and what was built from it)

The field's best bot is a rush bot with good legs (`tempest_reinforcements`,
84%). Its known holes, per the suites: no answer to a sealed/no-lane Core
except walking (breach via Gunner only), thin long-game economy (2.2
harvesters, capped trunk), and 3/10 losses to rushes it could out-heal for
pocket change.

`bots/luc/ragnarok` is the synthesis, and every part of it is on the
ablation table above or the doctrine table before it:

| taken from | mechanic |
|---|---|
| Luc `vigil` / `tempest_reinforcements` | chassis: economy planner, Launcher ferries, breaker Gunners, turret rotation and stand-down |
| Luc `prospect` | the corner (FORTIFY) doctrine — with its store-slot bug fixed |
| Jon `casemate` | the piercing-Sentinel siege, wrapped in barriers, as the no-lane fallback |
| Jon `tempest`/`mistral` | economy-free blitz, but conditioned on Core distance instead of always |
| Elias `gobbleglitch` lab | lane rebuild-tanking, mender defence, cost-scale hygiene, `get_nearby_units` returns buildings |
| Elias `autistimusprime` | farthest-first symmetry guessing (66.7% correct on the pool vs 9.5%) |

`bots/luc/ragnarok_fair` is the same bot with the offline atlas removed. It
is generated by `tools/build_ragnarok_fair.py` rather than maintained, so the
two cannot drift, and the generator fails if any `atlas` import survives.
Neither bot reads a map table at runtime: the doctrine branches on the map
dimensions and its own Core position only.

### Result

All 21 official maps, both seats, against nine opponents — 378 games:

| ragnarok vs | score | | ragnarok vs | score |
|---|---|---|---|---|
| casemate | 42/42 (100%) | | undertow | 38/42 (90%) |
| vanguard | 41/42 (98%) | | jonbot | 37/42 (88%) |
| mistral | 39/42 (93%) | | prospect | 33/42 (79%) |
| gobbleglitch | 38/42 (90%) | | tempest_reinforcements | 28/42 (67%) |
| | | | vigil | 26/42 (62%) |

**322/378 = 85.2% overall, and it beats every bot it was assembled from** —
including the two it is built on top of. Remaining weak maps are `sweden`
(12/18), `hive`, `bridge` and `aurora` (13/18): all large or closed, all
places where the long game and delivered titanium matter most, which is
exactly where the three zero-delta economy mechanics were supposed to help
and did not. That is the honest next thread to pull.

`ragnarok_fair`, the same bot with the atlas deleted, scores **267/378 =
70.6%** on the identical panel: it still beats `casemate` 42-0, `jonbot`,
`gobbleglitch`, `vanguard`, `mistral` and `undertow`, and loses only to the
three atlas-carrying Luc bots (`vigil` 16/42, `tempest_reinforcements`
19/42, `prospect` 21/42). So the atlas is worth roughly 15 points of win
rate here — far more than the "worth exactly nothing" that Elias's ablation
found on his own bot, because ragnarok's opening ferry and Gunner siting
both plan against terrain it would otherwise have to walk into first.

One fair-side improvement came out of measuring that gap. The bot used to
publish an inferred enemy Core only once two of the three symmetry
hypotheses had been *disproved*; it now commits to the farthest surviving
candidate immediately and revises when terrain contradicts it, with a
sighted-bit in the store so a real sighting always outranks a guess. Waiting
optimises being certain, and the game pays for being right early: that one
change is worth **+25 games / 252** to the fair bot.

### The turn limit is a correctness bug, not a performance one

The first build **exceeded the ladder's 10 ms per-unit budget** — 13,480 µs on
`longship`. A unit that overruns is interrupted mid-`run()` and does not act at
all that round, so this is not slowness, it is a Builder that randomly skips
turns on one map.

`benchmarks/timing.py` measures it the way `tournament/compliance.py` does:
wrap the Player, read the engine's own `get_cpu_time_elapsed()`, and recover
the markers from the replay (bot stdout is embedded there and is the only
channel that survives). Cost is extremely map-dependent — the worst map was 9×
the cheapest — so a three-map sample cannot distinguish "fast" from "not yet
measured on the slow map".

The cause was one line in the wrong place: `_keeps_route_open`, which runs two
full map searches, sat *inside* a 196-candidate loop, so siting one Gunner
searched the map up to 392 times. Two changes, both exact rather than
approximate:

- a candidate site that the existing route does not use cannot close that
  route, so only sites *on* the route need the second search;
- rank candidates first and pay for the check until one survives, instead of
  checking all of them and then taking the best.

| | worst turn | p99 | turns over 10 ms |
|---|---|---|---|
| before | 13,480 µs | 7,087 µs | 2 |
| after | **2,995 µs** | 2,273 µs | **0** |

Verified behaviour-preserving rather than assumed: against a frozen opponent,
before and after produce **42/42 byte-identical games**. A `CPU_SOFT_BUDGET_US`
guard now also stops the widest search once a turn has spent 4 ms, so a future
change cannot silently reintroduce this.

*Caveat on the panel numbers above:* `vigil` is under active development and
changed on disk between two of these runs, which moved that column by 3 games.
Every other opponent was byte-identical across 336 games. Scores against a
moving opponent are only meaningful with the date attached — the same lesson
recorded for the earlier tournament snapshot.

Reproduce: `uv run python -m benchmarks.suite --run-dir benchmarks/runs/<name>`
then `uv run python -m benchmarks.report --run-dir <same>`; ablations with
`uv run python -m benchmarks.ablate --run-dir benchmarks/runs/<name>`. Raw
per-match data for the field run is committed as
`benchmarks/data/field-20260802.csv` (run directories themselves are
gitignored — they hold staged copies of bots, which must never appear under
`bots/`, where tournament discovery would register a duplicate name and
abort the whole run).
