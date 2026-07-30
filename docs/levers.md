# Lever Board — ranked by expected needle movement

> ## RESULTS (measured, mirrored 30-game sweeps)
>
> | Opponent | Session start | Now | Core kills |
> |---|---|---|---|
> | `idle` | — | **30–0** | 30/30 |
> | `starter_fixed` | 21–9 | **23–7** | 4 |
> | `frontier` | 3–27 | **18–12** | 10 |
> | `lockin` | 0–30 | **6–24** | 6 |
> | `luc1` | 1–29 | **8–22** | 7 |
> | **total vs the four real bots** | **25–95** | **55–65** | |
>
> Shipped config: `BUILDERS = 6`, `USE_ATLAS_ORE = False`, BFS navigation, chain repair,
> rush enabled on all 15 maps.
>
> **What actually moved the needle, in order:**
> 1. **Builder navigation** (one dead-code branch) — the dominant term, and it was on nobody's list.
> 2. **Rush route execution + firing-lane reservation** — 13/30 → 30/30 rush conversion.
> 3. **Builder count 4 → 6** — only became profitable *after* nav; the curve was flat before.
> 4. **Chain repair** — +1 vs luc1.
>
> **What was ranked high and measured worthless:** barrier denial (S1, my #1 pick), launcher relay,
> magazine discipline, atlas ore-seeding, chain-length ore ranking, parallel-chain joining.
> Six of my top picks were wrong; the winner was a bug nobody had ranked at all. Rank cheaply,
> measure before believing.


Benchmark throughout: **games moved out of 30 against `luc1`**, the strongest bot on the team.
Current baseline: **3–27**, with our Core destroyed in ~20 of 30. Against `starter_fixed` we are 18–12.

`MEASURED` = we have a number. `ESTIMATED` = reasoned from verified mechanics. `SPECULATIVE` = untested idea.

---

## Tier S — could each move 6+ games

### S1. Barrier / occupancy denial of enemy firing positions · `ESTIMATED +8 to +14`
They kill our Core in 20 of 30 games. `rushplan.deny_tiles()` already returns the threat-ranked tiles an
enemy Gunner can bear on our Core from, pre-filtered against our own spawn ring. A Barrier is **3 Ti for
30 HP and blocks line of sight**. Denying even half their viable firing positions should convert a large
share of those 20 losses into 1000-round economy games, which we can then win on the tiebreak.

**Improvement over anyone else:** nobody on the team denies proactively. `cc3` has a barrier ring, but it is
undirected (and ships with a unit-deleting crash). Ours is aimed at *computed* firing geometry.

**Variant worth testing:** occupy the tile with a **conveyor** instead of a barrier — a friendly building in
a turret's ray jams it permanently, and a conveyor also earns. Same 3 Ti.

**Hard constraint:** never seal our own Core's 12-tile spawn ring — that loses outright.

### S2. Recover the six maps where the rush silently fails · `MEASURED, 12 games in play`
The rush converts on 9 of 15 maps (kill turns 66–101). On `atoll`, `fjord`, `pinch`, `quarry`, `runestone`,
`vault` the geometry is valid but the game runs to 1000. Worse, several end with almost no buildings
(atoll 4, quarry 2, vault 4 versus a normal 20–30), so the rusher appears to be **wedging our own economy**,
not merely failing. Fixing this is worth up to 12 games *and* removes an economy regression.

### S3. Chain integrity — detect and repair cut belts · `ESTIMATED +4 to +8`
A chain missing one link delivers **exactly zero**. Enemy builders can cut a 20 HP conveyor in 10 rounds
for 20 Ti using the range-0 attack, and Lucas's bot already does sabotage. We currently never notice a
broken chain. Detection is cheap: a harvester whose stack has not moved, or a known belt tile now empty.

---

## Tier A — 3 to 6 games each

### A1. Turret jamming as an offensive weapon · `SPECULATIVE, potentially top of the board`
**Nobody in this competition knows this exists.** Verified: a friendly entity in a turret's ray blocks it
*indefinitely* (373 consecutive rounds observed), and the turret then targets that friendly. Also verified:
a gunner ground its **own Core** 500→0 and lost the match.

So a 3 Ti conveyor placed in an enemy gunner's lane may both neutralise the gunner *and* turn it into a
weapon against its owner's buildings. If it works, that is the best titanium exchange rate in the game.
Being measured now.

### A2. Rank ore by chain length, not distance · `ESTIMATED +3 to +6`
We lose to the starter by a deficit of *exactly one harvester*, repeatedly. `_pick_ore` currently picks the
ore nearest the **builder**; value actually depends on how soon the chain starts delivering (~2.5 collected
per round of delay) and how many belt tiles it needs. Ranking by BFS path length to the Core should also
un-break atlas seeding, which measured worse (17–13 vs 20–10) precisely because it made builders claim
globally-nearest ore and walk past each other.

### A3. Launcher relay for the rusher · `ESTIMATED +2 to +5`
20 Ti, no ammo, throws a builder ~5 tiles in one action versus 1 tile/round walking. Earlier gunner = earlier
kill = we win more races outright. May also convert some of the six failing rush maps. Lucas uses relays;
we do not. **Our improvement:** precompute relay positions offline per map instead of deciding at runtime.

### A4. Steal their supply chain — with foreknowledge · `ESTIMATED +2 to +4`
Lucas's cleverest trick: trace the enemy belt, replace its final conveyor with your own gunner, so *their*
harvester feeds *your* siege. **Our improvement:** with the atlas we know where their belt will run *before
they build it*, because their ore and Core positions are known at round 0. His version requires scouting and
blanks against an opponent who builds nothing — ours can pre-position.

---

## Tier B — 1 to 3 games each

- **B1. Magazine-dump fire discipline.** If a turret only refills at exactly 0, holding fire is actively
  harmful. Being measured.
- **B2. Scale-factor discipline.** `destroy()` refunds the scale contribution (though **not** titanium —
  verified). Self-destructing idle builders after the economy saturates reclaims 20 points each. Also:
  buy gunners *before* a big conveyor build-out, since each belt tile is +1 point on everything.
- **B3. Anti-rush timing.** We know exactly when their gunner can land (turns 66–101 by map). Pre-empt.
- **B4. Spawn-ring protection.** Never let any building — ours or theirs — seal our Core's 12 spawn tiles.
- **B5. Heal only what wins the exchange.** Healing is 0.25 Ti/HP against a Gunner's 0.20 Ti/damage at 10
  damage per round; healing a Core under gunner fire *loses*. Kill the feeding harvester (30 HP) instead.

---

## Tier C — techniques from prior art that nobody in this competition has used

Sourced from winners of Battlecode, Screeps, Terminal, Halite, Lux, Russian AI Cup, CodinGame and Ants.

- **C1. Min-cut barrier placement** (Screeps). Max-flow between our Core and the map edges yields the
  *minimal* wall set, landing automatically on terrain chokepoints. Computable offline per map. Strictly
  better than hand-picking barrier tiles, and a natural upgrade to S1.
- **C2. One shared value function** (teccles, Halite III winner). Score every candidate action with a single
  expression instead of a priority ladder; fold new mechanics in as coefficients. This is also the *only*
  representation that makes later genetic programming tractable — evolve the formula, not control flow.
- **C3. BFS from the resource outward** (xathis, Ants winner). Flood from each ore until the first free
  builder is found: nearest-wins claim assignment, globally consistent, **zero communication**. Replaces our
  store-slot claims and frees slots.
- **C4. Breach-coordinate reactive defence** (Terminal, 3rd global). Log exactly where we took damage, and
  fortify precisely there next game — a per-map learned threat table.
- **C5. Attack-sync** (Battlecode 2025 winner). Attackers enter turret range only on even turns, so a
  one-shot-per-round defender can hit at most one of them.
- **C6. Event-sourced danger map** (Battlecode 2020 winner). Broadcast turret *created/destroyed events*
  rather than state; each unit maintains its own danger grid. Fits our 16-slot budget where a full map
  never would.
- **C7. Deterministic identical global recompute.** Because the engine is deterministic and the map pool is
  known, every unit can independently recompute the *same* global plan from atlas + store snapshot,
  bypassing the 16-slot comms limit for all coordination. No researched competition could do this — their
  engines were stochastic or their maps procedural. **This is our single most unusual structural advantage.**

---

## Tier P — process levers (compounding, not per-game)

- **P1. The version ladder.** Every winner of every competition researched did this and nothing else
  correlated as strongly. We have it (`arena/`, `tools/quickmatch.py`); the rest of the team does not.
  Until this week nobody had measured jon-vs-luc even once.
- **P2. The crash and validator gate.** Already caught two would-be ladder-killers (a `__pycache__` that
  makes the bot silently inert; the `main.py` path convention).
- **P3. The rival CPU audit.** If `luc1` really exceeds 10 ms on atoll, it will lose actions on the ladder
  and never on his Windows box. Robustness may decide the internal bake-off regardless of strategy.
- **P4. Ground-truth register discipline.** 33 verified claims; six repo doc errors found so far, including
  two inside the repo's own "corrections". Every hour here has paid for itself.

---

## Explicitly NOT worth doing

- **Neural network / RL policy.** numpy cannot load in the sandbox at all; prior art scoreboard is rules 4,
  RL 2, and the Halite IV winner was an RL professional who shipped rules.
- **Genetic programming over raw Python source.** An uncaught exception permanently deletes the unit, and
  the AST validator bans `finally:` and bare `except:`. Only a total-function DSL scoring expression (C2)
  is viable, and only once there is a value function to evolve.
- **Deep in-turn search.** 10 ms of Python per unit buys a full-map BFS (~270 µs), not rollouts.
- **Runtime map discovery.** The pool is known; every subsystem Battlecode teams were forced to build for
  this can simply be deleted.
