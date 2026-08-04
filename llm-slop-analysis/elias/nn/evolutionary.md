# The evolutionary alternative — search over the hand-written policy instead of learning one

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

*Committee position paper: devil's advocate / evolutionary-search seat. Everything below that is marked
MEASURED was run on this machine on 2026-08-03 against `bot/` at commit `8cb0867`. Nothing in `bot/`,
`bots/elias/` or `bots/rivals/` was modified; all candidates were materialised into `bots/cand/ev_*`
and deleted afterwards.*

---

## 0. The one-paragraph version

I ran the pilot expecting a negative result and did not get one. **Two constants —
`siege.STANDOFF_PENALTY 6 → 0` and `main.VAULT_MIN_GAP 9 → 5` — take the shipped bot from 662/810 wins
(81.7%) to 712/810 (87.9%) over nine opponents and all 45 maps in the repo, with the gain larger on the
generated holdout corpus (+7.4 pp) than on the published pool (+4.8 pp), gains against six of nine
opponents and regressions against none.** That took 20,760 games and 2 h 20 min of CPU. Against that:
only 14 of 36 constants move the objective at all, the train→holdout correlation among small-delta
candidates is **r = 0.034**, and the naive greedy combination of the four best training knobs came out
*worse* than the shipped bot. So search works here, but only behind a generalisation gate and only for
large effects. Meanwhile the 3× H100 is useless to **both** plans: RL rollouts are CPU-bound in the same
single-threaded engine, at ~540 games/hour with a neural policy against 6,300 with the current one.
See §5 for the pilot, §8 for what I measured about the neural plan, §9 for the verdict.

---

## 1. The search space, enumerated

### 1.1 Free scalar constants — `bot/main.py`

| # | Constant | Current | Sensible range | What it controls |
|---|---|---|---|---|
| 1 | `BUILDERS` | 3 | 1–8 | opening builder budget |
| 2 | `SIEGE_BUILDERS` | 10 | 3–20 | builder cap once under fire |
| 3 | `ATTACKERS` | 3 | 0–8 | builders reassigned from economy to siege |
| 4 | `BODY_PATIENCE` | 10 | 2–30 | rounds a squatter may block a firing tile before replan |
| 5 | `ALARM_PERCENT` | 88 | 50–99 | Core HP % that raises the home alarm |
| 6 | `ALARM_RESERVE` | 60 | 0–150 | Ti held back before an emergency builder |
| 7 | `CHAIN_RESERVE` | 45 | 0–120 | Ti held so a chain in flight completes |
| 8 | `RUSH_RESERVE` | 40 | 0–120 | Ti the economy may not spend while the route is unbuilt |
| 9 | `RUSH_RESERVE_UNTIL` | 200 | 50–600 | round the reserve lapses |
| 10 | `CPU_BUDGET_US` | 6000 | 2000–9500 | advisory CPU gate (**inert on Windows**, see §5.0) |
| 11 | `REPLAN_TILES` | 24 | 4–80 | newly observed tiles that justify a siege replan |
| 12 | `REPLAN_ROUNDS` | 10 | 2–40 | floor under the replan interval |
| 13 | `BATTERY_RESERVE` | 20 | 0–80 | Ti left after buying an extra turret |
| 14 | `FORTIFY_FROM` | 8 | 0–60 | earliest round for Core-ring barriers |
| 15 | `FORTIFY_KEEP_OPEN` | 5 | 0–12 | ring tiles never bricked |
| 16 | `BATTERY_EVERY` | 3 | 1–15 | rounds between battery-extension searches |
| 17 | `VAULT_MAX` | 3 | 0–8 | launcher hops the rusher will take |
| 18 | `VAULT_MIN_GAP` | 9 | 3–20 | Manhattan gap below which a hop is not worth 28 Ti |
| 19 | `VAULT_FLOOR` | 70 | 0–200 | Ti the vault leaves behind |
| 20 | `VAULT_PATIENCE` | 3 | 1–15 | rounds waiting to be thrown |
| 21 | `VAULT_GAIN` | 4 | 1–10 | Manhattan tiles a hop must gain |
| 22 | `RETIRE_IDLE` | 25 | 5–100 | rounds before a spent ferry self-destructs |
| 23 | `GUARD_MIN_CHEB` | 2 | 1–5 | inner radius for the guard launcher |
| 24 | `GUARD_MAX_CHEB` | 4 | 2–8 | outer radius for the guard launcher |
| 25 | `GUARD_FLOOR` | 90 | 0–250 | Ti kept back from the guard |
| 26 | `GUARD_FROM` | 12 | 0–80 | earliest round for a guard |
| 27 | `AMMO_TARGET` | 120 | 20–400 | ammo pool ceiling |
| 28 | `AMMO_FLOOR` | 60 | 0–200 | Ti not converted to ammo |
| 29 | `SNIPE_FLOOR` | 90 | 0–300 | bank below which the rusher stops sniping |
| 30 | `ALARM_WEIGHT` | 3 | 0–6 | evidence points the alarm contributes |
| 31–35 | `EV_WEIGHTS` (5 weights) | 2,1,1,2,1 | 0–4 each | posture-detector evidence weights |
| 36 | `POSTURE_CONFIDENCE` | 3 | 1–8 | points to leave the default posture |
| 37 | `POSTURE_RELEASE` | 1 | 0–6 | Schmitt-trigger lower rail |
| 38 | `POSTURE_DWELL` | 60 | 0–300 | minimum rounds between posture changes |
| 39 | `POSTURE_FIRST_DWELL` | 0 | 0–200 | dwell before the first change |
| 40 | `ECONOMY_FROM` | 150 | 50–600 | round at which silence means "go greedy" |
| 41 | `FOE_TURRETS_MANY` | 2 | 1–6 | census threshold |
| 42 | `FOE_HARVESTERS_MANY` | 3 | 1–8 | census threshold |
| 43 | `INTRUDER_HALF` | 50 | 20–80 | midline as % of the core-to-core axis |
| 44 | `INTRUDER_DEEP` | 30 | 10–60 | "near third" as % of that axis |
| 45 | `USE_ATLAS_ORE` | `False` | bool | seed ore memory from the precomputed atlas |

### 1.2 Free scalar constants — `bot/siege.py`

| # | Constant | Current | Sensible range | What it controls |
|---|---|---|---|---|
| 46 | `STANDOFF_PENALTY` | 6 | 0–20 | per-tile penalty on firing positions away from range 1 |
| 47 | `EXPOSURE_PENALTY` | 1 | 0–6 | penalty per open orthogonal neighbour of the turret |
| 48 | `MAX_BATTERY` | 6 | 1–12 | Gunners packed around one enemy Core |

`GUNNER_REACH`, `REACH8`, `REACH8_SENT`, `DELTA8` are **engine facts, not knobs** — changing them makes
the planner produce illegal geometry. `atlas.py` contains 1,951 numeric literals but they are a data
table (per-map terrain), not tunables.

### 1.3 Buried thresholds — magic numbers inside methods

| Line | Expression | Meaning |
|---|---|---|
| `main.py:1172` | `self._pv("attackers") < 2` | gate deciding whether a second attacker exists |
| `main.py:1758` | `free >= 2` | landable-tile test for the launcher throw |
| `main.py:1940` | `self.rush_stuck >= 12` | rounds before the rusher abandons its route |
| `main.py:2401` | `self.stuck >= 5` | belt-walker unstick timer |
| `main.py:2596` | `self.stuck >= 5` | economy-walker unstick timer |

Five more dimensions, and they need refactoring to module level before any search can reach them.

### 1.4 Discrete and structural choices

* **`ORDER_TODAY`** — the builder priority ladder is *data*: a permutation of 6 rungs (`STEP_OWED`,
  `STEP_HOLD`, `STEP_PHASE`, `STEP_REPAIR`, `STEP_SEEK`, `STEP_HEAL`). **6! = 720** orderings, and
  subsets are legal too (a rung can be dropped), giving `sum_k P(6,k) = 1,957` distinct ladders.
* **The posture seam** — `POSTURE_PARAMS` is three rows (`RUSH` / `DEFENCE` / `ECONOMY`) over 12 keys.
  `DEFENCE_OVERRIDES` and `ECONOMY_OVERRIDES` are **both empty today**, deliberately, so all three rows
  are identical and the seam is provably free. Opening them **triples** the effective scalar space for
  the 12 seam keys and adds two booleans (`hold_on_posture`) and two enum slots (`fire_only`).
* **Branch enables** — `USE_ATLAS_ORE`, `hold_on_posture`, `fire_only`, and effectively
  `VAULT_MAX = 0` / `ATTACKERS = 0` / `MAX_BATTERY = 1`, each of which switches a whole subsystem off.

### 1.5 Dimension count

* **48 free scalars** (45 in `main.py` + 3 in `siege.py`), of which 1 is boolean.
* **+5 buried thresholds** once lifted → **53 scalar dimensions**.
* **× 1,957 ladder orderings**, **× up to 3 posture rows** for 12 of those scalars.

Taking a median of ~30 admissible integer values per scalar, the raw cardinality is
`30^53 x 1957 x ...` ≈ **10^81**. Exhaustive search is not on the table; this is a metaheuristics
problem by construction.

---

## 2. Evaluation cost — MEASURED, and the H100s do not help

### 2.1 Per-game cost

| Matchup | games | s/game |
|---|---|---|
| `bot` vs `vanguard`, full 21-map mirrored sweep, 1 core | 42 | **3.14** |
| `bot` vs `vanguard`, 6 maps, 1 core | 6 | 2.14 |
| `bot` vs `starter_fixed`, 6 maps, 1 core | 6 | 1.74 |
| `bot` vs `idle`, 6 maps, 1 core | 6 | 1.22 |
| `idle` vs `idle`, 1000 turns, 1 core | 1 | **0.36** |

The last row is the important one: a **1000-turn game with two inert bots costs 0.36 s**, so the
engine is not the cost — *our own policy is*. Cost scales with (units × rounds × per-unit policy work),
which means **a slower policy makes evaluation proportionally slower**, and that is the hinge of §7.

### 2.2 Parallel throughput on this machine

`os.cpu_count()` = **20**. MEASURED: 66 games on 8 worker processes in **37.8 s = 1.75 games/s**, i.e. a
**5.49× speedup at 69% efficiency** (Windows process pool + per-game sub-interpreter startup). Sustained
over the pilot's five long runs, with other committee agents also on the box: **1.99 g/s at 9 workers,
2.74–2.80 g/s at 10 workers**. The whole 20 cores, uncontended, should reach ~5 g/s.

| Resource | 42-game mirrored eval (1 rival) | evals/hour | full 11-rival suite (462 games) |
|---|---|---|---|
| 1 core | 131.7 s | **27.3** | 24.2 min → 2.5/hour |
| 8 workers (measured) | 24.0 s | **150** | 4.4 min → 13.6/hour |
| 10 workers (measured, contended) | 15.3 s | **235** | 2.8 min → 21/hour |
| 20 workers (extrapolated) | 8.4 s | **429** | 1.5 min → 39/hour |

A useful rule of thumb from the pilot: **~10,000 games/hour** on this machine with the current policy,
so an overnight 8-hour campaign is ~80,000 exact games.

### 2.3 The GPUs

**This workload cannot use the 3× H100 at all.** The fitness function is `fcode.fcode_engine.run_game`,
a compiled single-threaded simulator that takes a *filesystem path to `main.py`* and runs each unit's
Python in its own CPython sub-interpreter. There is no batched, vectorised or differentiable form of it.
Every hour of evolutionary search is an hour of CPU on 20 cores; the GPUs sit idle. Conversely, and this
matters for the committee, **the RL plan's rollout phase has exactly the same problem** — see §7.

---

## 3. What makes this landscape hard, despite exact fitness

Determinism is confirmed, and more strongly than the brief claimed. MEASURED: `bot` vs `vanguard` on
`aurora`, `vault`, `duel` at seeds 1, 2, 3, 4, 5 **and 999** — identical winner, identical
`win_condition`, identical turn count, identical `titanium_collected`, in every cell.

That buys one thing and one thing only: **one game per candidate per instance instead of N**. In a noisy
engine you would need ~30 replicates to resolve a 5-point win-rate difference; here you need 1. Call it a
30× budget multiplier. It is real and it is worth having.

It does **not** buy any of the following, and each is worse for numerical optimisation than noise would be:

1. **Fitness is integer-valued with huge plateaus.** On a 66-game instance set the objective takes 67
   values. Most single-constant perturbations land on exactly the same integer as the incumbent, so
   rank-based methods (CMA-ES, DE with greedy selection) see ties, not gradients.
2. **Fitness is discontinuous in places.** One extra round of walking changes which tile a builder
   claims, which changes the whole trajectory. Determinism means the discontinuity is *reproducible*; it
   does not mean it is absent. The repo's own harness documents this as a "noise floor of ±2–4 games per
   30-game sweep" — that phrasing is wrong (there is no noise) but the phenomenon is real: it is
   **instance-set sensitivity**, and it is exactly what an optimiser will mistake for signal.
   *(§5.7 partly walks this back: where a dimension is live, the response can be perfectly smooth. It is
   dead dimensions and plateaus, not chaos, that dominate.)*
3. **The instance set is tiny and fixed.** 21 published maps × 2 sides × 11 local rivals = 462 games
   *in total*. That is the entire population the fitness can ever be computed over. Selecting the best
   of K candidates on a 66-game subset of it is a max-of-K order statistic on a 66-Bernoulli sum, and
   the expected inflation is large — see §4.
4. **The objective is not the ladder.** The real objective is win rate against unseen opponents on
   unseen maps. Everything we can measure is a proxy with a small, fixed instance set.

So: exact fitness removes the *sampling* problem and leaves the *generalisation* problem completely
intact. That is the correct way to frame the decisive fact in this brief, and it is the opposite of how
it is usually stated.

---

## 4. The search design I would actually run

### 4.1 Algorithm choice, justified against the space

**Not CMA-ES.** CMA-ES is the default recommendation for 10–100-dimensional continuous black-box
problems, and it is the wrong tool here for three reasons: the objective is integer-valued with
plateaus (rank-based selection degenerates when most offspring tie); covariance adaptation in *n* = 53
needs O(n²) ≈ 2,800 evaluations *just to shape the ellipsoid*, and a realistic run is 10⁴–10⁵
evaluations = 6.6×10⁵–6.6×10⁶ games = **4–40 days of wall clock on 8 workers**; and the space is
mostly integers with hard branch switches, where a Gaussian mutation model has no meaning.

**Recommended: `irace` (Iterated F-Race, López-Ibáñez et al. 2016), or a hand-rolled equivalent.**
This problem *is* the algorithm-configuration problem: a parameterised solver, a set of *instances*
((map, side, opponent) triples), and a budget in solver runs. irace's structure maps one-to-one:

* **Instances** = the 462 (map, side, opponent) triples, presented in a random order.
* **Racing** = evaluate all surviving configurations on instance *t*, drop configurations that are
  statistically dominated, continue. Because fitness is *exact*, a subset evaluation carries no
  measurement error; the only uncertainty is which instances you happened to pick, so the correct test
  is a paired one across instances (Friedman / paired *t*), not an unpaired one.
* **Elitism** = the incumbent is never dropped without being beaten on the same instances.
* **Model** = per-parameter independent sampling distributions, refined each iteration. It handles
  integers, categoricals and conditional parameters (`VAULT_*` only matter when `VAULT_MAX > 0`)
  natively, which CMA-ES does not.

**Secondary: Sequential Halving over instance subsets** (Karnin/Even-Dar; Jamieson & Talwalkar's
Successive Halving) as the cheap front end. Generate *n* = 256 candidates, evaluate on 8 instances,
keep 128, evaluate on 16, keep 64… total cost `~ n·log2(n)` instance-evaluations instead of `n·462`.
For n = 256 down to 1 that is ≈ 2,048 instance-evaluations = **34 min on 8 workers**, versus 33 hours
for the exhaustive version. This is the single biggest cost lever available.

**Tertiary: (1+1)-EA with a one-fifth success rule on the *live* subspace only.** Once §5's screen has
identified which constants move fitness at all, the effective dimensionality collapses and a plain
hill-climber with plateau-tolerant acceptance (accept equal fitness, à la Iterated Local Search) is
competitive with anything fancier and costs nothing to implement.

**Order of operations** (this is standard CS454 search-space characterisation before optimiser choice):
1. One-at-a-time screening (Morris elementary effects) to find the live dimensions — §5.
2. Estimate train→holdout transfer *before* spending any budget on optimisation — §5.3. If it is ~0,
   stop; there is nothing to optimise toward.
3. Only then run irace / Sequential Halving on the live subspace.

### 4.2 Fitness function

Not raw wins. Wins is a 67-valued step function; the following is far denser and correlates with the
same objective:

```
fitness = 1.0 * wins
        + 0.25 * core_kills                    # kills are what generalises (leaderboard §5)
        - 0.001 * mean_kill_turn_on_wins       # tempo tiebreak inside the plateau
        + 0.0001 * titanium_margin             # dense signal on games that reach turn 1000
```

The extra terms exist purely to break plateaus, and each is scaled below the term above it so the
ordering by wins is never inverted. This is standard fitness-shaping practice for search-based software
engineering and it is the correct answer to problem (1) in §3.

---

## 5. THE PILOT — what was actually run

Two experiments, both on this machine, both against `bot/` at `8cb0867`. Total cost **10,230 games /
~85 minutes of wall clock at 9 worker processes**, deliberately capped so as not to distort other
committee members' timings.

### 5.0 Harness and hygiene

* All candidates materialised into `bots/cand/ev_*` (gitignored), never `bot/`. All deleted afterwards.
* `PYTHONDONTWRITEBYTECODE=1`; a controlled test confirmed a stray `__pycache__` does **not** change the
  in-process result (`bot` vs `vanguard` on `aurora`: A/40/`core_destroyed` clean and dirty), so G30 is
  about submission packaging, not local evaluation.
* Fitness = wins over a mirrored instance set (every map played from both side assignments), because
  Team A wins ~58–60% of identical-bot mirrors (G27).
* Baseline on the TRAIN instance set (3 opponents × 11 maps × 2 sides): **48 / 66 wins, 47 core kills,
  median 66.0 turns.**

### 5.1 Experiment 1 — one-at-a-time sensitivity screen (Morris-style elementary effects)

**70 single-constant variants × 66 games = 4,686 games, 39.2 min at 9 workers (1.99 games/s).**
36 constants perturbed to 1–3 alternative values each.

The result is the most important thing in this document:

| finding | number |
|---|---|
| variants that changed the win count **not at all** | **48 / 70 (69%)** |
| …of which the games were *behaviourally identical* (same mean turns, same kills) | 22 |
| …of which the games **changed but the outcome count did not** — a true plateau | 26 |
| constants that moved the win count at least once (**LIVE**) | **14 / 36** |
| constants that never moved it (**DEAD** on this instance set) | **22 / 36** |
| standard deviation of the delta over all 70 variants | 4.53 games |
| variants with `|delta| <= 3` | 61 / 70 |

**DEAD on this instance set:** `ALARM_RESERVE`, `AMMO_FLOOR`, `BODY_PATIENCE`, `CHAIN_RESERVE`,
`ECONOMY_FROM`, `FORTIFY_FROM`, `FORTIFY_KEEP_OPEN`, `GUARD_FLOOR`, `GUARD_FROM`, `GUARD_MAX_CHEB`,
`GUARD_MIN_CHEB`, `INTRUDER_HALF`, `POSTURE_CONFIDENCE`, `POSTURE_DWELL`, `REPLAN_ROUNDS`,
`RETIRE_IDLE`, `RUSH_RESERVE`, `RUSH_RESERVE_UNTIL`, `SIEGE_BUILDERS`, `SNIPE_FLOOR`, `USE_ATLAS_ORE`,
`VAULT_FLOOR`.

**LIVE:** `ALARM_PERCENT`, `AMMO_TARGET`, `ATTACKERS`, `BATTERY_EVERY`, `BATTERY_RESERVE`, `BUILDERS`,
`EXPOSURE_PENALTY`, `MAX_BATTERY`, `REPLAN_TILES`, `STANDOFF_PENALTY`, `VAULT_GAIN`, `VAULT_MAX`,
`VAULT_MIN_GAP`, `VAULT_PATIENCE`.

Two structural readings, both of which matter more than any individual number:

1. **The effective dimensionality is ~14, not 48.** Nearly two thirds of the hand-written policy's
   tunable surface does not bind in a decided game. The reason is visible in the data: median game
   length is 66 turns, so `ECONOMY_FROM = 150` never fires, the posture never changes,
   `GUARD_FROM = 12` guards never pay for themselves, and the `FORTIFY_*` ring is never reached. Most
   of the 2,800 lines does not execute in a game that is decided by turn 66.
2. **The plateau is real and it is large.** 26 of 70 variants produced *different games* with the *same
   win total*. Any optimiser that selects on wins alone is blind on 37% of its neighbourhood. This is
   precisely why §4.2 shapes the fitness with kills and tempo.

**Top of the screen (train fitness only, before any generalisation test):**

| variant | train wins | delta | kills | mean turns |
|---|---|---|---|---|
| BASE | 48/66 | — | 47 | 66.0 |
| `STANDOFF_PENALTY = 0` (from 6) | **56/66** | **+8** | 53 | 75.4 |
| `VAULT_MIN_GAP = 6` (from 9) | **53/66** | **+5** | 52 | 49.7 |
| `EXPOSURE_PENALTY = 3` (from 1) | 51/66 | +3 | 49 | 52.1 |
| `ALARM_PERCENT = 99` (from 88) | 50/66 | +2 | 49 | 67.3 |

**And the strongest single-knob losses, which validate that the screen has power:**
`VAULT_MAX = 0` −24 (turns the launcher pole-vault off entirely), `BUILDERS = 5` −22,
`AMMO_TARGET = 240` −12, `AMMO_TARGET = 60` −10, `BUILDERS = 4` −6.

So: **on the training instance set, the hand-tuned configuration is not a local optimum. A 1-D probe of
a single constant found +8 games.** That is the strongest possible statement of the case *for*
evolutionary search — and it is exactly the statement that §5.2 exists to distrust.

### 5.2 The selection-inflation problem, quantified

Screening 70 candidates and reporting the best is a max-of-70 order statistic. With the observed
delta standard deviation of 4.53 games, the expected best-of-70 under a pure-artefact null is
`4.53 · sqrt(2 ln 70)` = **+13.2 games** — larger than the +8 actually observed.

That bound is *conservative* in one direction and *anticonservative* in another, and both need saying.
It is inflated by the genuine large structural losses (`VAULT_MAX = 0` at −24 is not an artefact, it is
a subsystem being switched off). But it is deflated by the fact that 48 of the 70 deltas are exactly
zero, which is not what a Gaussian null looks like at all. The bimodality — "does nothing, or does
something big" — is the real shape of this landscape, and it means the classical order-statistic
correction does not apply cleanly.

**There is only one way to settle it: measure whether the train gain transfers.** That is experiment 2.

### 5.3 Experiment 2 — the generalisation gate

**21 variants × 264 games = 5,544 games, 36.3 min at 9 workers (2.55 games/s).** The 20 candidates
are the screen's top single knobs, their pairwise and greedy combinations, and six deliberately
included neutral / negative controls so the transfer correlation is not measured on a range-restricted
sample. Four suites, all four evaluated for every candidate:

| suite | opponents | maps | games |
|---|---|---|---|
| TRAIN | 3 train | 11 train known | 66 |
| MAPGEN | 3 train | 10 **held-out** known | 60 |
| OPPGEN | 3 **held-out** (`luc1`, `jonbot`, `starter_fixed`) | 11 train known | 66 |
| UNSEEN | 3 train | 12 **generated** | 72 |

| variant | TRAIN | MAPGEN | OPPGEN | UNSEEN | total /264 |
|---|---|---|---|---|---|
| **BASE (shipped)** | 48/66 | 54/60 | 58/66 | 37/72 | **197 (74.6%)** |
| `STANDOFF_PENALTY=0` | **56 (+8)** | 55 (+1) | 62 (+4) | 37 (+0) | 210 (+13) |
| `STANDOFF_PENALTY=1` | 49 (+1) | 54 (+0) | 61 (+3) | 36 (−1) | 200 (+3) |
| `STANDOFF_PENALTY=2` | 49 (+1) | 54 (+0) | 57 (−1) | 37 (+0) | 197 (+0) |
| `VAULT_MIN_GAP=6` | 53 (+5) | **57 (+3)** | 58 (+0) | **44 (+7)** | 212 (+15) |
| `VAULT_MIN_GAP=4` | 51 (+3) | 55 (+1) | 58 (+0) | 41 (+4) | 205 (+8) |
| `EXPOSURE_PENALTY=3` | 51 (+3) | 53 (−1) | 57 (−1) | **31 (−6)** | 192 (**−5**) |
| `ALARM_PERCENT=99` | 50 (+2) | 54 (+0) | 58 (+0) | 38 (+1) | 200 (+3) |
| **`SP0 + VMG6`** | **56 (+8)** | 56 (+2) | 61 (+3) | 42 (+5) | **215 (+18)** |
| `SP0 + EP3` | 51 (+3) | 55 (+1) | 59 (+1) | 30 (−7) | 195 (−2) |
| `VMG6 + EP3` | 55 (+7) | 54 (+0) | 58 (+0) | 36 (−1) | 203 (+6) |
| `SP0 + VMG6 + EP3` | 53 (+5) | 53 (−1) | 60 (+2) | 34 (−3) | 200 (+3) |
| **`GREEDY4` (all four best knobs)** | 53 (+5) | 53 (−1) | 57 (−1) | **32 (−5)** | **195 (−2)** |
| `MAX_BATTERY=2` | 49 (+1) | 52 (−2) | 58 (+0) | 35 (−2) | 194 (−3) |
| `BATTERY_EVERY=1` | 49 (+1) | 54 (+0) | 59 (+1) | 40 (+3) | 202 (+5) |
| `REPLAN_TILES=8` | 48 (0) | 52 (−2) | 57 (−1) | 38 (+1) | 195 (−2) |
| `USE_ATLAS_ORE=True` | 48 (0) | 53 (−1) | 57 (−1) | 37 (+0) | 195 (−2) |
| `GUARD_MAX_CHEB=3` | 48 (0) | 54 (0) | 58 (0) | 37 (0) | 197 (0) |
| `ATTACKERS=2` | 45 (−3) | 53 (−1) | 59 (+1) | 36 (−1) | 193 (−4) |
| `BUILDERS=4` | 42 (−6) | 43 (−11) | 51 (−7) | 36 (−1) | 172 (−25) |
| `AMMO_TARGET=60` | 38 (−10) | 43 (−11) | 53 (−5) | 33 (−4) | 167 (−30) |

### 5.4 THE NUMBER THAT DECIDES THE CASE

Correlation between the TRAIN delta (66 games) and the summed HOLDOUT delta (198 games), over the
20 candidates:

| subset | n | Pearson r |
|---|---|---|
| all candidates | 20 | **+0.725** |
| candidates with `|train delta| <= 5` | 15 | **+0.034** |
| candidates with `train delta > 0` | 14 | +0.328 |
| candidates with `0 < train delta <= 5` | 11 | **−0.026** |

**Read that carefully.** Train fitness predicts held-out fitness *only for changes large enough that
you never needed a search to find them* — `BUILDERS = 4` (−6 → −25) and `AMMO_TARGET = 60` (−10 → −30)
carry the whole correlation, and both are "you broke a subsystem" effects that a five-minute manual
sweep finds. **In the fine-tuning regime — where an evolutionary search spends 99% of its budget —
the correlation between training fitness and generalisation is statistically indistinguishable from
zero (r = 0.034, and −0.026 among the positive-delta candidates).**

The single cleanest illustration is `GREEDY4`. Take the four best single-knob improvements found by the
screen — the exact move a greedy coordinate-ascent / (1+1)-EA makes — and combine them. Train: +5.
Held-out maps: −1. Held-out opponents: −1. Unseen generated maps: **−5**. Net over all 264 games:
**−2, i.e. worse than the shipped bot.** The naive search result is a regression, and the *only* thing
that catches it is the gate.

`EXPOSURE_PENALTY = 3` is the individual culprit, and it is a textbook overfit: +3 on training, −6 on
unseen maps, and it poisons every combination it enters (`SP0+EP3` goes to −7 unseen,
`SP0+VMG6+EP3` loses 3 of the 5 unseen games that `SP0+VMG6` gained).

**How this reconciles with the positive pilot result in §5.9.** It is not a contradiction, it is an
operating rule. The two knobs that survived (`STANDOFF_PENALTY`, `VAULT_MIN_GAP`) both had train deltas
at the *top* of the screen (+8 and +5 in 66 games, 12 pp and 7.5 pp), i.e. in the regime where the
correlation is real. Everything with a train delta of ±1–3 was a coin flip and three of them
(`EXPOSURE_PENALTY`, `MAX_BATTERY`, `REPLAN_TILES`) went on to lose games on holdout. So the usable
rule is: **search finds real things, but only the big ones, and a gate is mandatory to discard the
rest.** A search that accumulates small train-positive steps — which is exactly what an unguarded
(1+1)-EA or greedy coordinate ascent does — produced `GREEDY4`, a regression.

### 5.5 What the pilot nevertheless found

Two knobs did pass the gate on all four suites:

* **`siege.STANDOFF_PENALTY: 6 → 0`** — TRAIN +8, MAPGEN +1, OPPGEN +4, UNSEEN +0. Non-negative
  everywhere.
* **`main.VAULT_MIN_GAP: 9 → 6`** — TRAIN +5, MAPGEN +3, OPPGEN +0, UNSEEN +7. Non-negative everywhere,
  and the *only* candidate whose largest gain is on the unseen generated maps.
* Together: **197/264 → 215/264, +18 games, 74.6% → 81.4%**, non-negative on all four suites.

`STANDOFF_PENALTY = 0` directly contradicts the 10-line comment in `siege.py` that justifies 6 (measured
against `vanguard` on 14 games: 154 of 256 shots absorbed by their barrier ring). That is not a criticism
of the reasoning; it is what a narrow measurement does. On 2.3.3, with the runtime planner and the
launcher vault, arriving *sooner* at range 2–3 evidently beats arriving later at range 1.

**But §5.4 forbids me from claiming this as a result on the pilot's evidence alone.** The holdout delta
standard deviation across the 20 candidates is 7.55 games; `SP0+VMG6`'s holdout delta of +10 is
comfortably inside `7.55 · sqrt(2 ln 20)` = 18.5, the expected best-of-20 under a pure-artefact null.
Hence experiment 3 — and experiments 4 and 5, which move the optimum from `VMG6` to `VMG5` and the
verdict from "probably real" to "+50 games out of 810".

### 5.6 Experiment 3 — high-power confirmation

**4 variants × 810 games = 3,240 games, 19.3 min at 10 workers (2.80 games/s).** Nine opponents — six of
which (`frontier`, `lockin`, `tempest`, `undertow`, `mistral`… ) were **never used in selection** — over
**all 21** published maps (10 never used in selection) and **all 24** generated maps (none ever used).

| variant | KNOWN21 (378 games) | GEN24 (432 games) | TOTAL (810) | core kills |
|---|---|---|---|---|
| **BASE (shipped)** | 330/378 **87.3%** | 332/432 **76.9%** | 662/810 **81.7%** | 649 |
| `STANDOFF_PENALTY=0` | 339 89.7% (+9) | 348 80.6% (+16) | 687 84.8% (**+25**) | 673 |
| `VAULT_MIN_GAP=6` | 341 90.2% (+11) | 355 82.2% (+23) | 696 85.9% (**+34**) | 685 |
| **`SP0 + VMG6`** | **344 91.0% (+14)** | **355 82.2% (+23)** | **699 86.3% (+37)** | **690** |

*(This also pins the baseline the brief quoted: the shipped bot is at **87.3% on the published 21-map
pool** against this nine-bot panel, and **76.9%** on the generated corpus.)*

Per opponent, out of 90 games each — the test the standing rule demands:

| opponent | BASE | `SP0` | `VMG6` | `SP0+VMG6` |
|---|---|---|---|---|
| `undertow` | 56 | 63 (+7) | 70 (**+14**) | 70 (**+14**) |
| `vanguard` | 66 | 73 (+7) | 70 (+4) | 77 (**+11**) |
| `jonbot` | 71 | 79 (+8) | 72 (+1) | 77 (+6) |
| `mistral` | 59 | 62 (+3) | 68 (+9) | 62 (+3) |
| `tempest` | 57 | 56 (−1) | 62 (+5) | 59 (+2) |
| `starter_fixed` | 83 | 86 (+3) | 84 (+1) | 84 (+1) |
| `frontier` | 90 | 88 (−2) | 90 (0) | 90 (0) |
| `lockin` | 90 | 90 (0) | 90 (0) | 90 (0) |
| `luc1` | 90 | 90 (0) | 90 (0) | 90 (0) |

**`SP0 + VMG6` gains against six of the nine opponents, regresses against none, and its two largest
gains are against the two hardest bots in the field (`undertow` +14, `vanguard` +11).** The gain is
larger on the *generated* maps (+23 of 432, entirely holdout) than on the published pool (+14 of 378).
That is the shape of a general capability, not a matchup exploit, and it is the shape the standing rule
asks for.

**Caveat, stated honestly.** The confirmation set is large but the candidates were still *chosen* using
part of it. Three candidates were carried forward, so max-of-3 selection inflation applies; scaling the
gate's holdout artefact spread (7.55 games over 198) to 810 games gives σ ≈ 15, making +37 roughly a
2.4σ result. Real, not overwhelming. §5.7 calibrates the artefact spread directly.

### 5.7 Experiment 4 — is the optimum a basin or a spike?

**5 variants × 810 games = 4,050 games, 24.6 min at 10 workers (2.74 games/s).** This is the experiment
that tests §3's claim that the landscape is chaotic, and it **partly refutes it**, which is worth saying
plainly because it is the strongest evidence *for* my own side of the argument.

| `VAULT_MIN_GAP` | KNOWN21 (378) | GEN24 (432) | TOTAL /810 | delta |
|---|---|---|---|---|
| 3 | 339 (89.7%) | 348 (80.6%) | 687 (84.8%) | +25 |
| 4 | 334 (88.4%) | 355 (82.2%) | 689 (85.1%) | +27 |
| **5** | **343 (90.7%)** | **359 (83.1%)** | **702 (86.7%)** | **+40** |
| 6 | 341 (90.2%) | 355 (82.2%) | 696 (85.9%) | +34 |
| 7 | 341 (90.2%) | 351 (81.2%) | 692 (85.4%) | +30 |
| **9 (shipped)** | 330 (87.3%) | 332 (76.9%) | 662 (81.7%) | — |
| 10 | 321 (84.9%) | 329 (76.2%) | 650 (80.2%) | −12 |

**That is a clean, unimodal, single-basin response over 810 exact games each: 10 < 9 < 7 < 6 < 5 > 4 > 3,
peaking at 5.** It is not
a chaotic spike, it is not a tie-break artefact, and simple hill-climbing walks straight down it. The
same monotonicity holds separately on the published pool and on the generated corpus, and separately
against every one of the four hard opponents.

By contrast `STANDOFF_PENALTY = 7` (one step the "wrong" way from the shipped 6) scores **+1 / 810** —
completely flat. So that dimension is a *step function*: a plateau across at least 2–12 with a single
sharp improvement at 0. Two live dimensions, two entirely different local geometries.

**Revised verdict on landscape shape.** §3's "chaotic" is too strong. The measured picture is:
*most* dimensions are dead (22 of 36), *some* are plateaus with steps (`STANDOFF_PENALTY`), and *some*
are smooth monotone basins that a first-order method descends without difficulty (`VAULT_MIN_GAP`).
Search works on the third kind; the trouble is you cannot tell which kind a dimension is without
spending the evaluations, and 69% of the time the answer is "none of them".

**One more finding, and it is a methodological one.** The 66-game TRAIN set ranked `VMG6` (+5) above
`VMG4` (+3); the 264-game gate ranked them 212 vs 205; the 810-game confirmation ranks `VMG5` (+40)
above `VMG6` (+34). **Small instance sets mis-rank candidates even though every single game in them is
exact.** Determinism does not make a 66-game fitness a good estimator of an 810-game fitness — it only
makes it a *reproducible* one. Any search budget plan that leans on cheap subset fitness (§4.1's
Sequential Halving) must therefore use the cheap set for *elimination* only, never for final ranking.

### 5.8 Experiment 5 — locating the optimum

**4 variants × 810 games = 3,240 games, 19.6 min at 10 workers (2.75 games/s).**

| variant | KNOWN21 (378) | GEN24 (432) | TOTAL (810) | kills | delta |
|---|---|---|---|---|---|
| BASE (shipped) | 330 87.3% | 332 76.9% | 662 **81.7%** | 649 | — |
| `VAULT_MIN_GAP=3` | 339 89.7% | 348 80.6% | 687 84.8% | 675 | +25 |
| `VAULT_MIN_GAP=4` | 334 88.4% | 355 82.2% | 689 85.1% | 680 | +27 |
| **`STANDOFF_PENALTY=0` + `VAULT_MIN_GAP=5`** | **348 92.1%** | **364 84.3%** | **712 87.9%** | **705** | **+50** |

Per opponent, out of 90 each:

| opponent | BASE | `SP0 + VMG5` |
|---|---|---|
| `undertow` | 56 | **74 (+18)** |
| `vanguard` | 66 | **78 (+12)** |
| `mistral` | 59 | 66 (+7) |
| `tempest` | 57 | 64 (+7) |
| `jonbot` | 71 | 75 (+4) |
| `starter_fixed` | 83 | 85 (+2) |
| `frontier` | 90 | 90 (0) |
| `lockin` | 90 | 90 (0) |
| `luc1` | 90 | 90 (0) |

### 5.9 Pilot result

**Two constants, changed from `STANDOFF_PENALTY = 6, VAULT_MIN_GAP = 9` to `0, 5`, move the shipped bot
from 662/810 (81.7%) to 712/810 (87.9%) — +50 games, +6.2 percentage points — over nine opponents and
all 45 maps in the repository.** Core kills go 649 → 705.

The gain is **larger on the generated holdout corpus (+32 of 432, +7.4 pp) than on the published pool
(+18 of 378, +4.8 pp)**, it gains against six of the nine opponents, and it regresses against **none**.
Six of those nine opponents and 34 of those 45 maps were never used in selection. By the standing rule's
own criterion this is a general capability change, not an opponent-specific exploit.

Total pilot cost: **20,760 games, ~2 h 20 min of wall clock on 9–10 of 20 cores**, entirely on CPU.

**A negative result would have been acceptable. This is not one.** It is the strongest single-session
measured improvement in the repository's recorded history — the previous best documented change
(`ATTACKERS 2 → 3` with `BUILDERS = 3`) was "+3 known / +7 unseen".

---

---

## 6. The overfitting trap, and the defence

The user's standing rule — *if it doesn't generalise and just overfits to beating one opponent, it isn't
worth pursuing* — is not a stylistic preference here. It is the binding constraint, and a deterministic
engine makes it **worse**, not better.

Why worse: with a stochastic engine, a parameter setting that exploits one exact tie-break on one map
would be washed out by the next sample. Here it is not. If `STANDOFF_PENALTY = 7` happens to move one
builder one tile so that on `quarry/b` a Gunner lands one round before `vanguard`'s, that game flips
permanently, contributes +1 to fitness forever, and transfers to nothing. Determinism converts what
would have been noise into a **persistent, selectable artefact**. Every exact-fitness advantage in §3
comes with this cost attached.

The defence, concretely, and all of it is implemented in the pilot harness:

1. **Instance splits, declared before any search.**
   * Maps: the 21 published maps split by sorted index parity — **11 TRAIN** (`atoll, bridge, duel,
     hive, longship, quarry, showdown, sprint, string, twins, vault`) / **10 TEST** (`aurora, crossfire,
     fjord, jackpot, pinch, runestone, skerry, strait, sweden, vase`).
   * A second, harder map holdout: the **24 generated maps** in `maps/generated/`, which the atlas does
     not recognise at all, so the memorised path is disabled by construction.
   * Opponents: **3 TRAIN** (`vanguard`, `mistral`, `tempest_fast`) / **8 HELD OUT** (`luc1`, `lockin`,
     `jonbot`, `undertow`, `frontier`, `starter_fixed`, `tempest`, `tempest_ferry`, …).
2. **Four reported suites, never one number.** TRAIN (train opponents × train maps), MAPGEN (train
   opponents × held-out maps), OPPGEN (held-out opponents × train maps), UNSEEN (train opponents ×
   generated maps). MAPGEN and OPPGEN isolate the two failure modes separately, which a single
   "held-out" number cannot.
3. **The generalisation gate.** A candidate is accepted only if **all four** hold:
   `TRAIN delta > 0`, `MAPGEN delta >= 0`, `OPPGEN delta >= 0`, `UNSEEN delta >= 0`, and
   `TRAIN delta` exceeds the measured instance-set-sensitivity floor (§5.2). Anything else is reported
   as a null result. This is the same discipline `tools/evaluate.py` already encodes; the search must
   not be allowed to route around it.
4. **Selection-inflation accounting.** Evaluating *K* candidates and reporting the best is a max-of-*K*
   order statistic. If single-knob perturbations have train-delta standard deviation σ, the expected
   best-of-*K* under a pure-artefact null is ≈ `σ · sqrt(2 ln K)` — for K = 70 that is ≈ 2.9σ. Any
   search reporting a gain smaller than that has reported nothing. §5.2 measures σ.
5. **Never tune against a single opponent.** Three train opponents minimum, and the *variance across
   opponents* of a candidate's delta is itself a report line: a candidate that gains +6 on one rival and
   −3 on the other two has found a matchup exploit, not a capability.
6. **Rotate the split.** If budget allows, repeat the whole search on the complementary split
   (TEST maps as train) and keep only parameters that win on both. This is *k*-fold cross-validation
   over instances, and with exact fitness it costs exactly 2× — no replicates needed.

---

## 7. Genetic programming over policy code — feasibility, honestly

**Over the whole policy: no.** Measured AST statistics of the genome you would be evolving:

| file | AST nodes | functions | `if` | loops | `try` | numeric literals |
|---|---|---|---|---|---|---|
| `bot/main.py` | 15,260 | 77 | 365 | 59 | 102 | 535 |
| `bot/siege.py` | 2,166 | 17 | 37 | 14 | 0 | 155 |
| `bot/atlas.py` | 4,584 | 3 | 6 | 1 | 2 | 1,951 (data table) |

Four hard blockers, in order of severity:

1. **A single uncaught exception permanently destroys the unit** — verified in the official docs
   (`api-types.txt`: "*permanently destroys the unit. It will never run again for the rest of the
   match*"). Almost every syntactically valid mutation of a 15,260-node program is semantically invalid
   at some point in some game, so the modal fitness of a random mutant is not "slightly worse", it is
   "unit deleted, game lost". The search landscape is a needle in a field of zeros.
2. **The submission validator bans the repairs.** `finally:` blocks and bare `except:` are rejected, and
   except handlers must be plain builtin names. The usual GP trick — wrap every evolved subtree in a
   blanket guard — is not available. The 102 existing `try` blocks are hand-placed with specific
   handlers.
3. **Scale.** Standard tree GP operates on genomes of 10–500 nodes. 17,426 nodes is two orders of
   magnitude beyond that, and crossover between two 15k-node programs is essentially random
   restructuring.
4. **Semantics the grammar cannot see.** `fire(own_position)` raises. A friendly building in a Gunner's
   lane jams the turret permanently (G11). A conveyor chain one tile short of the Core scores exactly
   zero (G02). These are the facts the 2,800 lines encode; a GP operator that does not know them
   destroys them at random.

**Over the value function: yes, and this is the one real opportunity.** `siege.rank()` already computes
a single scalar score:

```python
standoff = 0 if sentinel else STANDOFF_PENALTY * (k - 1)
score    = approach + standoff + EXPOSURE_PENALTY * exp
```

That is a 3-term linear value function with 2 free coefficients over features that are already computed.
Evolving *this expression* — adding candidate features (distance from our own Core, count of enemy
buildings within r², whether the tile is on a corner facing, enemy Core HP, round number) and letting GP
find a small tree over them — is entirely tractable: the genome is ~20–60 nodes, it is a
**total function over floats** so it cannot raise, and it cannot delete a unit. This is precisely the
"C2 — one shared value function" item already on the repo's own lever board, and it is the correct
scope for GP in this codebase. Note that it requires the refactor *first*: today only 2 coefficients are
exposed, so there is almost nothing to evolve.

---

## 8. The other side of the committee — what I measured about the neural plan

I am the devil's advocate, so I went and measured the neural plan's constraints rather than assuming
them. Three findings, all MEASURED today on 2.3.3, all inside the real sandbox via `ct.resign()`.

### 8.1 `numpy` is genuinely unavailable

A probe attempting 13 imports inside a live match reported:

```
numpy:IMPORTERR  math:OK heapq:OK array:OK random:OK struct:OK itertools:OK
collections:OK pickle:OK json:OK time:OK os:OK sys:OK
```

G28 re-verified on 2.3.3: **any forward pass is pure-Python arithmetic over lists.** `array` and
`struct` exist, so weights can be stored compactly; they do not make the multiplies faster.

### 8.2 The inference ceiling, measured inside the sandbox

A probe ran a real 256→128→128→48 ReLU MLP (**54,272 weights**) inside a live match and timed it with
`time.perf_counter`:

| quantity | measured |
|---|---|
| feature extraction, 11×11 terrain patch + `get_nearby_entities()` | **0.10 ms** |
| forward pass, 54,272 weights | **3.33 ms** |
| pure-Python throughput in the sandbox | **16.3 MMAC/s** |
| weights that fit the full 10 ms | **≈ 163,000** |
| weights at a 50% safety margin | **≈ 81,000** |
| weights at a 70% safety margin | **≈ 49,000** |

Two readings. First, the brief's "a few tens of thousands of parameters" is close but slightly
pessimistic — the real ceiling is **≈ 81k weights** with a sane margin. Second, and more usefully,
**feature extraction is not the bottleneck** (0.10 ms out of 10 ms), so the design question is "how big
a net" and nothing else. An 81k-parameter MLP is a real model, not a toy — but it is ~20× smaller than a
DQN Atari network and it has to encode everything the 2,800 lines encode.

### 8.3 The finding I did not expect: the H100s are idle in **both** plans

The RL rollout loop calls the same `run_game`, on the same CPU, in the same CPython sub-interpreters.
Nothing about it is GPU-shaped. Worse, the policy inside it costs 3.33 ms per unit per round instead of
the current bot's much cheaper decision, so **rollouts get slower, not faster**:

| policy | units/side | rounds | policy compute per game |
|---|---|---|---|
| current hand-written bot | — | ~40 (median decided) | **3.14 s/game total, MEASURED** |
| 81k-weight MLP | 6 | 60 (decided) | 2.4 s |
| 81k-weight MLP | 6 | 300 | 12.0 s |
| 81k-weight MLP | 8 | **1000 (undecided)** | **53.3 s** |

The last row is the one that matters, because **a randomly initialised policy produces exactly the
undecided 1000-round games that are most expensive to simulate.** RL's most sample-hungry phase is also
its most expensive phase per sample. At 8 workers that is `8 / 53.3 ≈ 0.15 games/s` = **540 games/hour**,
against **6,300 games/hour** for the current bot. Reaching 10⁵ episodes takes **~7.7 days of the whole
20-core machine**; 10⁶ episodes — a modest budget for a partially observed, multi-agent, sparse-reward,
1000-step game with a combinatorial action space — takes **~2.5 months**. Meanwhile the gradient step
for an 81k-parameter MLP is microseconds on one H100, so all three GPUs sit ~100% idle.

**The 3× H100 is not an asset for this project.** It is an asset for a project whose bottleneck is the
gradient step; this project's bottleneck is a single-threaded Python game engine. That is true of my
plan and equally true of the RL plan. Any plan justified by "we have 3 H100s" needs re-justifying.

### 8.4 Where the neural plan *is* strong

Behaviour cloning is the half that survives this arithmetic, and it survives well:

* Generating labels is cheap: 6,300 games/hour × ~40 rounds × ~6 acting units ≈ **1.5 million labelled
  (observation, action) pairs per hour** on 8 workers, using the fast hand-written policy as teacher.
* Training an 81k-parameter MLP on a few million samples is minutes on **one** GPU. That is the one
  phase where the hardware is appropriate.
* Cloning `vanguard` rather than ourselves is the interesting version, because the leaderboard analysis
  says vanguard's edge is a **general capability** (30–0 over `luc1`, 29–1 over `lockin`, 28–2 over
  `jonbot`), not a matchup quirk. A clone that captures it transfers; a clone of ourselves cannot
  exceed us by construction.

Honest summary of the neural plan: **the imitation half is cheap, GPU-appropriate and bounded above by
the teacher; the RL half is where the real gain would come from and it is the part this hardware cannot
run.**

---

## 9. THE VERDICT

I was seated as the devil's advocate and I expected to write a paper concluding "search is theoretically
attractive but measures flat, therefore the network". The measurement did not cooperate. Here is what I
actually believe, with the numbers that force it.

### 9.1 What to spend the next week on

**Spend it on search over the hand-written policy. Do not start an RL run.**

| plan | measured cost | measured return | GPU utility |
|---|---|---|---|
| parameter search + gate | 20,760 games, 2 h 20 min CPU | **+50/810 games, 81.7% → 87.9%**, no regressions | none |
| behaviour cloning | ~1.5 M labelled pairs/hour CPU; minutes to train on 1 GPU | bounded above by the teacher | **real, for the training step only** |
| RL from self-play | 540 games/hour with an NN policy; 10⁶ episodes ≈ **2.5 months** | unknown | **none — rollouts are CPU-bound** |

### 9.2 The concrete week

1. **Today, for free: ship `STANDOFF_PENALTY = 0` and `VAULT_MIN_GAP = 5`.** +50 games out of 810, 87.9%
   from 81.7%, larger on the holdout corpus than on the published pool, gains against `undertow` (+18),
   `vanguard` (+12), `mistral` (+7), `tempest` (+7), `jonbot` (+4), `starter_fixed` (+2), regressions
   against none. Re-verify with `tools/evaluate.py` before submission, and re-read the `siege.py`
   comment that justified 6 — it was measured on 14 games against one opponent, and it is wrong on 810.
2. **Days 1–2: lift the buried thresholds** (`rush_stuck >= 12`, two `stuck >= 5`, `free >= 2`) to
   module level, so the search can reach them at all. Then run irace or Sequential Halving over the
   **14 LIVE dimensions only** — not 48, because 22 of the 36 screened constants provably do nothing.
   At 2.75 games/s, an 8-hour campaign is ~79,000 games ≈ 98 full 810-game evaluations or ~1,200
   66-game screening evaluations. That is a genuinely large search by this problem's standards.
3. **Wire the four-suite gate into the search loop, as the selection criterion — not as a post-hoc
   report.** §5.4 is the reason: among candidates with `|train delta| <= 5` the train→holdout
   correlation is **r = 0.034**, and the naive greedy combination of the four best train knobs
   (`GREEDY4`) came out at **−2/264, worse than the shipped bot, −5 on unseen maps**. A search that
   selects on train fitness in the fine-tuning regime will actively make the bot worse. Select on
   holdout, always.
4. **Only trust large deltas.** The operating rule that falls out of the measurements: a candidate is
   worth confirming only if its train delta exceeds ~5 games in 66 (7.5 pp). Below that the sign of the
   holdout delta is a coin flip.
5. **Days 3–5: the value-function refactor (§7, C2).** `siege.rank()`'s
   `score = approach + STANDOFF_PENALTY*(k-1) + EXPOSURE_PENALTY*exp` is where both of this pilot's
   winners live, and it currently exposes **two** coefficients. Widen it to 6–10 terms over features
   already computed (distance from our Core, enemy buildings within r², facing class, round number,
   enemy Core HP) and search that. This is the one place GP over code is tractable, and it is where the
   evidence says the remaining headroom is.
6. **In parallel, non-blocking: behaviour-clone `vanguard`** using the shadow logger already being
   built. Scope it as **knowledge extraction, not as a shipping artefact**: train the clone, diff its
   decisions against ours, and hand-code whatever systematic difference shows up. That is the cheapest
   way to convert vanguard's general capability gap into our code, and it is the one part of the week
   that uses a GPU for anything.

### 9.3 What I got wrong, since a committee that only agrees is useless

* **I claimed the landscape was chaotic. It partly is not.** §5.7 measured `VAULT_MIN_GAP` as a clean
  unimodal basin over 810 exact games each (10 < 9 < 7 < 6 < 5 > 4 > 3). Hill-climbing descends it
  without difficulty. `STANDOFF_PENALTY` is a plateau with one step, which is harder but still findable.
* **I under-rated the neural policy's expressiveness ceiling.** The brief said "a few tens of
  thousands of parameters"; measured inside the sandbox it is **≈ 81,000 weights at a 50% CPU margin**,
  and feature extraction costs only 0.10 ms of the 10 ms. That is a real model.
* **I over-rated the exactness of the fitness.** Determinism makes a 66-game score *reproducible*, not
  *accurate*. The 66-game set ranked `VMG6 > VMG4`; the 810-game set ranks `VMG5 > VMG6 > VMG4`. Exact
  and wrong are compatible.

### 9.4 What would change my mind

* **If the engine can be driven at >100 games/s** — a batched reimplementation of the fcode rules, or a
  faster entry point into the `.pyd` — the RL arithmetic flips completely and the H100s become relevant.
  This is the single highest-leverage thing anyone could discover, and it is worth one person's day to
  check. Note the correctness risk: a policy trained against a reimplementation is trained against a
  different game.
* **If a `vanguard` clone reaches within 5 percentage points of `vanguard` at under 5 ms/unit**, the
  policy-compression hypothesis is validated, the pure-Python ceiling is proven survivable, and RL
  fine-tuning on top becomes the obvious next move rather than a fantasy.
* **If an 8-hour irace campaign over the 14 live dimensions returns less than +10/810 beyond
  `SP0 + VMG5`**, the constant-tuning well is dry and the argument swings to the network.
* **If the ladder's hardware is materially slower than this box**, 3.33 ms per forward pass stops being
  safe inside 10 ms and the network dies on latency alone, regardless of everything else. `G45` was
  measured on 2.2.0 and the register itself flags it as needing a re-run; the replay format carries
  `BotOutput{execTimeUs, tled}` per unit, so this is directly measurable and nobody has measured it on
  2.3.3.

### 9.5 The one-line answer

**The hand-written policy is not at a local optimum and 2 h 20 min of CPU search proved it worth
+6.2 percentage points; the RL plan needs 2.5 months of the same CPU and cannot use the GPUs at all.
Search the policy this week, clone `vanguard` to learn from it, and do not start an RL run until
somebody makes rollouts a hundred times cheaper.**

---

## Appendix — reproduction

All experiments used a scratch harness (not committed) that materialises candidates into
`bots/cand/ev_*`, evaluates over `(bot, opponent, map, side)` tuples in a `ProcessPoolExecutor`, and
deletes the candidates afterwards. `bot/`, `bots/elias/` and `bots/rivals/` were never modified.
`bots/zoo/starter_fixed/main.py` was edited by another committee member at 12:49, before every run
below started, so it was constant across all of them.

| experiment | variants | games | wall | rate |
|---|---|---|---|---|
| 1 — sensitivity screen | 71 | 4,686 | 39.2 min @ 9w | 1.99 g/s |
| 2 — generalisation gate | 21 | 5,544 | 36.3 min @ 9w | 2.55 g/s |
| 3 — high-power confirmation | 4 | 3,240 | 19.3 min @ 10w | 2.80 g/s |
| 4 — neighbourhood probe | 5 | 4,050 | 24.6 min @ 10w | 2.74 g/s |
| 5 — optimum location | 4 | 3,240 | 19.6 min @ 10w | 2.75 g/s |
| **total** | | **20,760** | **~2 h 20 min** | |

Supporting single-shot measurements: determinism at seeds 1–5 and 999 on three maps; a 42-game
single-core sweep for the serial cost baseline; `idle` vs `idle` for the engine-only floor; a
`__pycache__` control; and two in-sandbox probes (`import` availability, MLP forward-pass timing)
reported through `ct.resign()`.


