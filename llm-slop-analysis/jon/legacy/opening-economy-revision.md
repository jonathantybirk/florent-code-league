# Opening economy, revision pass

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

Independent rebuild, 31 July 2026. Revises
[`opening-economy-builder-count.md`](opening-economy-builder-count.md).

This pass was done without reading the prior analysis or its script; the earlier
document was read only after all measurements below were finished. Ground truth
was the spec shipped inside the engine wheel (`fcode/data/docs/spec.md`) plus
direct probes, because the tutorial mirror in `docs/scraped-originals/.../tutorials/` disagrees with
the engine on three points that matter.

The tooling behind every number below lives on the **`x/jon`** branch:
`analysis/econ/` (planner, simulations, sweeps) and `bots/jon/probes/` (engine
probes). Both are gitignored from `main` as research scaffolding, so check out
`x/jon` to reproduce.

---

## 1. What changed vs. the prior analysis

The prior document's conclusion (adaptive 2–3 builders) survives. The reasoning
under it does not, and should not be reused.

### 1.1 The timing model was wrong

It assumed the builder *"builds outward from the Core, alternating build and
movement rounds"* and derived `first delivery = i + 1 + 3L`.

Measured in-engine at L = 3, 6, 10, 13 (`bots/jon/probes/probe_order`, four variants run
head-to-head on identical maps):

```
first delivery = 2L + 6     building and moving in the same round
               = 3L + 5     alternating build and move rounds
```

So the prior formula is 4 rounds optimistic about its *own* model, while that
model is `L − 1` rounds pessimistic about what the engine actually allows. At
L=13 it assumes 40–44 rounds where **32** is achievable — a 20–27% error.

This matters for its conclusion specifically: making serial construction look
~1.5× slower than it is **systematically overvalues parallelism**, which is the
exact quantity the document set out to measure.

A second, surprising result from the same experiment: laying the belt outward
from the core and building the harvester first then laying back are **identical**
in delivery time (both measured 12/18/26/32). The pipeline chase exactly cancels
the extra travel. The build order is not the lever; build-plus-move is.

### 1.2 Ownership was computed with cardinal-only distance

The prior doc classifies ore as own-side using *"shortest cardinal passable path
distance"*. Builders move on all eight directions, so contest distance is
Chebyshev. Recomputed 8-connected, this undercounts own-side ore: crossfire 2 vs
**4**, duel 2 vs **3**. (Its counts for quarry 8, aurora 7, longship 8 do match.)

Both 1.1 and 1.2 trace to the same root cause: trusting `docs/scraped-originals/.../tutorials/`, which
states that a build blocks the round's move, that builders cannot build on their
own tile or diagonally, and which moves on `CARDINALS` only. All false in 2.2.0.
This is now recorded in [`../meta/mechanics-audit.md`](../meta/mechanics-audit.md).

### 1.3 It ranks builder counts by *stored* titanium

The spec's first tiebreaker is **titanium delivered to the core**; stored is
third, behind harvester count. The prior tables rank on stored, and its text
notes that four builders *"mine the most by every reported horizon"* while
losing on stored — i.e. it recommends against the option that wins the actual
tiebreak. Delivered and stored are different objectives and need separate rows.

Everything below is measured in **delivered**.

### 1.4 Trunk capacity is the dominant constraint, not a footnote

The prior doc states the 4-harvester consequence correctly, but files it under
*"Limits and next modeling steps."* Measured, it is the largest single effect in
the opening — bigger than every builder-count decision combined. See §3.

### 1.5 Confirmed unchanged

Passive income (+10 on rounds ≡ 0 mod 4, 2500 Ti per match); a builder spawned
round `i` first acts on `i+1`; builder base cost 30 and **+20 scale points**;
strictly-own-side ore counts for most maps; initially-visible ore counts. Its
duel validation is consistent with my measurements — a length-1 line simply does
not exercise the build-vs-move question, which is why the error survived it.

---

## 2. Measured economics

One harvester delivers **10 Ti per 4 rounds = 2.5 Ti/round**, forever, at every
distance tested (3–15). That is exactly the whole team's passive income.

A deposit at L=6 costs ~24 Ti (harvester) + ~18 Ti (belt) ≈ 42 Ti and returns
~2450 Ti over a match: a **~58× return**. Titanium is never the opening
constraint — 500 Ti buys roughly ten complete deposits. Time and belt capacity
are the constraints.

A builder's real price is not its 30 Ti. It is **+20 scale points forever**, on
one global additive pool shared by all entity types — as much as 4 harvesters or
20 conveyors. A later build-out with 400 Ti of base cost pays an extra 80 Ti per
builder bought earlier.

---

## 3. The thing that matters more than builder count

**Never merge lines into a shared trunk.** A conveyor line carries 1 stack/round
= 10 Ti/round = exactly 4 harvesters. Measured directly: adding a 5th, 6th and
7th harvester to a saturated line added **0.0 Ti/round** each.

The cap is **per line, not per core** — two lines into two different core tiles
measured 22.49 Ti/round against 22.50 predicted. The core has 8 orthogonal feed
tiles, so the ceiling is 8 × 10 = 80 Ti/round.

Same bot, same maps, only the routing rule changed:

| map | disjoint lines | merged trunk |
|---|---:|---:|
| quarry | 27,430 | 4,940 |
| runestone | 23,730 | 2,360 |
| fjord | 19,050 | 7,560 |
| twins | 16,770 | 12,200 |

A 2–5× effect. On quarry the merged version built 13 harvesters and 4 of them
were earning anything.

Correct shape: **one line per ore cluster, ≤4 harvesters per line, each line
entering the core on its own tile.** Free wins: ore orthogonally adjacent to the
core footprint needs **zero conveyors** (measured: 5.0 Ti/round with no belt),
and a line running past a cluster picks up every harvester beside it at no
marginal cost.

---

## 4. Builder count, measured three ways

**(a) Offline planner, perfect knowledge, no execution noise** — extra builders
worth +4 to +6% of total delivered.

**(b) The engine driven by those plans** (`bots/jon/probes/exec_plan`) — one builder reaches
**96.3%** of the planner's optimum. Delivered by round H, summed over 15 maps:

| | H=150 | H=250 | H=400 | H=999 |
|---|---:|---:|---:|---:|
| NB=1 | 28,720 | 65,330 | 128,570 | **383,660** |
| NB=2 | +26.7% | +14.6% | +3.8% | −4.2% |
| NB=3 | +36.0% | +15.7% | +1.5% | −8.8% |
| NB=4 | **+45.4%** | **+22.2%** | **+6.6%** | −4.8% |

**(c) Tick-level fog simulation with a competent generic policy** — agrees on
shape, larger early magnitudes (+33.9 / +47.9 / +53.1% at H=150), and:

| | NB=1 | NB=2 | NB=3 | NB=4 |
|---|---:|---:|---:|---:|
| delivered by r1000 | 393,248 | +2.7% | +1.7% | +2.1% |
| last deposit connected (median round) | 227 | 113 | 82 | 72 |

**Fog is nearly free**: one builder under fog gets 393,248 vs 398,765 with
perfect knowledge — **1.4%**. The core sees radius 6 from round 0 (every map has
1–4 deposits already visible) and a builder reveals terrain while walking to and
from its jobs. Scouting is mostly a by-product of building.

### The crossover

There is a clean crossover at roughly **round 400**. Before it, more builders
deliver more. After it, they are behind — they cost scale and they physically
block each other around the core, and the economy is finished either way (one
builder completes the median map by round 227).

So the answer depends entirely on which horizon decides the game:

- **a 1000-round tiebreaker** → builder count is worth ±3%, i.e. nothing;
- **an early or mid-game fight** → builder #2 is the best purchase in the game.

---

## 5. Can the decision be conditioned on round-0 Core vision?

Tested directly, and the honest answer is mostly **no**.

Per-map best builder count was regressed against exactly what the Core can read
on its first `run()`: map size, and the count and belt-lengths of ore inside
r²≤36. Scoring candidate rules against flat policies (`analysis/econ/policy.py`):

| policy | H=250 | H=400 | H=1000 |
|---|---:|---:|---:|
| always 1 | — | — | — |
| always 2 | +23.3% | +11.6% | +2.7% |
| always 3 | +28.4% | +13.0% | +1.7% |
| always 4 | +30.8% | +14.2% | +2.1% |
| rule on visible-ore count | +22.1% | +10.9% | +2.5% |
| rule on map area | +27.8% | +12.7% | +1.6% |
| rule on area + visible count | +30.5% | +14.6% | +3.0% |
| per-map oracle | +34.0% | +18.0% | +6.5% |

Two results worth stating plainly:

1. **Visible-ore count is not a useful signal — it is actively misleading.** A
   rule keyed on it scores *worse than a flat "always 2"*. This contradicts the
   prior document's central claim that builder count should follow the number of
   visible credible jobs. The reason: seeing little ore does not mean there is
   little work, it means the work is *undiscovered* — which is precisely what an
   extra builder fixes. Hive shows 1 visible deposit and still wants ≥3 builders.
2. **Map area is a mild real signal**, and it is knowable on round 0 from
   `get_map_width() × get_map_height()`. Small maps (sprint 100, duel 144,
   crossfire 256, atoll 324) show 3–9% spread across builder counts; large maps
   (quarry 576, pinch 252, aurora 676, longship 560) show 15–34%.

But the best conditional rule beats a flat "always 3" by only **~2 points**, and
that margin sits inside simulation noise. **Conditioning on round-0 vision is
not worth the complexity for pure economy.**

---

## 6. Concrete recommendation

### Builder count

**Spawn 2 builders, immediately, on rounds 0 and 1. Then stop and re-decide at
around round 60 on evidence, not on round-0 vision.**

Why 2 rather than 1 or 3:

- it captures the large majority of the tempo gain (+26.7% delivered by r150,
  +14.6% by r250) for +20 scale points and ~36 Ti;
- it halves time-to-full-build-out (median round 227 → 113);
- builder #3 adds only +9 points at r150 and **+1 point at r250**, and is where
  engine congestion starts to bite (NB=3 is the *worst* count at H=999, −8.8%);
- it is the least sensitive choice: 2 is never badly wrong on any map, whereas
  1 loses badly on large maps early and 4 loses late everywhere.

The one round-0 conditional actually worth wiring in, because it is cheap and
the signal is real:

```
area = W * H
n = 2                                  # always
if area >= 400 and intending an early/mid-game fight:
    n = 3                              # aurora, hive, longship, quarry,
                                       # runestone, skerry, strait, vault, fjord
if area <= 330:
    n = 2                              # cap: sprint, duel, crossfire, atoll,
                                       # pinch have nothing for a 3rd to do
```

Do **not** condition on how much ore the Core can see. Do not exceed 3 for
economic reasons; past 3 you are paying scale and causing congestion for ~2%.

Builder #3 and beyond should be justified by scouting, harassment or defence —
which this pass deliberately did not measure (everything here is against
`do_nothing_bot`) — not by economy.

### Opening build order

This is worth more than the builder count and is not map-conditional:

1. **Take any ore orthogonally adjacent to the core footprint first.** Zero
   conveyors, delivering by ~round 5. Free.
2. Then nearest-first by `travel + 1 + belt_length`, not by Euclidean distance.
3. **Build the harvester, then lay the belt back** — or lay outward; they are
   equal. What is *not* optional: **build and move in the same round**, and build
   the conveyor on the builder's own tile so a belt advances one tile per round.
   Getting this wrong costs `L − 1` rounds on every line.
4. **Move diagonally.** Travel is Chebyshev, not Manhattan.
5. **One line per cluster, never a shared trunk**, ≤4 harvesters per line, each
   line entering the core on its own tile (8 available).
6. Wrap `run()` in `try/except GameError` — an escaping GameError destroys the
   unit. This was found the hard way.

### What to re-measure once combat is in scope

The 4-per-line cap means a single destroyed belt tile can idle four harvesters
at once, and a shared trunk is also a single point of failure. Both push further
toward disjoint lines than the pure-economy numbers already do. The builder-count
answer may also move, since builders are the only unit that can heal and repair.

---

## 7. Reproduction

```sh
git checkout x/jon        # the scripts below are gitignored from main

python3 analysis/econ/mapstats.py        # per-map ore geometry
python3 analysis/econ/sweep_line.py      # harvester yield vs distance
python3 analysis/econ/run_trunk.py       # line saturation at 4 harvesters
python3 analysis/econ/exp_twoline.py     # cap is per line, not per core
python3 analysis/econ/planner.py         # offline optimum, perfect knowledge
python3 analysis/econ/sweep_plan.py      # engine, plan-driven builder sweep
python3 analysis/econ/engine_tempo.py    # engine delivered-by-round-H curves
python3 analysis/econ/simfog.py          # fog tick simulation
python3 analysis/econ/policy.py          # round-0 conditioning rules
```

Synthetic maps are generated into `analysis/econ/testmaps/`, deliberately not
`maps/` — `fcode run` without a map argument picks the alphabetically first file
there, so a `_line3.map26` would silently hijack every match.
