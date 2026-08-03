# Beyond imitation — what the loss function is once cloning is done

Seat: stage 2 of the two-stage learning system. The question is not "how do we copy the good bots",
it is "what objective makes the thing exceed the bots it copied".

Everything numeric below was measured on this machine during this analysis unless it carries a `G##`
tag, in which case it comes from `llm-slop-analysis/elias/ground-truth.md`. Nothing under `bot/`,
`bots/elias/` or `bots/rivals/` was modified; the instrumented copies live in the session scratchpad.

---

## 0. The answer, up front

**There is a learnable V(s), and it is much easier to find than the AlphaGo framing suggests.** A
hand-written potential function built from nine scalars a unit can read for free — no fitting, no
network, no training — separates winners from losers at **AUC 0.889 at turn 20, 0.951 at turn 30,
0.981 at turn 40** across 126 games against 9 different rivals on 7 maps. The user's own first guess,
*differential Core HP*, is on its own worth **AUC 0.906 at turn 20**. This game has an intrinsic
board value and it is roughly `0.5·ΔcoreHP + Δtitanium-equity`.

**Use it as a potential, not as a reward.** Ng, Harada & Russell (1999) guarantee that
`F(s,s') = γΦ(s') − Φ(s)` leaves the optimal policy untouched for *any* Φ. That converts the value
function from a thing you have to get right into a thing you cannot get wrong, which matters here
because two of the terms point the opposite way to intuition (see §1.4: banked titanium and banked
ammo both **anti-correlate** with winning).

**AlphaZero is off the table, and not because of branching factor.** `fcode.fcode_engine` exports
exactly one symbol: `run_game`. There is no step function, no state snapshot, no clone. MCTS cannot
expand a node because there is no node to expand. This is a hard architectural fact, verified.

**Recommendation, in priority order:**

1. **CMA-ES with margin over ~20 constants of the existing bot, with a graded fitness.** Highest
   expected value per engineer-hour, ~3 days, uses the harness that already exists.
2. **A supervised win-probability model** (half a day) — it is the diagnostic that tells you whether
   anything downstream can work, and its coefficients are the Φ for every later method.
3. **A neural *ranker* over the bot's own candidate moves**, trained by MAPPO with the Φ above, only
   if (1) plateaus. Not a neural policy from scratch: a 33k-MAC net will not rediscover the
   map-symmetry deduction that finds the enemy Core, and that single deduction is worth more than
   everything a net of that size can learn.
4. **Not genetic programming over policy code.** Reasons in §5.3.

**And the compute observation you will not like: the 3× H100 are the wrong resource.** The engine is
a CPython extension driving pure-Python bots. The shippable network is ~33 000 multiply-accumulates,
which is ~5 µs of *one CPU core* under numpy. Rollouts are CPU-bound and GPU-irrelevant. Ask for
cores, not cards.

---

## 1. The value function

### 1.1 What I measured

I copied `bot/` to a scratchpad, added a god-state logger to `Player.run()` (file writes work from
inside the sandbox — see §6.1), and played **126 games**: our bot vs 9 opponents (`luc1`, `vanguard`,
`frontier`, `tempest`, `undertow`, `mistral`, `jonbot`, `lockin`, `starter_fixed`) × 7 maps × both
sides. 65 346 per-unit rows. Wall time: **137 s on 14 cores**.

Sample composition, which matters for reading everything below:

| | |
|---|---|
| our win rate | 0.841 |
| decided by `core_destroyed` | **123 / 126** |
| decided by tiebreak | 3 / 126 |
| median game length | **35 turns** |
| longest | 1000 turns |

**The first finding is that against real opponents this game is decisive and short.** The 1000-round
limit and the tiebreak ladder are not the typical case at this skill level; they are the exception
(2.4%). That reframes the "sparse, long-horizon reward" premise: the horizon is ~35 rounds, not 1000.

### 1.2 Is there a learnable V(s)? Yes — measured

Nine features, all readable by any unit for free: own Core HP, enemy Core HP (only when a unit of
ours can see it), a "have we located the enemy Core" flag, titanium stored, ammo, own unit count,
cost scale, enemy units seen, enemy buildings seen.

A **linear** logistic regression on those nine, **held out by opponent** (train on 8 rivals, test on
the 9th, rotated):

| turn | games surviving | majority-class baseline | AUC in-sample | **AUC held-out opponent** |
|---|---|---|---|---|
| 10 | 126 | 0.84 | 0.761 | **0.580** |
| 20 | 123 | 0.86 | 0.927 | **0.845** |
| 30 | 79 | 0.84 | 0.920 | **0.844** |
| 40 | 42 | 0.76 | 0.950 | **0.872** |

By turn 20 — well before the median game ends at turn 35 — nine scalars and a linear model predict
the winner of a game against a bot the model has never seen, at AUC 0.845. **The value function
exists, it is nearly linear, and it is cheap.**

Turn 10 is genuinely undecided (AUC 0.58). That is a useful boundary: shaping has almost nothing to
say about the first ten rounds, and any method that tries to learn the opening from outcome signal
alone will be learning from noise. The opening is a *planning* problem (which ore, which firing
tile) and should stay in the hand-written planner.

### 1.3 The potential function I recommend

Denominate everything in **titanium**, because titanium is the one commensurable currency in this
game and because the tiebreak ladder is itself denominated in it.

```
Φ(s, t) = tanh( (E_us(s) − E_them(s)) / 300 )

E_team =  0.5 · coreHP
        + 1.0 · titanium_stored
        + 1.0 · ammo
        + 1.0 · titanium_collected
        + Σ_entities base_cost(e)        # BASE cost, never the scaled cost
```

Every weight is an exchange rate the engine itself fixes, not a guess:

- **ammo at 1.0** — `convert_ammo` is exactly 1:1 with titanium (G52). This is not a hyperparameter.
- **entities at base cost** — replacement value. It must be the *base* cost and not
  `get_*_cost()`, because the scaled cost is a function of your own build history; using it makes Φ
  farmable by destroying things to lower the scale. Base costs are constants (builder 30, gunner 10,
  harvester 20, sentinel 30, launcher 20, conveyor 3, splitter 6, barrier 3 — G07), so Φ stays a
  linear function of board contents.
- **titanium_collected at 1.0** — it is the primary tiebreak and it is *absolute*, not relative
  (G01/G03). It decides every drawn game.
- **coreHP at 0.5 Ti/HP** — a Gunner converts 2 Ti of ammo into 10 damage, so the marginal price of
  enemy Core HP is 0.2 Ti/HP. The measured end-to-end price of a Core kill is 162 Ti for 500 HP
  (G57) = 0.32 Ti/HP including the builder and the gunner. I round to 0.5 to price the escort and
  positioning overhead. A full Core is then worth ~250 Ti against a 500 Ti opening bank — the right
  order of magnitude.
- **K = 300 Ti in the tanh** — about 60% of the opening bank, so Φ saturates only when one side is
  decisively ahead. Bounding Φ bounds `|F| ≤ 1 + γ`, which matters with γ near 1.

**I tested this exact function, unfitted, on the logged states.** Because enemy titanium, ammo, scale
and unit count are unreadable (verified — the four team-global getters take no id and raise
`TypeError`), the enemy side is approximated by what our units can see:
`E_them ≈ 0.5·foeCoreHP + 30·foeUnitsSeen + 10·foeBuildingsSeen`, with foeCoreHP defaulting to 500
when unlocated.

| single scalar, no fitting | AUC @20 | AUC @30 | AUC @40 |
|---|---|---|---|
| **proposed Φ(s)** | **0.889** | **0.951** | **0.981** |
| core HP differential | 0.906 | 0.911 | 0.847 |
| own core HP | 0.878 | 0.854 | 0.845 |
| own unit count | 0.807 | 0.775 | 0.808 |
| cost scale | 0.741 | 0.715 | 0.783 |
| enemy Core located? | 0.599 | 0.593 | 0.503 |
| **titanium stored** | **0.420** | **0.484** | 0.631 |
| **ammo** | **0.339** | **0.263** | **0.395** |

The hand-written Φ beats the *fitted, held-out* logistic model at every horizon. Caveat the turn-40
row: n=42 and it is survivorship-filtered (only games still alive at turn 40 appear, and many are
nearly over). The turn-20 numbers are the honest ones.

### 1.4 The finding that would have broken a hand-designed reward

**Banked titanium and banked ammo predict *losing*.** Ammo at AUC 0.263 at turn 30 is a strong
inverse signal. Stored titanium at turn 10 gets a coefficient of **−1.44** in the fitted model.

The reading is straightforward: resources sitting in the bank are resources you failed to convert
into board presence, and in a 35-turn game there is no time to convert them later. But it means a
hand-written reward of the obvious shape — "reward the agent for having more titanium" — points the
agent in the wrong direction, and it means the user's third candidate potential
(`w1·ΔcoreHP + w2·turretPositions + w3·Δcollected`) is only safe on its first and third terms.

This is precisely why the shaping must be potential-based rather than a bonus. Under Ng/Harada/
Russell the sign of `w_titanium` **cannot change the optimal policy** — a wrong weight costs sample
efficiency and nothing else. Under a naive bonus it changes what the agent optimises. The classic
failure is Randløv & Alstrøm (1998), whose bicycle agent learned to ride in circles to farm a
progress bonus; "hold turret firing positions" is the same shape of bonus and would produce a bot
that camps firing positions instead of shooting the Core.

### 1.5 Applying the theorem properly

Three conditions, all of which this design satisfies:

1. **Φ is a function of state only** — no actions, no events. Every term above is a state quantity.
   This is what makes build-then-destroy telescope to zero automatically: you get `+base_cost` on the
   build and `−base_cost` on the destroy, net zero, with no special-casing.
2. **Φ(terminal) ≡ 0, enforced.** In an episodic task the shaping sum telescopes to
   `γ^T Φ(s_T) − Φ(s_0)`. Forcing `Φ(s_T)=0` leaves `−Φ(s_0)`, a constant per start state. The engine
   is deterministic and the start state is fixed per (map, side), so this is literally a per-map
   constant and cannot reorder policies at all.
3. **Time-dependence is legal.** `Φ(s,t)` with the round number in it is covered by Devlin & Kudenko
   (2012), *dynamic potential-based reward shaping*, which extends the invariance result to
   time-varying potentials. Use it: 300 Ti banked at turn 20 and at turn 900 are not the same state,
   and §1.4 says the sign of that term probably flips with `t`.
4. **Per-unit potentials are legal too.** Devlin & Kudenko (2011) prove that adding PBRS to each
   agent individually in a cooperative game preserves the Nash equilibria. This is the licence to
   hand each unit its *own* dense signal — see §4.

### 1.6 What target to regress V on

Not the win/loss label directly. Use **GAE(λ) on the shaped reward with a centralised critic**, i.e.
the standard MAPPO target. Two properties of this specific engine make high λ unusually attractive:

- **The environment contributes zero variance to a return.** The engine is deterministic (G26); the
  only stochasticity in a rollout is the policy's own sampling. Monte-Carlo returns are therefore
  unbiased *and* low-variance, which is not the normal situation and argues for λ close to 1.
- **Episodes are short.** Median 35 rounds. A 35-step Monte-Carlo return is not a long-horizon credit
  assignment problem at all.

The bootstrap only matters for the 2.4% of games that run to 1000, and for those the tiebreak ladder
already supplies a graded terminal reward: `titanium_collected → harvesters → titanium_stored →
coinflip`. **The game's own tiebreak ladder is a built-in curriculum.** A from-scratch agent that
cannot yet kill a Core is scored on how much it mined, then on how many harvesters it kept alive.
That is exactly the right first lesson, and it comes free in the terminal reward.

---

## 2. AlphaZero-style, or not?

### 2.1 The blocking fact

```
>>> from fcode import fcode_engine as E; print([n for n in dir(E) if not n.startswith('_')])
['run_game']
```

One symbol. `run_game(a_main, b_main, engine_root, map, replay, seed, tle)` plays a **complete game
from turn 0** and returns a summary dict. There is no `step`, no `get_state`, no `clone`, no
`set_state`. I also scanned the compiled extension's string table for `snapshot|clone|state|step|
save|restore|checkpoint|fork` and found nothing beyond `run_game` and an unrelated `err_state`.

**MCTS is therefore impossible, not merely impractical.** Tree search requires the ability to reach a
state, try an action, and undo. This engine offers none of the three.

### 2.2 The determinism workaround, and why it dies on arithmetic

Determinism does buy a theoretical state-restore: a state is uniquely identified by
`(map, seed, policy_A, policy_B)`, so you can reach depth *d* by replaying *d* rounds from turn 0
with both bots reading a recorded action script off disk (file I/O works — §6.1). Cost of one node
expansion at depth 60 is 60 rounds of simulation.

Measured round costs: an empty game (`idle` vs `idle`) is **0.39 ms/round**; a light socket-driven
bot with ~40 units is **~3 ms/round**. So reaching turn 60 costs roughly 25–180 ms *per node*. A
100-simulation search at a single decision point costs 2.5–18 s. A game has **147–275 of our own
unit-decisions when decisive** (measured: duel 147 over 23 turns, fjord 275 over 31 turns) and
**7075 in a 1000-turn game**. Searching every decision point of a single game costs 100–1400 core-
hours. Dead.

### 2.3 The branching factor, for completeness

Even with a step API, vanilla MCTS is meaningless. A Builder Bot's exclusive action set is ~122
discrete choices (4 moves; 4 harvester/barrier/launcher sites; 16 conveyor and 16 splitter
site×facing; 32 gunner and 32 sentinel site×facing; 4 fire; 4 heal; self-destruct; pass), multiplied
by 2⁴ free `destroy` subsets and 16 free store writes. With up to 50 units the joint per-round
branching is ~122⁵⁰ ≈ 10¹⁰⁴. Go's is 10².

### 2.4 The adaptation that *is* right, and is free

The engine executes units **sequentially, in ascending global entity id, across both teams** — I did
not re-derive this; it is `VERIFIED-WIN` in the register from three racing probes (12/12). Crucially,
"resource changes made by one unit are immediately visible to the next unit that acts".

That is not a modelling convenience, it is the literal execution semantics. It means the round is
already a sequence of 50 single-agent decisions, each conditioned on the realised actions of all
lower-id units. So:

- The **multi-agent advantage decomposition lemma** (Kuba et al. 2022, HATRPO/HAPPO) applies
  *exactly* rather than as an approximation. `A(s, u¹⁻ⁿ) = Σᵢ A^i(s, u¹⁻⁽ⁱ⁻¹⁾, uⁱ)` is not a
  factorisation assumption here; it is how the engine actually resolves the round.
- The right policy shape is therefore **autoregressive over units in id order** — the AlphaStar
  action-head trick and the Multi-Agent Transformer (Wen et al. 2022) formulation — with the
  conditioning carried by the thing the engine already gives you: the 16 store slots (u32, team-wide,
  one round of lag) and each unit's own persistent `self`.
- One free consequence worth exploiting whatever else you build: **lower entity ids win every
  contested same-round action for the whole match.** A unit spawned one round earlier permanently
  out-prioritises its counterpart. That is a strategic lever, not a training detail.

**Verdict: no MCTS, no AlphaZero. Take the sequential-id decomposition and use it as the
factorisation for an actor-critic method.** That gives you AlphaZero's policy-iteration structure
(policy improvement driven by a learned value) minus the search operator, which is what the search
was standing in for anyway.

---

## 3. Self-play vs the fixed pool

### 3.1 The trap specific to this engine

**Team A wins 58–60% of identical-bot mirrors** (G27), because Team A's Core holds the lower entity
id and therefore wins every contested same-round action. My own run reproduces the mechanism: `idle`
vs `idle` resolves to `coinflip` → Team A on every map at seed 1.

So **raw self-play win rate is a biased objective by roughly 8–10 percentage points before any
strategy exists.** Any self-play score must be mirrored: play both side assignments of every map and
score antisymmetrically. `arena/score.py::compare` already does exactly this and returns
`S ∈ [−1,+1]`. Use it; do not write a new scorer.

### 3.2 Recommended scheme

**Prioritised fictitious self-play with permanent anchors** — the AlphaStar league (Vinyals et al.
2019) with the exploiter machinery cut, because 15 hand-written rivals *are* the exploiters and they
cost nothing to maintain.

Three populations:

| population | members | sampling weight |
|---|---|---|
| **main** | current agent, self-play | 35% |
| **historical** | frozen checkpoints, one every N updates | 35%, PFSP-weighted `p ∝ (1 − winrate)²` |
| **anchors** | 15 rivals + our own hand bot + `starter_fixed` + `idle` | 30%, PFSP-weighted |

The `(1 − winrate)²` weighting concentrates opponent sampling on bots we *barely* beat, which is the
whole point of PFSP and is what stops the agent forgetting how to beat `frontier` while it chases
`luc1`. `idle` stays in the pool as a floor detector: a candidate that loses to `idle` is broken, not
weak, and you want to find that out in one game rather than at submission.

The anchors also solve the overfitting worry in the cleanest available way: **the promotion gate is
already `0.7·mean(S) + 0.3·min(S)`** across the pool (`arena/zoo.py`). The `min` term means one
catastrophic matchup blocks promotion. Keep that as the *gate* even if you train on a different
weighting, and validate on the 24 generated unseen maps (`tools/unseen.py`), which is the existing
house rule and the only defence against map memorisation.

If you want the principled version rather than the heuristic one: **PSRO / double oracle** (Lanctot
et al. 2017). Maintain the population, compute the empirical payoff matrix, solve for the Nash
meta-distribution over opponents, train a best response to that mixture, add it, repeat. The payoff
matrix for 20 members is 400 cells; at 42 games per cell and the measured throughput below, one full
matrix is ~2.5 core-hours, and `arena/score.py` already caches results keyed on bot source
fingerprint so re-evaluation of unchanged members is free. This is affordable. It is also more
machinery than a hackathon needs — PFSP first, PSRO only if you see cyclic behaviour.

### 3.3 Sizing it — measured throughput

Everything here is measured on this 14-physical-core laptop.

| workload | measurement |
|---|---|
| `idle` vs `idle`, 1000 turns | 0.39 s → **0.39 ms/round** engine floor |
| `starter_fixed` mirror, 1000 turns | 2.2–4.0 s |
| our bot vs `tempest`, decisive (19–38 turns) | **2.1–2.8 s/game** |
| our bot vs `tempest`, 1000 turns (`vault`) | **50.8 s/game** |
| our bot, unit-decisions per game | **147** (duel, 23 turns) / **275** (fjord, 31 turns) / **7075** (vault, 1000 turns) |
| our bot, decision throughput | **~240 unit-decisions/s/core** (both sides) |
| **socket-served policy, 12 maps × 1000 turns** | **418 070 unit-decisions in 36.9 s wall on 12 workers = 944 unit-decisions/s/core** |
| 126-game evaluation sweep (9 opponents × 7 maps × 2 sides) | **137 s wall on 14 cores** |

A neural policy served over a socket is **~4× cheaper per decision** than a game between two
hand-written bots, because our bot spends milliseconds of Python per unit-turn and the network bot
spends microseconds.

Scaling that: **13 200 unit-decisions/s on this laptop; ~60 000/s on a 64-core node** ≈ 5 billion
decisions/day. MAPPO solves SMAC scenarios in 10⁶–10⁷ steps. **Sample budget is not the constraint.**

### 3.4 The awkward part about the H100s

The engine is a CPython extension driving pure-Python bots. The GPU cannot run it. The only GPU work
in the whole pipeline is the forward/backward pass of a network that must fit in ~33 000 MACs
(§5.1) — about 5 µs of a single CPU core under numpy, and utterly invisible on an H100.

Concretely: the recommended architecture puts a **numpy inference process on each rollout worker's
own core**, not on the GPU. Localhost socket round-trip measured at **35 µs**; a 33k-MAC numpy
matmul is ~5 µs; so per-decision inference cost is ~40 µs against a 10 ms budget.

**If you can trade the 3 GPU cards for CPU cores, do it.** If you cannot, run on the GPU nodes'
CPUs — a `gpuh100` node typically carries 32–64 cores — and let the cards idle. Reporting this
honestly now is better than discovering it after writing a distributed trainer.

---

## 4. Credit assignment across 50 units with one shared reward

### 4.1 Ruling things out

**COMA** (Foerster et al. 2018) computes a counterfactual baseline by marginalising one agent's
action out of a centralised Q. With ~122 actions and up to 50 units that is 6100 critic forwards per
timestep. Affordable on paper, but Yu et al. (2021), *The Surprising Effectiveness of PPO in
Cooperative MARL*, showed MAPPO beats COMA on essentially every benchmark. Skip it.

**QMIX / VDN** impose a monotonicity constraint: `∂Q_tot/∂Q_i ≥ 0`. This game violates it constantly.
A builder that walks into a chokepoint and dies to block a rush has negative individual value and
positive team value. A Gunner is worthless without the builder that escorted it and the Core that
converted its ammo. Also QMIX is off-policy Q-learning over a 122-way masked action space — awkward
to implement and slower to converge here than PPO. Skip it.

### 4.2 What to use

**MAPPO with a centralised critic, per-unit potential-based shaping, and the sequential-id
decomposition from §2.4.** Three reasons, in order of weight:

1. **The centralised critic is free in self-play.** We control both clients. Each side's units stream
   their observations to the same policy server, so the server holds the exact joint state of both
   teams with no extra machinery. That is textbook CTDE and it costs nothing here. Against a fixed
   rival you only get our side's view — still fine, the critic just conditions on less.
2. **The sequential execution order makes per-unit advantages exact, not approximate.** Because unit
   *i* genuinely observes the effects of units 1…*i*−1 this round, `A^i` computed from a centralised
   V with lower-id actions already applied is an unbiased per-unit advantage. This is better credit
   assignment than COMA's counterfactual *and* it costs one critic forward per unit-turn instead of
   122.
3. **Per-unit potentials give the dense signal the shared reward cannot.** Devlin & Kudenko (2011)
   licence individual `Φ_i` without touching the equilibria. Concretely I would give each unit:
   - **rusher**: `−0.1 × walk_distance_to_assigned_firing_tile`, plus the shared Core-damage term.
     `siege.plan` already computes the walk distances via BFS, so this is free.
   - **economy builder**: `+1.0 × titanium_collected_attributable`, i.e. stacks that reached the Core
     footprint through belts this unit built. `built_belts` is already tracked per unit.
   - **every unit**: `−(base cost of anything it built that later got destroyed without firing)`.

   Every one of these is a *state* function of the unit's situation, so PBRS applies and none of
   them can distort the optimum.

So the answer to "how does a unit know its action mattered": it does not need to infer it from the
team reward at all. The engine's ordering gives an exact decomposition, and PBRS lets you hand each
unit a bespoke dense signal without paying for it in policy distortion.

---

## 5. RL, or evolutionary search? — the honest comparison

### 5.1 The inference budget, measured

10 ms of CPU per unit per round, on AWS Graviton3 for ranked games. Pure Python; `numpy`, `torch`,
`scipy`, `sklearn` cannot be imported inside the sandbox at all (G28, and `arena/strict.py` blocks
them statically). Measured pure-CPython dense MLP forward passes on this x86 box:

| shape | MACs | ms/forward |
|---|---|---|
| 32→32→16 | 1 536 | 0.059 |
| 64→64→40 | 6 656 | 0.225 |
| 128→128→40 | 21 504 | 0.705 |
| 200→128→64 | 33 792 | **1.105** |
| 256→256→64 | 81 920 | 2.642 |

≈ **31 MMAC/s in pure CPython.** Graviton3 is likely 2–3× slower, so budget ~10–15 MMAC/s there.

Observation encoding is *not* the problem. Measured Controller call costs from inside the sandbox:
`get_nearby_tiles()` 16 µs (65 tiles), `get_nearby_units()` 1 µs, `get_tile_env(pos)` **0.1 µs**,
`get_global_resources()` 0.1 µs. A 220-feature observation built from ~200 per-tile getters costs
~40–60 µs. Negligible.

The binding constraint is the matmul, and the second binding constraint is that **our current bot
already self-caps at 6 ms** (`CPU_BUDGET_US = 6000` in `bot/main.py`). So a network bolted *on top*
of the existing bot has ~3–4 ms of headroom on x86 and less on ARM.

**Design point: ≤ 35 000 MACs**, i.e. roughly `200 → 128 → 40`, ~33k parameters. That is a very small
network. (A parallel seat is probing binary/XNOR nets with base64 weight blobs, which could raise
this ceiling substantially — take their number over mine if it lands.)

### 5.2 (a) RL on a neural policy

**Ceiling: highest. Risk: highest. And the risk is specific and identifiable.**

A 33k-parameter MLP looking at a 69-tile disc cannot express what `bot/main.py` already does:

- **Map-symmetry inference to locate the enemy Core.** The bot refutes symmetry hypotheses against
  accumulated terrain memory and falls back to a farthest-first guess; the comment records the hit
  rate going from 9.5% to 66.7%. That is a *logical deduction over an unbounded history*, not a
  function of a local disc. My own data confirms its value: "enemy Core located?" is the strongest
  single early feature at turn 10 (coefficient +1.54, the largest in the model).
- **BFS pathing and the ranked firing-position solver** in `siege.py`.
- **The store-slot claim protocol** (write your id, read it back next round, lowest id wins).

A per-round feed-forward net of this size will not rediscover any of them, so imitation plateaus
*below* the teacher and RL then has to climb out of a hole it dug itself.

**The fix is to not make the net the whole policy.** Make it a **ranker over the bot's own
candidates.** `siege.plan` already returns ranked firing tiles; the ladder already returns candidate
steps; every `can_*` predicate already filters legality. Replace the `sorted()` calls and the
hand-set thresholds with a learned scorer over the same candidates. This:

- keeps BFS, symmetry inference and pathing, which are unlearnable at this parameter count;
- shrinks the action space from ~122 raw actions to **ranking 10–30 candidates**, which collapses the
  exploration problem;
- makes illegal actions impossible, which matters enormously because an uncaught `GameError`
  **permanently deletes the unit** (G23);
- keeps the network small enough to ship, because scoring 20 candidates with a 40-feature-per-
  candidate scorer of width 64 is 20 × 40 × 64 ≈ 51k MACs — right at budget, and it replaces rather
  than adds to the bot's existing scoring loops.

### 5.3 (b) CMA-ES over the existing bot's constants

**Ceiling: bounded. Risk: lowest. Time to first signal: days.**

The parameter surface: **49 named module-level scalars**, plus ~7–9 genuinely tunable inline magic
numbers, plus 26 more sitting behind `DEFENCE_OVERRIDES`/`ECONOMY_OVERRIDES` which are currently
empty dicts (the posture machinery is fully built and currently a no-op). A realistic starting vector
is **20–25 dimensions**. `_BASE_ROW` (a 13-key dict read through `self._pv()`) is the seam a
parameter vector should be stamped into.

**The honest problem: the fitness landscape is mostly plateaus.** Roughly 45 of the 49 constants
appear as `if x < CONST` integer thresholds, so fitness is piecewise constant in them. Only ~8 are
smooth weights (`siege.STANDOFF_PENALTY`, `siege.EXPOSURE_PENALTY`, and the six posture weights —
and the posture weights currently change nothing because all three posture rows are identical). Plain
CMA-ES will wander the plateaus.

Three fixes, all standard metaheuristics:

1. **CMA-ES *with margin*** (Hamano et al. 2022) — the mixed-integer variant that enforces a minimum
   mutation width per integer coordinate so the sampled population always straddles a threshold
   instead of collapsing inside a plateau. This is exactly the failure mode described above and
   exactly what the method was built for. `pycma` implements it (`integer_variables`).
2. **A graded fitness instead of win/loss.** Keep the win/loss term strictly dominant, then break
   ties continuously:

   ```
   f = mean over (map, side) of
         sign(win)
       + 0.20 · sign(win) · (1 − turns/1000)                  # win faster, lose slower
       + 0.20 · tanh((our_collected − their_collected)/500)   # the actual tiebreak metric
   ```

   Both correction terms are bounded by 0.4 < 1.0, so they can never reorder a win above a loss.
   This is ordinary fitness shaping and it turns the plateau into a slope. It is also the CS454
   answer to the user's question, and the same trick as §1's PBRS in a search-based costume.
3. **Handle the discrete structure separately.** The 6-rung ladder is a permutation (720 orderings)
   and the snipe priority is another (24). Those are not CMA-ES's job — enumerate the interesting
   subset or run a `(1+λ)` EA over them.

**Cost, measured.** A 126-game fitness evaluation is **137 s wall on 14 cores**. A cheaper 56-game
evaluation (4 opponents × 7 maps × 2 sides) is ~61 s. With λ = 4 + 3·ln(25) ≈ 14, one generation is
~14 min locally and ~3 min on 64 cores. **200 generations ≈ 10 hours on one node.** That is a real
optimisation run, not a toy. `arena/score.py`'s fingerprint cache makes re-sampled candidates free.

**And the noise floor is the thing that will bite you.** M01: a change that provably cannot lengthen
any path still moved **7 of 30 games**. The engine is deterministic but the landscape is chaotic at
fine scale. Evaluate on many maps (21 known + 24 unseen, both sides) precisely to average over that
ruggedness, and treat anything under ~5 games as noise.

### 5.4 (c) Genetic programming over policy code

**Do not do this.** Four specific reasons, not general distaste:

1. **1100 of `main.py`'s 3101 lines are comments recording measured experiments.** That measurement
   record is the repository's principal asset. GP discards it on the first mutation.
2. **An uncaught exception permanently deletes the unit** (G23). Random code mutation produces
   exceptions constantly, so almost every mutant is not merely worse but structurally crippled — the
   fitness landscape around any GP individual is a cliff, not a gradient.
3. **The engine's AST validator terminates the process with exit code 10** on `finally:`, bare
   `except:`, non-Name handler types, or non-allowlisted exception names. A large fraction of
   syntactically valid mutants will not even run.
4. **The 10 ms budget** silently truncates a unit's turn, so a slow mutant looks like a *strategic*
   failure rather than a performance one, and you will misattribute it.

The one restricted version worth an hour: a `(1+λ)` EA over the **discrete structure** CMA-ES cannot
touch — the ladder permutation, the snipe priority, the `USE_ATLAS_ORE` boolean. That is a search
space of a few thousand points and you can largely enumerate it.

### 5.5 The thing that dissolves the user's question entirely

Worth stating plainly, because it is the most direct answer available.

**Evolution strategies do not need a loss function at all — the win rate *is* the objective.**
OpenAI-ES (Salimans et al. 2017) estimates a search gradient from episode returns alone: no value
function, no credit assignment, no reward shaping, no trajectory logging, no GAE, no critic. It needs
only "play a game, get a number". The user's entire stage-2 anxiety — *what is the loss, how do we
assign credit, how do we value a state* — is a set of questions **ES never asks**.

The trade is sample efficiency, which scales roughly linearly in parameter dimension. At **25
dimensions** (the bot's constants) ES/CMA-ES is unambiguously the right call. At **33 000 dimensions**
(the shippable net) it is borderline and PPO wins. The threshold sits somewhere in the low thousands.

The strategic consequence: **build the ES loop first regardless of which method wins.** A parameter-
vector-to-bot-directory stamper plus `arena.score.compare` as the objective is the *same harness*
whether the vector is 25 hand-tuned constants or 33k network weights. Nothing is thrown away.

### 5.6 Recommendation

| | verdict |
|---|---|
| **(b) CMA-ES over constants** | **Do this first.** 3 days, uses the existing harness, bounded but certain gain. |
| **(a) RL on a neural policy** | **Only as a candidate *ranker*, and only if (b) plateaus.** Never as a from-scratch policy — it cannot express the symmetry deduction, which is the single most valuable thing the bot does. |
| **(c) GP over code** | **No**, except a tiny EA over the two permutations. |

---

## 6. The minimum viable version

Two experiments. The first is half a day and answers the user's actual question. The second is three
days and is the one that wins games.

### 6.1 The three engine facts that make this cheap (all measured today)

Before the plan, the enabling discoveries, because they change what is buildable:

1. **A bot can write and read files from inside the sub-interpreter.** `open("x","w")` succeeds; cwd
   is the repo root. Every stdlib module I tried imports: `os, sys, json, struct, array, time,
   pickle, socket, pathlib, heapq, math, random, collections`. This is the trajectory-logging channel
   the harness docs say does not exist — they are right that `print()` is swallowed and that
   `resign_message` truncates at 500 chars, but **file I/O works** and it is how I collected 65 346
   state rows across 126 games.
2. **A bot can open a TCP socket to localhost and complete a round trip in 35 µs.** Measured: an
   800-byte request and 40-byte reply, 200 iterations. Against a 10 ms budget this is a rounding
   error. **Training-time inference can therefore live outside the sandbox entirely** — the shipped
   bot is a thin client during training and only needs pure-Python weights at submission. This also
   means the policy server sees every `(obs, action)` from both teams, so the centralised critic and
   the trajectory store are the same object.
3. **A socket-served policy runs ~4× more rollouts per core than our hand-written bot.** 944
   unit-decisions/s/core measured, against ~240 for two hand bots playing each other.

(Housekeeping note: running `arena.zoo.ensure_zoo()` regenerated `bots/zoo/starter_fixed/main.py`
from the current `bots/starter/main.py`. It is a generated file and the regeneration is what the tool
is for, but the committed copy was stale, so it now shows as modified in git.)

### 6.2 MVP-0 — the win-probability probe (half a day)

**Already done, in this document.** §1.2 and §1.3 are MVP-0, executed: 126 games, 137 s, held-out-
opponent AUC 0.845 at turn 20, and a hand-written Φ at AUC 0.889/0.951/0.981.

What remains is to widen it into a reusable artefact:

- log 6–8 more features (own building counts by type, distance from our rusher to the enemy Core
  anchor, number of firing positions held) — all cheap, all already computed inside the bot;
- extend to the full 21-map pool and all 15 rivals (~630 games, ~12 min on this laptop);
- fit both a linear model and a small gradient-boosted tree, and report the AUC gap. If the tree
  beats linear by a lot, the value function is non-linear and a network is worth having. **If it does
  not, ship the linear Φ and skip the network entirely.**

**The decision rule:** held-out AUC at turn 20 above 0.75 means the value function exists and
everything downstream is viable. It is 0.845. **This gate is passed.**

The immediate payoff, independent of any learning: **a calibrated win-probability read-out turns
every future experiment from a 42-game binary count into a continuous measurement.** With M01's noise
floor at 5 games out of 30, that is the difference between "we cannot tell" and "we can tell in an
afternoon".

### 6.3 MVP-1 — CMA-ES on 20 constants with a graded fitness (2–3 days)

The smallest experiment that could actually beat the bot we started from.

**Day 1 — the seam.**
- Promote ~20 constants into `_BASE_ROW` so `self._pv()` reaches them (13 are already there). Pick
  the high-impact cluster: `BUILDERS`, `SIEGE_BUILDERS`, `ATTACKERS`, `CHAIN_RESERVE`,
  `ALARM_RESERVE`, `RUSH_RESERVE`, `RUSH_RESERVE_UNTIL`, `AMMO_TARGET`, `AMMO_FLOOR`, `SNIPE_FLOOR`,
  `BATTERY_RESERVE`, `MAX_BATTERY`, `REPLAN_TILES`, `REPLAN_ROUNDS`, `siege.STANDOFF_PENALTY`,
  `siege.EXPOSURE_PENALTY`, `VAULT_MAX`, `VAULT_MIN_GAP`, `FORTIFY_FROM`, `ALARM_PERCENT`.
- Write `stamp(vector) -> temp_bot_dir`: copy `bot/`, rewrite the parameter table, sweep
  `__pycache__` (a stray one makes the bot silently inert — G30), run `arena.strict --static-only`.
  Reject invalid candidates before they reach a worker; an AST rejection kills the whole worker chunk
  (rc=10).
- Verify round-trip: `stamp(baseline_vector)` must score identically to `bot/`. If it does not, the
  seam is wrong and nothing after this is meaningful.

**Day 2 — the loop.**
- Objective: `arena.score.compare` against 4 opponents (`starter_fixed`, `luc1`, `vanguard`,
  `frontier`) × 7 maps × 2 sides = 56 games, with the graded fitness of §5.3(2).
- `pycma`, `sigma0` = 20% of each parameter's plausible range, `integer_variables` set for every
  integer coordinate (this is the plateau fix, not an optional nicety).
- λ = 14. ~61 s per candidate, ~14 min per generation on 14 cores.

**Day 3 — the verdict.**
- Run 60–100 generations. Then take the incumbent-best and run the **real** gate: `arena.zoo.
  promotion_gate` over the full pool, plus the **24 unseen generated maps**.
- **Success criterion: the tuned bot beats the hand-tuned baseline by more than 5 games on the
  UNSEEN map set.** Five games is the house noise floor (M01) and unseen is the house rule against
  memorisation. Anything less is not a result.

If MVP-1 succeeds, the same harness accepts a network weight vector and you are already in stage 2
proper. If it plateaus after 30 generations, that is itself the answer — the constants are near-
optimal, the remaining headroom is structural, and §5.2's candidate-ranker becomes the next move
rather than a speculative one.

### 6.4 What I would explicitly *not* build first

- A full MAPPO trainer. It is 2–3 weeks and it is gated on MVP-0's answer, which you now have but
  which says the *linear* value function is already excellent — the marginal value of the network is
  unproven.
- Any MCTS. §2 — it is impossible, not hard.
- A distributed GPU pipeline. §3.4 — the cards do not help.
- Behavioural cloning of all 15 rivals. Cloning a bot you already beat 84% of the time buys nothing
  by itself; imitation is only useful as an *initialiser* for the ranker in §5.2, and that is stage 3.

---

## 7. Things that would change this recommendation

- **If the parallel binary/XNOR-net probe finds that a 2048-wide quantised network fits in 10 ms**,
  the inference ceiling moves by two orders of magnitude and §5.2's "a small net cannot express the
  symmetry deduction" gets much weaker. Take their measurement over my 33k-MAC float estimate.
- **If Graviton3 turns out 5× slower than x86 rather than 2–3×**, the ~33k-MAC design point drops to
  ~13k and the ranker becomes marginal. Nothing here has been confirmed on ARM (G44 is open).
- **If the win rate against the real ladder is much lower than 84%**, games get longer, the 1000-turn
  tiebreak stops being a 2.4% edge case, and the shaping story shifts from Core HP toward
  `titanium_collected`. Φ already carries that term, which is why it is in there.
- **If `--tle` enforcement on Linux shows our bot already exceeding budget on some maps** (G45 is
  open, and Windows cannot measure CPU — `get_cpu_time_elapsed()` returns 0 here), then there is *no*
  headroom for a network on top of the bot, and only §5.3's constant tuning remains viable.

## 8. References

- Ng, Harada & Russell (1999), *Policy invariance under reward transformations*. The shaping theorem.
- Randløv & Alstrøm (1998), *Learning to drive a bicycle using RL and shaping*. The failure mode.
- Devlin & Kudenko (2011), *Theoretical considerations of PBRS for multi-agent systems*. Per-unit Φ.
- Devlin & Kudenko (2012), *Dynamic potential-based reward shaping*. Time-varying Φ.
- Foerster et al. (2018), *Counterfactual multi-agent policy gradients* (COMA). Considered, rejected.
- Rashid et al. (2018), *QMIX*. Considered, rejected on the monotonicity constraint.
- Yu et al. (2021), *The surprising effectiveness of PPO in cooperative multi-agent games* (MAPPO).
- Kuba et al. (2022), *Trust region policy optimisation in multi-agent RL* (HAPPO/HATRPO). The
  sequential advantage decomposition that the entity-id ordering makes exact.
- Wen et al. (2022), *Multi-Agent Transformer*. Autoregressive-over-agents policy shape.
- Vinyals et al. (2019), *Grandmaster level in StarCraft II* (AlphaStar). PFSP league.
- Lanctot et al. (2017), *A unified game-theoretic approach to multiagent RL* (PSRO).
- Salimans et al. (2017), *Evolution strategies as a scalable alternative to RL*.
- Hansen & Ostermeier (2001), *Completely derandomised self-adaptation in evolution strategies*
  (CMA-ES).
- Hamano et al. (2022), *CMA-ES with margin*. The mixed-integer variant that fixes plateaus.
