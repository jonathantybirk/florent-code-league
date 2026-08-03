# Stage 1 — imitation learning: design and go/no-go

Committee seat: behaviour cloning. Everything below that is stated as a number was measured
on this machine on 2026-08-03 with `.venv/Scripts/python.exe`, fcode 2.3.3, 14 physical cores.
Artefacts:

| file | what |
|---|---|
| `llm-slop-analysis/elias/nn/replay_decode.py` | full `.replay26` decoder + state reconstruction |
| `llm-slop-analysis/elias/nn/shadow.py` | the logging wrapper (`make_shadow`, `verify`) |

Nothing under `bot/`, `bots/elias/` or `bots/rivals/` was modified. The shadow wrapper
*copies* a bot directory; the original is never touched.

---

## 0. The constraint nobody costed: inference is pure CPython

This dominates every other design choice and was not in the brief.

`numpy` cannot load inside the bot sandbox (G28, `arena/strict.py`). I confirmed it from
inside a real `run_game` sub-interpreter — a probe bot resigned with its findings, the only
string channel that survives (`print()` is swallowed):

```
py=3.13.12  sumprod=yes  array=yes  numpy=no  weights=172032
matvec512x256_ms=0.952  cpu_us=0
```

Three things fall out.

1. **`math.sumprod` exists and is the whole ballgame.** It is a C-level dot product (new in
   3.12) and it is available in the sandbox. Measured on lists of Python floats:
   **88–150 MMAC/s**, versus 34 MMAC/s for `sum(map(mul, a, b))` and 13 MMAC/s for the
   integer/quantised path. **Do not quantise to int** — in CPython, int multiply is *slower*
   than float multiply. And **do not use an NNUE-style sparse accumulator**: the gather loop
   is Python (128 active × 256 dims = 5.6 ms) while a dense `sumprod` of the same size is
   ~1.5 ms. Dense-float-`sumprod` beats every clever alternative because the cleverness is
   interpreted and the density is compiled.

2. **A 10 ms budget buys ~1M MACs; budget ~250k for the net.** Honest end-to-end
   multi-layer figures with He-scaled weights (an earlier run showed 17 MMAC/s purely
   because unscaled weights made activations blow up, which slows `sumprod`):

   | net | MAC | ms | MMAC/s |
   |---|---|---|---|
   | (256, 128, 64) | 41k | 0.26 | 155 |
   | (512, 256, 128, 64) | 172k | 1.65 | 104 |
   | (1024, 256, 128, 64) | 303k | 3.14 | 97 |
   | (1024, 512, 256, 64) | 672k | 7.05 | 95 |

   **No convolutions at inference.** One 3×3×32×32 conv over a 32×32 board is 9.4M MAC ≈ 100 ms.
   Any conv/transformer trunk lives on the H100s as a *teacher* and must be distilled into an
   MLP before it can play.

3. **Weights ship as a file next to `main.py` and load in 2.3 ms.** Verified end to end: a
   672 KB float32 blob was read and unpacked inside the sandbox. Load costs, per
   sub-interpreter, for 172k params: `array.frombytes` 0.46 ms, conversion to Python lists
   2.07 ms, total 2.29 ms. Lists infer at 143 MMAC/s; keeping rows as `array.array('f')` loads
   3× faster but infers 2× slower, so **lists win** — the load is paid once.

   **Memory caveat, unmeasured and load-bearing:** module globals are not shared between
   sub-interpreters, so up to 50 units each hold their own copy. 237k params as Python
   floats is ~9.5 MB per interpreter, ~475 MB across 50 units. As `array.array('f')` it is
   688 KB → ~34 MB. Cap the shipped model at **≤1 MB on disk** and measure resident memory
   before trusting the list-storage plan; the fallback is array rows for the big first layer
   and lists for the rest.

---

## 1. Can we extract (observation, action) pairs at scale? — **GO**

### 1a. The replay format is decoded, and it is a full state trace

`.replay26` is protobuf. The schema is not shipped as a `.proto`; it is embedded as a
protobuf.js JSON descriptor in `fcode/data/visualiser/assets/main-Dsbji_K9.js` (the object
assigned to `yl`, search `nested:{battlecode:`). It is transcribed in
`replay_decode.py`'s docstring and reimplemented there with a hand-rolled wire parser — no
protobuf runtime needed, and none is installed.

```
Replay { Map map = 1; repeated Turn turns = 3; Team winner = 4; }
Turn   { repeated Update updates = 1; }
Update = oneof { 1 PlaceEntity   2 MoveBuilderBot  3 RemoveEntity  4 DistributeResources
                 5 UpdateHp      6 UpdatePlayers   7 SetActionCooldown 8 SetMoveCooldown
                 9 BotOutput    10 IndicatorLine  11 IndicatorDot 12 FireTurret
                13 BuilderAttack 14 CoreConvertAmmo 15 BuilderHeal 16 BuilderBuild }
```

Two properties make it more useful than expected.

* **The update stream is in exact execution order.** Each unit's own updates come
  immediately *before* its own `BotOutput`, and units run in ascending entity-id order,
  interleaved across both teams. So replaying updates one at a time reconstructs the exact
  pre-decision global state for every unit — not merely a start-of-turn snapshot.
  Verified by dumping raw update order:
  `BOTOUT(1) convert(1) hp(1) heal(3) acd(3) BOTOUT(3) move(6) mcd(6) BOTOUT(6) …`
* **`BotOutput` is emitted for every unit that ran**, carrying `{id, stdout, execTimeUs, tled}`.
  That is a free "this unit was alive and got a turn" marker, which is what distinguishes
  *chose to pass* from *was not there*. (`stdout` is empty on this build — consistent with
  `HARNESS.md`: `print()` is swallowed.)

### 1b. …but the replay alone is not sufficient

Audited 8,613 unit-decisions across 9 rival-vs-rival replays, attributing one action to
every `BotOutput`:

```
24.4% builder|move      13.9% launcher|NONE    6.9% core|convert_ammo   0.9% builder|build:gunner
14.3% gunner|fire       13.4% gunner|NONE      6.8% builder|NONE        0.9% builder|build:conveyor
10.5% builder|heal       5.4% core|NONE        1.9% launcher|ACTED-BUT-UNLABELLED
```

Four holes, and they are exactly the holes that matter:

1. **The 16 store slots are absent from the schema entirely.** No update message carries a
   store write. The store is the *only* cross-unit channel and therefore part of every
   unit's observation. A replay-only pipeline cannot see team coordination state at all.
2. **`rotate()` is invisible.** There is no direction-change update. A gunner that rotates
   is silently mislabelled `PASS`. `frontier` is the one bot that re-aims gunners, so this
   is not hypothetical.
3. **`launch()` is unlabelled** — 159 launcher decisions consumed an action cooldown with no
   attributable update (the thrown builder appears as an ordinary `MoveBuilderBot`).
   Recoverable heuristically as "a move of length > 1", but only heuristically.
4. **`destroy()` is unattributable.** It surfaces as `RemoveEntity` on the *building*, never
   on the builder, and it is unmetered so it can co-occur with another action in the same turn.
   `destroy` is indistinguishable from `self_destruct` and from death by damage.

### 1c. The logging wrapper — built, and verified behaviour-identical

`shadow.py` builds a shadow of an arbitrary bot: copy the directory, rename `main.py` to
`_origmain.py` (so sibling imports like `import builder` keep resolving), add `_shadow.py`,
and write a new `main.py` whose `Player` wraps the original and passes it a recording proxy
Controller. The original bot is never edited.

Design points that turned out to be necessary:

* The proxy forwards every call and records only the 19 mutating entry points. Every
  wrapper method returns the real return value unchanged.
* An uncaught exception permanently deletes the unit (G23), so the original exception must
  propagate **unchanged**. `finally` is banned by the engine's AST validator, so the emit is
  duplicated across the `try` and the `except` and the handler ends in a bare `raise`.
* **One log file per worker *process*.** Arena workers are separate processes appending to
  one path and interleaved appends tear lines — measured as a 15-line drift between two
  identical 6-match runs. Per-pid files fixed it: two consecutive 6-match runs now produce
  10,097 lines, 0 torn, byte-identical. Matches within one file split on the round counter
  resetting to 0.
* Optional "fat" mode (`FCL_SHADOW_FAT=1`) also logs the unit's real local observation via
  `get_nearby_tiles()` / `get_nearby_entities()`. Because vision is a raw euclidean disc
  with **no occlusion**, that call set is exactly the observable state — there is nothing to
  reconstruct and no join with the replay to get wrong.

**Verification** — each bot played 6 maps (sprint, duel, fjord, quarry, longship, aurora)
plain and shadowed, seed 1, and the engine's full result dict was diffed
(winner, turns, win_condition, both teams' titanium / collected / units / buildings):

| bot | identical | mismatched maps | decisions logged | wall-clock overhead |
|---|---|---|---|---|
| `bot/` (ours) | yes | 0 | 2,837 | +5.5% |
| vanguard | yes | 0 | 5,436 | +7.1% |
| undertow | yes | 0 | 1,743 | +3.7% |
| frontier | yes | 0 | 10,067 | +13.1% |
| lockin | yes | 0 | 13,836 | +10.6% |
| jonbot | yes | 0 | 3,754 | +8.3% |

All 5 distinct rival codebases plus our own bot, 36 matches, **zero divergence**.

### 1d. Recommendation

**Shadow wrapper is primary; replay is secondary.** Fat-mode shadow gives the exact
observation, the exact action with arguments, and the store — the three things a policy
needs. Keep the replay decoder because it gives the *global* two-team state, which the
shadow (correctly) cannot see and which a centralised critic in stage 2 will want.

---

## 2. State representation

### 2a. Critique of "time step + known work position"

Reject it as the input. Three reasons:

* **`known work position` is an output of the planner, not an observation.** Feeding the
  bot's own chosen goal into the policy that is supposed to choose the goal is circular. At
  deployment, something has to produce that goal. If the answer is "the hand-coded planner
  still produces it", then say so explicitly — that is the hybrid of §5, and it is a
  defensible design, but it must be named rather than smuggled in through a feature.
* **A policy on (t, goal) cannot express the game.** It sees no terrain, no enemies, and no
  legality. It can only reproduce a fixed schedule. Measured: at a 5-tile plus-shaped
  observation the majority-label purity is already only 0.74–0.92; (t, goal) is strictly less.
* **Round number is genuinely useful, but as one feature among ~64.** These bots are strongly
  phase-structured (openings are scripted), so round earns its place — just not alone.

Keep: round, and the goal *if* roles stay hand-coded. Add everything below.

### 2b. Why the "variable-size world" problem does not exist

Maps are 8×8 to 30×30 (`maps/generated/generate_maps.py`: `MIN_SIZE=8`, `MAX_SIZE=30`).
That is at most 900 tiles. Pad every map to a fixed frame with a validity mask and the
variable-size question disappears. The real constraint is not expressiveness, it is the
~250k-MAC inference budget, so the representation must be *small*, not *flexible*.

Vision radii (`GameConstants`), which set the useful crop sizes:
core r²=36 (|d|≤6), sentinel r²=32 (|d|≤5), launcher r²=26 (|d|≤5), builder r²=20 (|d|≤4),
gunner r²=13 (|d|≤3). A 9×9 egocentric window covers builder vision exactly.

### 2c. Exact tensor spec

All float32, concatenated into one flat vector of length **784**.

**Block N — near field, `(5, 18)` = 90.**
Cells: self, N, E, S, W — the entire legality-bearing neighbourhood, because *every*
builder action (move, build, heal, attack, fire, destroy) targets an orthogonal
neighbour or the unit's own tile. Per cell, 18 channels:

| # | channel |
|---|---|
| 0 | in_bounds |
| 1 | is_wall |
| 2 | is_ore |
| 3 | is_tile_passable (engine call, team-aware) |
| 4–12 | entity kind one-hot: builder, core, gunner, sentinel, launcher, conveyor, splitter, harvester, barrier |
| 13 | team sign: +1 ally, −1 enemy, 0 empty |
| 14 | hp / max_hp |
| 15 | facing cos (0 if no facing) |
| 16 | facing sin |
| 17 | has_stored_resource |

**Block M — mid field, `(9, 9, 6)` = 486.**
Egocentric, |dx|,|dy| ≤ 4. Coarse on purpose — it exists to choose a *direction*, not an action.

| # | channel |
|---|---|
| 0 | in_vision (dx²+dy² ≤ my r², in bounds) |
| 1 | is_wall (out-of-bounds counts as wall) |
| 2 | is_ore |
| 3 | ally unit present |
| 4 | ally building present |
| 5 | enemy entity present |

**Block F — far field, `(6, 6, 4)` = 144.**
Whole board in *map frame* (not egocentric), padded to 30×30 and mean-pooled 5×5 → 6×6.
Channels: wall density, ore density, ally entity count/5 (clipped), enemy entity count/5
(clipped). Fed from **team memory**, not this unit's current vision — this is the block that
carries "where is the map" and it is why a memoryless policy is not hopeless.

**Block G — global scalars, 64.**
round/1000 + 8 RBF bumps over round (9) · log1p(Ti)/8, Ti/1000, ammo/500, scale%/300 (4) ·
unit_count/50 + ally builders/gunners/harvesters/conveyors (5) · enemy units seen/20,
enemy turrets seen/10 (2) · own core hp/500, enemy core hp/500, enemy-core-known flag (3) ·
my hp frac, action_cooldown, move_cooldown, can_act (4) · x/W, y/H, W/30, H/30, dx/dy from
own core (6) · (cos, sin, dist) to own core (3) · (cos, sin, dist, known) to believed enemy
core (4) · 8 affordability booleans from the cost getters (8) · **16 store slots, decoded**
(16).

> The store slots go in **decoded**, not raw. Our bot packs positions as `((x+1)<<8)|(y+1)`
> with bit-16 flags; `frontier` packs a lease expiry, a 5×5 coverage bitmask and a symmetry
> mask into single words. Handing a net a u32 and asking it to learn bit-field arithmetic is
> a waste of a 250k-MAC budget. Decode in the feature extractor.

**Total input 90 + 486 + 144 + 64 = 784.**

### 2d. Network and its cost

Trunk `784 → 256 → 128`, ReLU. Autoregressive heads over the factored action, so the
158-way builder action space (4 moves + 2 turret kinds × 4 targets × 8 facings + 2 belt
kinds × 4 × 8 + 3 kinds × 4 + heal×4 + attack×4 + destroy×4 + self_destruct + pass) never
has to be enumerated:

| head | shape | MAC |
|---|---|---|
| verb | 128 → 13 | 1,664 |
| target dir, given verb | 141 → 5 | 705 |
| facing, given verb+target | 146 → 9 | 1,314 |
| value (for stage 2) | 128 → 1 | 128 |

| | MAC |
|---|---|
| 784×256 | 200,704 |
| 256×128 | 32,768 |
| heads | 3,811 |
| **total** | **≈237k → ≈1.7 ms at 140 MMAC/s** |

Leaves ~8 ms for feature extraction and legality masking. **Always mask to legal actions
with the `can_*` predicates before the argmax** — it is free accuracy and it makes an
illegal-action `GameError` (which deletes the unit, G23) structurally impossible.

Weights ≈237k params ≈ 948 KB float32. If the 50-interpreter memory measurement comes back
bad, the fallback is `512 → 192 → 96` (117k MAC, 0.85 ms, 470 KB) by cutting Block M to
9×9×4 and Block F to 4×4×4.

---

## 3. Whose behaviour do we clone? — pool everything, condition on a style token

Measured on 132,323 builder decisions from 6 bots over 126 matches. Key = radius-2
observation + coarse globals; label = verb + target direction; statistics conditional on the
key repeating, because purity on a key seen once is vacuous.

| dataset | n | keys | rep-mass | purity@rep |
|---|---|---|---|---|
| mistral alone | 8,460 | 2,393 | 0.787 | **0.885** |
| jonbot alone | 26,035 | 2,799 | 0.929 | **0.982** |
| mistral + jonbot | 34,495 | 4,998 | 0.899 | 0.958 |
| mistral + jonbot **+ style token** | 34,495 | 5,192 | 0.894 | **0.961** |
| undertow alone | 17,331 | 5,119 | 0.773 | 0.950 |
| vanguard alone | 16,125 | 4,517 | 0.797 | 0.941 |
| undertow + vanguard | 33,456 | 9,163 | 0.803 | 0.941 |
| undertow + vanguard **+ style token** | 33,456 | 9,636 | 0.784 | **0.946** |
| all six pooled | 105,084 | 17,900 | 0.883 | 0.950 |
| all six **+ style token** | 105,084 | 19,652 | 0.866 | **0.963** |

Read that carefully, because it contradicts the premise in the brief.

* **The feared averaging catastrophe does not happen.** mistral and jonbot are the
  pathological pair — byte-identical `builder.py` differing only in
  `ECONOMY_BUILDERS = 0/3` and `SCOUT_BUILDERS = 4/1`. Pooled purity 0.958 versus a
  size-weighted average of the separates of 0.958. They barely collide, because the two
  policies mostly occupy *different regions of observation space* (a zero-economy bot is
  rarely standing next to a harvester chain).
* **The residual conflict is real but ~1 point.** undertow+vanguard drops to 0.941 from a
  weighted average of 0.946. A bot-identity token appended to the key recovers it
  (0.946), and on the full pool the token is worth **+1.3 points** (0.950 → 0.963).
* **Per-bot self-determination is 0.885–0.984.** That is the label-noise floor imposed by
  hidden per-unit memory (role latch, phase, blacklists, route cursor — see §5), and it is
  the number a memoryless net cannot beat.

**Recommendation: train one policy on all bots with a learned per-bot style embedding
(≈8-dim, concatenated into Block G); at deployment freeze the embedding to the strongest
teacher's.** This gets the volume and representation benefit of 6× the data without paying
the averaging cost, and the embedding becomes a free knob in stage 2 — you can search over
it, or interpolate, or let RL fine-tune it. Filtering to winning trajectories only is *not*
recommended as the primary filter: it discards ~50% of data to remove a bias that the style
token already handles, and win/loss is a team-level, 1000-step-delayed label that says
almost nothing about whether an individual builder's move was right.

Do exclude near-clones from the pool (they add rows, not information): keep one of
{tempest, tempest_fast}, one of {mistral, mistral_fast}, one of {lockin, luc1}, and drop the
`*_oracle` variants — they use a bundled map atlas and their behaviour is conditioned on
information a fair bot does not have.

---

## 4. Per-unit or per-team policy? — one shared trunk, but **learn only the builder**

The sub-interpreter argument is right as far as it goes: there is no team-level actor to
place, each unit must decide alone from its own observation, so a single policy conditioned
on unit type is the natural shape. Refuting that is not the interesting part. The
interesting part is that the data says most unit types are not worth a policy at all.

Verb distribution over all six bots, 126 matches:

| unit type | decisions | H(verb) | distribution |
|---|---|---|---|
| **builder_bot** | **132,323** | **1.50 bits** | PASS 50%, move 41%, heal 5%, build_conveyor 1%, fire 1% |
| core | 29,414 | 0.79 bits | PASS 82%, convert_ammo 14%, spawn_builder 3% |
| gunner | 25,873 | 0.97 bits | PASS 60%, fire 40%, rotate 0% |
| launcher | 40,383 | 0.23 bits | PASS 96%, launch 4% |
| **sentinel** | **51** | 0.00 | PASS 100% |

* **Sentinel: 51 decisions in 126 games across six bots.** Nobody builds them (undertow's own
  docstring rejects them at 1.8 dmg/Ti versus a gunner's 5). There is no data and no reason.
  Hand-code, or omit.
* **Gunner: the policy is one line.** `get_gunner_target()` already returns the engine's
  choice; the entire decision is "is it an enemy, and can I afford the shot". Our bot's
  gunner handler is 5 lines and its terminal action count is 1. Learning this is negative value —
  it can only introduce friendly fire, and every turret API is team-blind (G10/G11).
* **Launcher: 96% PASS**, and the 4% that isn't is a geometric search over landing tiles that
  is easier to write than to learn.
* **Core: 2 verbs.** `convert_ammo` is a threshold rule. `spawn_builder` placement is a
  ranking over ≤12 ring tiles — the one core decision with real content, and a plausible
  second small head later.

**Recommendation: a single builder policy, shared trunk, unit-type one-hot retained in
Block G so the architecture generalises later. Ship hand-coded handlers for core, gunner,
sentinel and launcher in v1.** This concentrates the whole 250k-MAC budget on the 58% of
decisions that carry 1.50 bits, and removes four ways to lose a unit to a `GameError`.

---

## 5. The role / coordination problem — **keep roles hand-coded**, this is not a close call

Our bot allocates **all 16 slots** and coordinates through claim protocols with a 1-round
write lag. Concretely: slot 12 `S_RUSHER` and slot 9 `S_RUSHER2` hold `entity_id + 1`;
slot 2 is a spawn-ordinal counter; slots 4–8 are five ore claims; slot 10 packs an enemy-core
anchor plus a `SIGHTED` bit at bit 16; slot 11 packs a 3-bit symmetry-rejection mask *and* a
7-bit archetype-evidence field in one monotone word; slot 14 packs a firing tile plus a
direction index at bit 17. Rivals are no simpler — `frontier` uses expiring 12-round leases
(`1 | x<<1 | y<<6 | expires<<11`) and 5×5 coverage bitmasks.

Three reasons BC cannot learn this, in increasing order of severity.

1. **The encoding is arithmetic, not perception.** A net would have to learn bit-field
   packing before it could learn a policy.
2. **Claim protocols are counterfactual and demonstrations only ever show the winner.**
   Our bot's `_is_rusher` writes its id, *returns False that round*, and reads back next
   round to see whether it won the seat. The demonstration contains "wrote 6, then behaved
   as a rusher". It never contains the branch where another unit got there first, because
   in a deterministic engine that branch never executes. BC has no signal for the arbitration
   rule — only for its outcome.
3. **The role latch is invisible per-unit state.** `self.rush_role` is set once and never
   revisited for ~1000 rounds. Two builders on identical tiles with identical stores take
   opposite actions because one latched a role 400 rounds ago. This is precisely the residual
   1.5–11.5% impurity measured in §3, and it is not reducible by any observation the engine
   offers.

**Recommendation — the hybrid, and it is the practical answer.** Keep the store protocol and
role arbitration exactly as hand-written. Feed the policy the *decoded* consequences as
features: a role one-hot (rusher-1 / rusher-2 / economy / defence), the claimed ore position
as (cos, sin, dist), the enemy-core anchor and its sighted flag, the reserved firing ray, the
alarm and posture bits. The net then learns only within-role behaviour — which move, which
build, which facing — which is exactly the 1.50-bit decision it can actually see.

This also fixes something the imitator would otherwise inherit: the role protocol has known
bugs (nothing is reclaimed on death, so a dead rusher's seat is never refilled; claim slots
alias at `ordinal % 5` once the alarm raises the builder cap to 10; `_near_home` reads slots
0/1 without removing the +1 bias). Those are fixable in Python in an afternoon and are
invisible to a cloning objective, which would faithfully reproduce the bugs.

---

## 6. How much data, and how fast can we make it? — data is not the constraint

Measured with both sides shadowed, so one match yields two teams' demonstrations.

| | slim mode | fat mode (full observation) |
|---|---|---|
| matches | 63 | 126 |
| workers | 14 (physical cores) | 14 |
| wall | 112.3 s | 149.9 s |
| **matches/hour** | **2,020** | **3,027** |
| mean turns/match | 96.6 | 116.7 |
| decisions/match (both teams) | 1,343 | 1,810 |
| **decisions/hour** | 2.71M | **5.48M** |
| bytes/decision | 245 | 849 |
| crashed / torn lines | 0 / 0 | 0 / 0 |

Builder decisions are 58% of the total → **3.2M builder (obs, action) pairs per hour on 14
cores**, ≈230k per core-hour. A 3×H100 box will have 32–96 CPU cores; at 64 cores that is
**~15M builder pairs/hour**, and the GPUs will be idle waiting.

Sizing: a ~237k-parameter policy over a 27-way factored action space with a measured label
ceiling of ~0.95 needs on the order of **5–20M pairs** before it is data-limited rather than
capacity-limited. That is **2–7 core-hours per million**, i.e. a few hours of one machine for
the whole corpus. Storage at 849 B/decision is 665 MB/hour of JSONL, which should be packed
to a fixed-width binary record on write (the 784-float vector is 3.1 KB dense, but as
`(tiles, ents)` sparse lists it is the 849 B measured — keep the sparse form on disk and
densify in the dataloader).

Coverage matters more than volume. Generate on **all 21 published + 24 generated maps**, all
6 style families, both seatings (team A and team B — team A wins ~58–60% of identical-bot
mirrors, G27, so an unmirrored corpus is biased), and include some matchups that go the
distance: mean turns is only 96.6 because strong-versus-strong games end in a gunner rush by
turn 20–60, so late-game states are rare and must be deliberately oversampled.

**Verdict: data volume is a non-issue.** The binding constraints are the ~0.95 label ceiling
and the 250k-MAC inference budget.

---

## 7. Evaluation of the imitator — the gate

Behavioural-cloning accuracy is the wrong headline metric, and here is the specific reason,
not the general one: **50% of builder decisions are PASS.** A policy that always passes
scores 50% top-1 and loses every game. Report accuracy, never gate on it.

### Gate — all six must pass, in order (cheap first)

1. **Static.** `python -m arena.strict <bot>` passes: AST validator clean, no `__pycache__`
   (G30 makes a bot silently inert), no BOM, no stray `.py`, no banned imports.
2. **No self-inflicted deaths.** Across the 30-game mirrored sweep, **zero** of our units
   deleted by an uncaught exception (G23). The legality mask should make this structural;
   if it is non-zero the mask is wrong.
3. **Time.** p99 per-unit execution < 8 ms and p100 < 10 ms, measured **on Linux**.
   ⚠ This cannot be measured here: `get_cpu_time_elapsed()` returns 0 on Windows and `--tle`
   is never enforced (confirmed by the sandbox probe, `cpu_us=0`). Note also that the bundled
   visualiser's fallback TLE threshold is **2 ms**, not 10 (`tled = execTimeUs > 2e3`) —
   either the visualiser is stale or the effective budget is tighter than the brief assumes.
   **Resolve this before sizing the network up.** Also measure resident memory with 50 live
   units.
4. **Determinism.** Same match twice, bit-identical result. A fresh sub-interpreter seeds
   `random` from `os.urandom`, so any unseeded randomness makes every sweep untrustworthy.
   The net must be argmax or seeded-sampling, never unseeded.
5. **Fidelity — the real imitation gate.** Against the teacher it cloned, mirrored,
   21 published + 24 generated maps: **win rate ≥ 45%**. Imitation has succeeded when the
   clone is a near-peer of its teacher, not when it matches its actions. Secondary read:
   its win rate against the *field* (the zoo + 5 rival families) must be within **5 points**
   of the teacher's against the same field. A clone that beats its teacher but collapses
   against everything else has overfitted to one matchup.
6. **Generalisation.** The published-map and generated-map win rates must not differ by more
   than **8 points**. `maps/generated` is the proxy for the unseen competition pool, and a
   large gap means the policy memorised geometry.

### Diagnostics to report alongside (not gates)

* Top-1 accuracy split by verb, on a **held-out map-geometry** split — because the
  interesting failure is that the model gets `move` right and `build_gunner` wrong, and a
  pooled number hides it.
* Accuracy conditional on the action *not* being PASS. This is the number that actually
  correlates with play strength.
* Per-role accuracy (rusher-1 / rusher-2 / economy). If economy is fine and rush is not,
  the fault is the route cursor, i.e. missing memory, not missing capacity.
* Turn-of-death distribution versus the teacher's. Compounding BC error shows up as games
  that diverge from the teacher's trajectory at a characteristic round; that round tells you
  where to point DAgger or stage-2 RL.

### Expected outcome, stated in advance

With a memoryless policy and a measured per-bot label ceiling of 0.885–0.984, expect ~0.90
top-1 on non-PASS builder actions and a clone that reaches roughly 30–45% mirrored against
its teacher. That is a **successful stage 1** — BC's compounding error over ~1000 sequential
decisions per unit means a 10% per-decision error rate will not reproduce the teacher, and
closing that gap is exactly what stage 2 is for. If stage 1 clears gates 1–4 and 6 and lands
at ≥30% against its teacher, proceed; if it clears gate 5 at ≥45%, that is better than the
literature would predict and the representation is doing more work than expected.

---

## Summary of go/no-go

| # | question | verdict |
|---|---|---|
| 1 | extract (obs, action) at scale | **GO** — shadow wrapper, verified identical on 6 bot families × 6 maps, 4–18% overhead; replay decoded but insufficient alone (no store, no rotate, no destroy attribution) |
| 2 | state representation | **GO** — 784-float input, 90/486/144/64 blocks, `784→256→128` + factored heads, ≈237k MAC ≈1.7 ms |
| 3 | whose behaviour | **GO** — pool all, per-bot style embedding (+1.3 pts purity), deploy the best teacher's token; style conflict measured at ~1 pt, not catastrophic |
| 4 | per-unit or per-team | **GO with a scope cut** — learn the builder only; core/gunner/sentinel/launcher stay hand-coded on measured decision-content grounds (sentinel: 51 decisions in 126 games) |
| 5 | role coordination | **NO-GO on learning it** — keep the store protocol hand-coded, feed decoded role features; claim arbitration is counterfactual and BC never sees the losing branch |
| 6 | data volume | **GO** — 3.2M builder pairs/hour on 14 cores; ~2–7 core-hours per million; not the constraint |
| 7 | evaluation | **GO** — 6-part gate, headline is ≥45% mirrored vs the teacher on 45 maps; ⚠ the CPU-time gate cannot be measured on Windows and must be run on Linux first |

**One open risk that blocks sizing:** the real per-unit CPU budget. The brief says 10 ms,
the bundled visualiser assumes 2 ms, and this machine cannot measure either. Every number in
§0 and §2d scales linearly with that budget.
