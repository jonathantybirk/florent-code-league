# Design — Verification-First Development and the Offensive Thesis

## Context

Three independent sources of truth exist for this game, and they disagree:

1. The **official docs** at `game.code.florent.vc` (scraped into `docs/scraped-originals/`).
2. The **repo's corrections** — `docs/**/*.md` carries "Correction vs. the official docs" blocks written by
   the repo author after probing the real engine.
3. **The engine itself**, which has now contradicted *both* on at least four points.

The correct epistemic stance is that **only source 3 counts**, and only when measured on the platform the
ladder actually runs. Everything else is a hypothesis.

## Decision 1: A three-tier claim status, and a hard gate

Every engine claim carries a status:

| Status | Meaning | May influence bot logic? |
|---|---|---|
| `ASSERTED` | Someone wrote it down. Docs, a teammate, or an agent report. | **No** |
| `VERIFIED-WIN` | Reproduced by our own probe on Windows/x86. | Only behind a runtime feature flag |
| `VERIFIED-LINUX` | Reproduced on Linux, ideally confirmed via `fcode match test` on Graviton3. | Yes |

The gate is deliberately harsh because the cost asymmetry is extreme: a wrong belief about, say, whether
Builder Bots can deal damage sends a person down a week-long dead end, and we have three weeks.

**Rationale for the platform split.** Two findings measured on the Windows wheel are suspicious enough to
justify the whole tier system:

- `ct.get_cpu_time_elapsed()` returns `0` on Windows even after 10⁸ operations, and `--tle` is never
  enforced. On WSL the same probe returned `cpu_us=26510` and the TLE fired correctly. This is
  unambiguously a platform difference, which proves platform differences exist in this engine.
- Builder Bots reportedly deal **zero** damage — `can_fire()` false and `fire()` raising against an adjacent
  enemy Core, Barrier and Harvester — flatly contradicting the docs' "2 damage for 2 Ti". If this is a
  Windows regression, the entire sabotage/raid strategy space reopens. If it is a real rule, that space does
  not exist. We cannot afford to guess which.

## Decision 2: Offence is the default hypothesis, not economy

The evidence currently points somewhere counterintuitive, and we should follow it rather than the field.

**The economic case for economy is real but bounded.** `titanium_collected` — the round-1000 tiebreak — counts
only titanium mined and physically delivered into the Core by conveyor. Bank and passive income contribute
nothing; a do-nothing bot finishes with 3000 Ti banked and **0 collected**. One connected harvester yields
≈2470 over a match, so one harvester ≈ an entire match of passive income. Economy is cheap and compounding,
and we should always take it.

**But the kill is cheaper.** Measured end-to-end in a purpose-built arena:

| Setup | Core destroyed | Ammo spent | Conveyors needed |
|---|---|---|---|
| 1 Gunner + 1 adjacent Harvester | **turn 77** | 100 Ti | **0** |
| 1 Sentinel + 1 adjacent Harvester | turn 145 | 280 Ti | 0 |
| 4 Builder Bots adjacent to the Core | **never** | 0 | — |

Total capital for the Gunner kill at 160% scale: builder 48 + harvester 32 + gunner 16 = **96 Ti**, about 3%
of a match's income. And the logistics objection largely dissolves: reportedly **13 of 15 maps have a Gunner
firing position with an ore tile orthogonally adjacent**, so the harvester feeds the gunner directly with no
conveyor chain at all. *(This 13/15 claim is `ASSERTED` and is one of the highest-priority verifications in
this change — the whole doctrine rests on it.)*

**Why the earlier "defence wins" conclusion was wrong.** It compared healing (0.25 Ti per HP) against
*Builder Bot chip damage* (1.00 Ti per damage) and concluded defence out-trades offence 4:1. That comparison
is against the wrong attacker. The real attacker is a Gunner:

| | Ti per damage | Damage per round |
|---|---|---|
| Gunner ammo | **0.20** | **10** |
| Sentinel ammo | 0.56 | 4.5 |
| Builder Bot heal (defence) | 0.25 per HP | 4 HP |

A Gunner out-trades healing on titanium **and** out-paces it 2.5:1 on throughput. Neutralising one Gunner
requires roughly **2.5 Builder Bots healing full time**, each costing +20 percentage points of global cost
scale, forever. Defence loses the exchange.

**The honest counter-argument, which we must test rather than dismiss:** every measured Core kill was against
a *passive* opponent. Nobody has yet tested a forward gunner against a defender that (a) heals, (b) has its
own gunner covering the approach, and (c) destroys the attacking harvester — which is 30 HP and the single
point of failure for the whole attack. The doctrine is not adopted until it survives that.

## Decision 3: Defensive dogmas are guilty until proven innocent

Each of the following is a belief a reasonable person would hold, and each is at best unproven. They are
enumerated here so the team argues with the arithmetic rather than the vibe.

**Dogma 1 — "Barriers protect the Core."** Barrier is 30 HP for 3 Ti = 10 HP/Ti, genuinely the best armour
per titanium in the game. But: a Gunner chews one in 3 rounds for 6 Ti of ammo, so a 12-tile ring (36 Ti,
+12 scale points) buys about three rounds per lane. **Sentinels ignore walls entirely**, so a barrier ring is
no defence at all against the one weapon that outranges everything. And barriers block line of sight — which
means they block *your own* turret rays, and can wall in your own Core's 12-tile spawn ring. Verdict:
situational anti-builder tool, not a defence. **Attack this.**

**Dogma 2 — "Turtle and win the round-1000 tiebreak."** The tiebreak counts *delivered* titanium only.
Turtling without connected harvesters delivers zero and loses the tiebreak to any opponent with a single
working chain. Turtling is not an economic strategy; it is the absence of one. **This dogma is already dead.**

**Dogma 3 — "Heal-tank the attack."** Refuted by the exchange rates above. Worse, healing requires a Builder
Bot standing orthogonally adjacent to the damaged entity every round, which puts it in the attacker's
firing line, where it dies in 4 rounds. **Attack this.**

**Dogma 4 — "Defensive gunners near the Core."** This is what the starter bot does and it is broken twice
over. Its gunners are never fed, so they cannot fire. And if they *were* fed, turrets reportedly have **no
friend/foe check** — a Gunner will target and kill its own team's Builder Bots and buildings, and a friendly
building in the ray blocks it permanently. A home-defence gunner sits exactly where your own builders walk
past it all game. **Verify the friend/foe claim first; if true this is the highest-value bug in the field.**

**Dogma 5 — "More Builder Bots is safer."** Each costs +20 percentage points of *global* cost scale,
permanently, across all entity types. Eight builders cost 408 Ti cumulative and put you at 260% scale, making
every subsequent gunner and harvester 2.6× more expensive. And if Builder Bots really deal zero damage, they
cannot defend anything at all. A full economy simulation across all 15 maps put the optimum near 3–4, with
5 costing 40 scale points for 0.15% more mined titanium. **Attack the starter's `MAX_BUILDERS = 5`.**

**Dogma 6 — "We must scout to find the enemy."** Maps come from a *published, fixed pool of 15* that ships in
`maps/`. Map identity is likely determined at round 0 from `(width, height, own_core_position, team)`. But
the naive corollary is a trap: **6 of 15 maps are not 180°-rotationally symmetric** — `pinch`/`strait`/`twins`
are vertical mirrors, `longship`/`runestone` horizontal, `atoll` diagonal — so mirroring your Core through
the map centre finds the enemy Core **wrong 40% of the time**. Precompute per map; never compute at runtime.

**Dogma 7 — "The 16 comm slots are our bottleneck."** They are not. Per-unit `self` state persists across all
1000 rounds, so every unit can carry a full private map model for free. The real bottleneck is **vision** —
`ct.get_tile_env(pos)` raises for tiles outside vision, so no unit can scan the map. Spend the 16 slots only
on *dynamic* facts (enemy core position, rally point, phase, role counter), never on terrain.

## Decision 4: The harness is the arbiter, not the ladder

The engine is deterministic. With a `random`-free bot, results are bit-identical across runs, and identical
across `--seed` values — `--seed` observably controls only the coinflip tiebreak. Measured: **100% of outcome
variance is between-map; 0% is within-map across seeds.**

Consequences that invert normal practice:

- **Replicates are waste.** Never run the same (bots, map, side) twice.
- **15 maps × 2 sides = 30 games is exhaustive**, not a sample, and costs ~10 seconds. Our local estimate is
  *more precise* than the ladder's own best-of-five.
- **Mirroring is mandatory.** Team A wins ~58–60% of identical-bot-vs-itself games because its Core acts
  first. An unpaired comparison of two bots reported one ahead by +1024 Ti when the paired score was −106 —
  the unpaired estimate was almost entirely side bias, with the sign wrong. Score antisymmetrically:
  `S(X,Y) = ½[s(X as A, Y as B) − s(Y as A, X as B)]`.
- **Hold out 3 maps.** The pool "may be updated between rounds", so a bot tuned to 15 known maps is overfit
  by construction.

Build on the in-process API, not the CLI: `fcode.fcode_engine.run_game(...)` returns a result dict directly,
at roughly 800 matches/hour/core. Note that `ProcessPoolExecutor` with fork dies on sub-interpreter
finalisation — use one-shot subprocess workers ending in `os._exit(0)`.

**CPU is a first-class fitness term, not an afterthought.** A cheap bot runs ~800 matches/hour/core; a bot
that maxes its 10 ms budget across 50 units runs ~4. That is a 200× throughput collapse and it decides
whether any search-based approach is viable at all.

## Decision 5: Deliberately out of scope

- **No neural network in shippable code.** numpy cannot be imported in the bot sandbox at all — it is a
  single-phase-init C extension and the engine's trial sub-interpreter consumes the only slot
  (`ImportError: cannot load module more than once per process`). This is a hard blocker independent of the
  separate argument that neuroevolution is sample-starved here. The `x/llm-RL` branch must be assessed
  against this constraint specifically.
- **No shared-memory architecture.** Module-level globals are not shared between units; each runs in its own
  CPython sub-interpreter. Confirmed independently twice.
- **No genetic programming over raw Python source.** An uncaught exception permanently deletes a unit, and
  the AST validator rejects `finally:` and bare `except:`. If GP is used at all it must be over a
  total-function DSL producing a scoring expression, never control flow.
- **Nothing that touches the platform adversarially.** No multiple accounts, no collusion, no sandbox
  escape, no rate-limit evasion. If an engine defect is found that crashes opponents, we report it rather
  than weaponise it.

## Open questions this change is designed to answer

1. Do Builder Bots deal damage on Linux? *(Decides whether raiding/sabotage exists at all.)*
2. Do turrets really lack friend/foe checks? *(Decides whether the field is killing its own units.)*
3. Is the "13/15 maps have ore adjacent to a gunner firing spot" claim true? *(The doctrine rests on it.)*
4. Does the forward-gunner rush survive a competent defender?
5. Does turret ammo really only refill at exactly 0? *(Inverts fire-discipline policy.)*
6. Do harvesters block movement, contradicting the reference table? *(Decides whether auto-build can wall
   itself in.)*
7. Is the entry point `main.py` or `bot.py`? *(Decides whether we can submit at all.)*
