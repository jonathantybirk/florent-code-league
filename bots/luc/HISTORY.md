# How we got here — the full history of the competition work

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

Written 2026-08-04, synthesized from every archived AI-assistant session about this competition:
19 Claude Code sessions across three project checkouts (2026-07-24 → 2026-08-04), 20 Codex CLI
sessions (2026-07-25 → 2026-08-02), plus `bots/luc/NOTES.md`, all 129 commits on `x/luc`, and the
persistent memory files. The eleven per-chunk digests with full per-session detail live in
`bots/luc/history/digest-*.md`; this file is the synthesis. It exists to answer two questions for
any future session: *what do we actually know*, and *how sure are we* — which conclusions were
confirmed independently, and which were confidently stated and later disproved.

The single most important pattern in the whole record: **almost every big gain came from
re-examining something already "settled", and almost every big waste came from trusting it.**
The reversals ledger below is not a list of embarrassments; it is the working map of where the
next gains probably are.

---

## The eras at a glance

| Era | Dates | Where | What happened |
|---|---|---|---|
| 1. Learning the game | Jul 24–27 | `~/projects/florent`, then `florent-code-league` | Engine probed, docs corrected, `.map26` decoded, atlas built |
| 2. First bots & the arms race | Jul 28 | `florent-code-league` | `bots/1`, Jon's `lockin` crisis, TLE cliff #1, first round robin |
| 3. The RL detour | Jul 28–29 | `florent-code-league-llm-rl` (its namesake) | PPO self-play: 0 wins in 17,792 matches, killed |
| — gap — | Jul 29–31 | | One commit ("Simplify main") |
| 4. Infrastructure day | Aug 1 | `llm-rl` + Codex in parallel | Tournament harness, DTU HPC, compliance, website, live CI evaluator |
| 5. The meta cracks open | Aug 2 | `llm-rl` | Ammo-floor +26pp, map clustering, regression benchmark, `ragnarok` |
| 6. Replay intelligence & the lineage sprint | Aug 3 | `llm-rl` | Pantheon decoded, valkyrie→…→bastion, Launcher scale discipline, Nash pillar |
| 7. heimdall & the great re-sweep | Aug 3 night–Aug 4 | `llm-rl` | Fair atlas-free bot 0.702 → 0.905 pool / 0.838 unknown maps |

---

## Era chronicles

### 1. Jul 24–27 — learning the game (digests A, D)

Day zero. No competitive bots, no harness — the work was establishing what the game *actually is*,
and the founding discovery was that **the official docs are wrong in load-bearing places**. The
documented team-wide ammo pool (`ct.convert_ammo`) does not exist in the engine: ammo is titanium
stored per-turret, delivered by conveyors (Gunner shot = 2, Sentinel = 10, Launcher none). Splitters
have three outputs and one back input, mirror-image of conveyors, so a splitter must point the way
the last conveyor travels. Four doc pages were patched with explicit corrections and the habit of
verifying against the running engine rather than the docs became the project's founding precedent —
it paid again on Jul 28 (Builder `fire()` works only on the bot's own tile; Build/Heal/Destroy work
diagonally; the Core spawns on a uniform 12-tile ring around its 2×2 footprint; even the
engine-bundled `spec.md` has a wrong Core action radius) and again on Aug 1 (Launcher pickup is
team-blind despite the docs).

Also established here: the execution model (10 ms per unit per round + 5% bank; an uncaught
exception permanently kills the unit; 50-unit cap; 1000-round limit; AWS Graviton3 on the ladder;
Python 3.12/3.13, no native code), one persistent `Player` instance per unit, the 16-slot u32
global store with one-round-buffered writes as the only sanctioned cross-unit channel, and the
SHARED_GIL sub-interpreter model (never name Player methods after Controller methods). The
undocumented `.map26` format was reverse-engineered (tiles 0=EMPTY/1=WALL/2=ORE) and a 15-map atlas
built from the game's own sprites — the artifact that later became the fairness controversy. Codex
designed a 64-byte map-sharing encoding (rotational canonicalization + combinadic set encoding,
every known map ≤ 29 bytes) that was never wired in — `decode_map_info` is still a stub.

### 2. Jul 28 — first bots and the arms race (digests B, D)

`bots/1` was built in a day, and the day's crisis defined the meta: Jon's `lockin` — a
counter-tuned copy of Lucas's own architecture — went 14–1 against it. The decisive answer was
**parking a Builder on the final Core-feeding conveyor to physically deny the supply-line takeover**
(2/30 → 12/30, landing at 11–4 vs lockin and 13–2 vs Jon's `frontier` simultaneously). That is the
earliest ancestor of everything that later won: deny/guard the home ground rather than out-attack.

The other founding discovery was the **TLE cliff**: at the ladder's 10 ms limit,
`ordered_ores`' per-ore reverse BFS cost 21.1 ms on the Core's first turn and left the bot inert
(0 mined in 1000 rounds); one shared reverse BFS cut it to 2.76 ms and flipped a stalemate into a
turn-88 Core kill. The same bug shape — a full-map search inside a per-candidate loop — recurred
twice more (Aug 1 Codex: 10.67 → 1.50 ms; Aug 2 ragnarok: 13.48 → 3.00 ms). CPU is a strategic
resource, and the cluster's hardware is ~1.5× slower than this laptop.

An unattended Codex-vs-Claude arms race (4 pushes in 2.5 h) and Lucas's own 840-game round robin
closed the era: claude_challenger_1 topped it at 145/210; a large first-listed-side advantage
proved both orientations are mandatory in every measurement; per-game determinism was first
observed here. Also learned: each Builder raises all build costs 20%, so army spam starves the
economy — the seed of the scale-discipline doctrine.

### 3. Jul 28–29 — the RL detour (digest C)

The session that created this checkout (`llm-rl`, branch `x/llm-RL`): an AlphaGo-inspired PPO
self-play attempt. Architecture was forced by the engine (per-unit sub-interpreters forbid torch →
Unix-socket inference server for training; the ladder forbids sockets → pure-Python export with
JSON weights and manual matmul, measured ~0.56 ms/forward, fully TLE-compliant). After a major
action/observation redesign (14 → 34 Builder actions, hybrid 7×7 local + 8×8 coarse map memory),
the verdict was **0 wins in 17,792 matches** — units died within ~a round of spawning, root cause
never found before Lucas killed it ("yes kill it"). The RL line is dead, but its engine findings
(sub-interpreter constraints, the pure-Python deployment budget) still bind every bot. Lucas's
"Don't allocate gpu time if you don't use it!" survives as HPC etiquette.

### 4. Aug 1 — infrastructure day (digests E, F, G)

The evaluation stack was built in one day, in parallel Claude and Codex sessions, and it is the
instrument everything since runs on:

- **The harness** (`tournament/`): mElo + Nash averaging per Balduzzi 2018, bots pinned
  `name@commit` via `git archive` (bots on unchecked-out branches are usable; ratings can't be
  invalidated by edits). The paper's own appendix-E SGD *failed its own rock-paper-scissors test*
  and was replaced with the closed-form §F.3 Schur construction. One match per OS process
  (SHARED_GIL). Match cost is mean 8.8 s / max 64 s — the early 1.3 s estimate was one lucky
  41-turn game.
- **The founding rating insight**: `tempest@da3fd8a` ranked #11 by mElo yet beat all 41 opponents
  head-to-head — the sole Nash-core agent. mElo rewards crushing weak ancestors; Nash asks only
  "can anyone beat you?". Report both; the disagreement (`rank_delta`) is the signal. By evening
  the Nash core was a literal rock-paper-scissors cycle (vanguard_oracle 0.575 /
  tempest_oracle_ferry 0.305 / Elias's autistimusprime 0.120).
- **Fairness**: `tempest_oracle_ferry`'s embedded map atlas made it literally unbeatable (45–0,
  nash_prob 1.0) and was flagged unfair the same afternoon. A code-based audit found 11 bots
  mislabelled fair (including every `tempest_reinforcements` revision). Crucially (established
  Aug 2): the atlas ban is **our team's house rule, not a league rule**.
- **The CI**: `botrankings-evaluator.timer`, 2-minute ticks from the `florent-code-league-ci`
  worktree on `x/tournament`, publishing to lucasrgpedersen.com/botrankings. Lucas's verbatim
  standing order — **"NEVER silently ignore missing data. Fix it"** — reshaped the framework and
  its guard later caught a scheduler/rater mismatch that would have published fabricated results.
- **Compliance**: timeouts as censored ≥12 ms observations, expanded to all 21 maps (v5), which
  flipped 7 verdicts including ladder-#3 `vanguard@9932bec` to exceeded.
- **The relay chain**: Lucas specified the Launcher ferry chain to the enemy base that night;
  Codex found `_opening_ferry` let only Builder 1 ride, and per-Builder request slots flipped the
  126-game benchmark from 41 wins to 72. This mechanic, heavily re-tuned, is still heimdall's
  signature.
- Also: second-moving Team B wins 51.0% field-wide (cause: turn order is ascending global entity
  id — established Aug 3); seat bias direction varies by bot, so both seats always.

### 5. Aug 2 — the meta cracks open (digest H)

Five threads, each with a lasting lesson:

- **`COMBAT_AMMO_FLOOR`**: the suspected regression's two hypotheses were both measured inert;
  the real finding was tempest_reinforcements playing entire matches at 0–1 ammo with
  `MIN_AMMO_FOR_GUNNER = 20` gating every turret path. A floor of 80 took it 52.4% → 78.6%
  (+22/−0 paired, p < 1e-5). Pushed as `65ddc55` — the exact build that, two days later, topped
  the *held-out* map pool. Also proven here: engine seeds are completely inert.
- **Map clustering**: over 138,785 matches, the 21 maps split into 4 clusters that reproduce
  exactly on independent halves (adjusted Rand 1.0); rush wins 82%/79% on the open clusters and
  28%/25% on the closed ones (bridge 3.6% vs showdown 96.9% for the same bot pair). But **one
  strategy branch captures two-thirds of the ceiling** (+6.8pp atlas-free; k=4 is *worse*), and a
  turn-0 fair bot cannot measure map geometry (vision gap — the entire reason the atlas exists).
- **prospect / janus and the shelf-life lesson**: the doctrine that won 8–2 against its own twin
  was a wash against a real opponent, and the "vanguard beats tempest on closed maps" fact janus
  was built on had already expired — the tempest line outgrew it in one day of commits. *A
  map-strategy result is a fact about two particular bots on a particular afternoon.*
- **The regression benchmark**: Lucas hypothesized the lineages were going in circles; the
  `benchmarks/` package (1,944 matches) said "right, and understated" — mistral built 0 harvesters
  in 138 games, the bots built to defend lost to rushes worse than the attackers did, casemate
  shipped an 8-connected pathfinder on a cardinal-only engine.
- **`ragnarok`**: the "final boss" composite, every adopted mechanic ablated rather than argued
  (field Gunners under FORTIFY +8, lane-blocking +5, corner doctrine +5, siege Sentinel +2, three
  exactly 0). 322/378 (85.2%) against nine opponents; `ragnarok_fair` (generated atlas-free twin)
  70.6%. Plus the TLE fix, the frozen-opponent lesson (Lucas edited vigil mid-A/B), and the
  evaluator id-race fix.

### 6. Aug 3 — replay intelligence and the lineage sprint (digests I, J)

Ladder replays were decoded (schema extracted from the visualiser JS; the server strips stdout but
leaks `execTimeUs`). **Pantheon (#1) plays one fixed catapult opening on every map; Erebus (#2)
builds no Launcher at all and wins on the round-1000 titanium tiebreak; the rush is beaten by
surviving it** — whoever has turrets around their own Core before the enemy's forward turrets
land, lives. Porting Pantheon's opening was measured a downgrade (18/42 vs 23/42): our relay chain
already delivers a Gunner to the enemy Core on round 12 of aurora vs Pantheon's 32.

The lineage sprint (valkyrie → warden → warden_walk → aegis → steward → bastion) found the day's
one real lever by chasing an anomaly: `ragnarok_fair` beats `valkyrie` 25/42 while `ragnarok` only
draws — the fair twin *cannot ferry*, walks, and ends with Gunners and Harvesters where the
chaining bot ends with Launchers. **Every Launcher is +10% on every later price, and the bill
lands on the only things that win.** Capping the relay and ring moved the worst-map metric
5% → 33% and put `warden_walk` into the Nash core ({vigil@e22eda8, warden_walk} at 50/50 across
98 bots / 285,183 matches) — with the *lowest* mElo of the top seven, which sharpened the goal:
**highest mElo AND sole Nash support**, not either alone. steward fixed the dying-rich bug (a team
down to one Builder never respawns and dies holding 358 Ti); the opening headcount was settled at
three (a fourth Builder regresses in both directions). `pantheon_replica_day3` reproduced
Pantheon's online signature (90.5% @ r34 vs the real bot's 93% @ r38, 12/13 outcome agreement).
The multi-agent working rules (CLAUDE.local.md) date from this evening.

### 7. Aug 3 night – Aug 4 — heimdall and the great re-sweep (digest K, NOTES.md)

Under an explicit goal (">80% against all other bots… fair bot that doesn't use the maps"),
`heimdall` was built on the warden_walk chassis:

- **The reactive home guard** — answer an intruder *on sighting*, not after the Core has already
  taken 50 HP (which fires five rounds after the enemy turret is emplaced) — was worth +17pp, the
  single biggest mechanic win in the record. A *static* pre-placed guard (bastion) is worth +1
  game; the reactive one +29 over the same control. Only the ring Builder guards; letting all
  three guard costs the economy (0.815 vs 0.875).
- **The atlas is worth ~12pp on the published pool and exactly zero off it**: on generated maps,
  three atlas-carrying controls landed on an identical 0.479 vs heimdall's 0.677, reproduced on a
  second independent set. And the excuse "the weak matchups are hard because they carry the atlas"
  was disproved by a control: `ragnarok_fair` is *harder* to beat than `ragnarok`.
- **The stale-constant re-sweep**: turning `FERRY_ON_INFERENCE` off (0.807 → 0.839), guard radius
  36 → 64 (0.857), chase 4 → 6 (0.875), guard cap 4 (worse in total, kept for the worst matchup),
  relay cap 1 → 2 (0.878), ring 2 → 1 (**0.905 pool / 0.838 unknown maps, every opponent
  ≥ 0.81**). The two biggest knobs sat behind a NOTES line saying they were "finished". Every
  constant tuned before the ferry came off had flipped.
- **The economy bug chain**: three separate "zero titanium over 1000 rounds" defects traced from
  replays (a miner asking to be thrown two tiles, a ferry request never expiring — 969 requests in
  one game, a belt losing its Core-feeding tile with no shared memory of it). The last needed a
  four-link fix ending in Lucas's income watchdog (Core notices titanium stopped arriving) —
  the right instrument precisely because it needs no Builder's vision.
- **Methodology gold**: the engine is deterministic given (bot, opponent, map, seat, seed), so
  "noise" was the wrong word all along — the right phrase is "too few maps to say whether it
  generalises". Pre-registered replication killed a +11-game find (counter-battery) and confirmed
  a +17-game one (the guard's escalating allowance). Three consecutive ±3-game washes = this
  chassis is out of reach of a 168-game gate; stop tuning, change mechanism or instrument.
- The held-out map eval (93 bots, ~115k matches) showed the secret pool *disagrees* with the
  official one — secret #1 is `tempest_reinforcements@65ddc55`, and a bot can be Nash rank 1
  while scoring 0/10 on the core maps (the map-pool confounder made flesh; only per-map Nash
  averaging is immune). `vigil@e267eeb` is the robust combined bot.

---

## The through-lines — conclusions confirmed independently, multiple times

These are the things future work can lean on. Each was confirmed on separate days, by separate
methods, usually on separate chassis.

1. **Guard the home ground; the defence must trigger on sighting.** Jul 28 conveyor-parking
   (2/30 → 12/30) → replay finding that rush is beaten by surviving (Aug 3) → reactive guard +29
   games vs static +1 (Aug 3–4). Confirmed ≥3 independent ways over 6 days.
2. **Scale discipline: every body and every Launcher taxes every later price.** Jul 28 ("army
   spam starves the economy") → Aug 2 ablations → Aug 3 Launcher caps (5% → 33% worst-map) and
   headcount-of-three → Aug 4 refill-catastrophe next to the guard. The principle held every
   time; *which* spender to cut moved with the chassis.
3. **Waste beats tactics as a place to look.** COMBAT_AMMO_FLOOR (+26pp from a bot that couldn't
   afford to shoot), dying-rich respawn fix, zero-economy bug chain, banked-titanium losses. "Look
   for resources the bot fails to convert before tactics it fails to execute. Trades between
   matchups are usually a frontier; waste is usually free."
4. **The engine is deterministic and the docs are unreliable.** Determinism observed Jul 28,
   verified across cluster nodes Aug 1, seeds proven inert Aug 2, byte-copy control scoring
   identically Aug 4. Docs corrected on ammo, Launcher pickup, fire(), spawn ring, Core radius.
   Always probe the engine; always fix the seed story in your head before reading a table.
5. **mElo and Nash measure different things and both are needed.** tempest (Aug 1),
   tempest_oracle_ferry (Aug 1), warden_walk (Aug 3): three separate demonstrations that a bot
   can be unexploitable yet mediocre on average, or vice versa. Current goal: both at once.
6. **CPU is a strategic resource and the bug is always a per-candidate map search.** Three
   instances (Jul 28, Aug 1, Aug 2), same shape, same fix. A TLE is a *correctness* bug — the
   engine silently drops the turn. Cluster hardware is ~1.5× slower than local.
7. **The atlas is worth ~12pp on the pool and nothing off it** — measured twice with clean
   controls (three bots at exactly 0.479; second set reproducing 20pp exactly). The final is
   presumably on unseen maps; fairness and final-readiness point the same way.
8. **The closed/open map split is real (Rand 1.0, twice) but shallow**: one branch captures
   two-thirds of the value; per-map win rates don't correlate with any geometry statistic for the
   Launcher knobs; only ~1 pool map has terrain worth adapting to. Map adaptation keeps
   *seeming* bigger than it measures.
9. **Both seats, frozen opponents, full runs, full panels.** Seat bias confirmed Jul 28 and
   Aug 1 (direction varies by bot; mechanism is ascending-entity-id turn order). Partial-run trap
   hit twice in one session; narrow-panel trap at least three times (steward, guard cap 4,
   Launcher knobs).

---

## The reversals ledger — believed, then disproved

The record's most valuable section. Format: what was believed → what overturned it → the general
lesson. Bots named per the genealogy section below.

1. **"Ammo is a team-wide pool"** (official docs, tutorial) → engine probing, day 1 → *verify
   against the engine, not the docs.*
2. **"We can read opponents' stdout from ladder replays"** (asserted Aug 3) → downloaded replays
   are stripped; only `execTimeUs` survives; Lucas caught the false claim → *check the actual
   bytes before claiming a capability.*
3. **"The Launcher knobs are finished (relay 1, ring 2)"** (NOTES, Aug 3) → full-panel re-sweep on
   the current chassis found relay 2 / ring 1, +14 pool games — the largest gain of the session,
   sitting behind a note saying not to look → *a constant is only measured for the bot it was
   measured on.* Three causes, all general: narrower panel, older chassis, interacting knobs read
   one at a time.
4. **`FERRY_ON_INFERENCE`** — measured three times, flipped twice (OFF on atlas ancestors, ON on
   pre-guard heimdall, OFF on shipped heimdall) → *re-test flags after any change that alters what
   the bot spends on.* Note the residual nuance: on the official pool the ferry-at-guess is +9
   (rotation-heavy symmetry convention), on uniform generated maps −3; the shipped bet is ON for
   pool-like map conventions.
5. **Counter-battery, +11 games** (found on generated set 2) → pre-registered prediction on a
   fresh third set failed (+2); full ledger +1/+11/+2/+1 → *"it worked on the set I found it on"
   is not a measurement; pre-registration is the cheapest lie detector.*
6. **"steward is off the trade-off frontier"** (3-opponent probe, 84/126) → four-bot panel
   reversed it to noise → *two opponents chosen as poles of a trade-off are a probe, not a panel.*
7. **"Builder refill is a large regression"** (−30pp beside the guard) vs **"refill is neutral"**
   (steward, +2) — *both true*: refill is chassis-dependent, harmless where Builders rarely die,
   ruinous next to a guard that makes both sides lose bodies → *interactions, not contradictions;
   test the mechanic on the chassis that will carry it.*
8. **"The weak matchups are weak because those bots carry the atlas"** (asserted repeatedly,
   Aug 3–4) → `ragnarok_fair` (atlas removed) is *harder* than `ragnarok`; the real cause was our
   own ferry → *one control settles what any amount of assertion cannot.*
9. **"Map doctrine wins"** (prospect fortify, 8–2 vs its own twin) → wash against a real third
   party (6/10 either way); +0.9pp over 3,444 games with mElo disagreeing → *a knob-flip cannot
   reproduce a between-bot difference; different maps are won by different machines, not
   different flags.*
10. **"vanguard beats tempest on closed maps, so dispatch by map"** (janus's premise) → the
    pinned tempest the tournament measured had been outgrown within a day → *map-strategy results
    have a shelf life of about one day of commits.*
11. **Partial-run reads** — "2/10 vs vigil" (full sample: 57%) and "warden 90.5%" (full: 89.0%,
    neutral) in one session → *a run is partial until matches.csv reaches the planned count.*
12. **"Inside noise"** as a concept → the local gate is deterministic; there is no sampling noise,
    only map-coverage doubt → *small differences are real behaviour on specific maps; what they
    are not is evidence of generalisation.*
13. **"Copy the leader"** (Pantheon's opening) → measured downgrade 18/42; our delivery is
    already faster (round 12 vs 32) → *decode what the leader gets right, check whether we
    already have it, port only the gap.*
14. **Pad-first spawn order** (Pantheon-style) → −25 games in 252; first Harvester delayed
    2 rounds → same lesson as 13.
15. **"A static guard approximates the reactive guard"** → +1 vs +29 → *pre-placing where the
    enemy probably comes is a different mechanic from answering the intruder you see.*
16. **"~1.3 s per match"** (first estimate) → mean 8.8 s, median runs the full 1000 rounds → *the
    first sample was one lucky short game; cost models need distributions, not anecdotes.*
17. **The Balduzzi paper's own SGD** → fails its own rock-paper-scissors test with its stated
    hyperparameters → replaced with the closed-form Schur construction → *even the reference
    implementation is a claim to verify.*
18. **The RL line** → 0 wins in 17,792 matches, killed → the engine constraints it surfaced
    outlived it.
19. **"The `51ad530` reserve change caused the regression"** (both of Lucas's hypotheses) → 0 and
    1 flipped cells in 84; the real problem was ammo starvation nobody suspected → *instrument
    before hypothesizing; the biggest gain of that day was found while disproving the stated
    theory.*
20. **"BLITZ threshold 8 is the natural gap in the distance distribution"** → measured worse than
    off (duel at −6); shipped 6 → *a natural-looking threshold is still a knob to measure.*
21. **"The two-tile-pacing livelocks must be costing games"** → five idle-behaviour fixes across
    two Builders, all neutral off the pool (three landed on *exactly* 110/160) → *pacing is a
    symptom of having nothing worth doing; fix what put the Builder in that state, not the
    pacing.*

---

## The methodology doctrine (as it stands 2026-08-04)

What survived three weeks of being wrong in instructive ways:

- **Measure on the full 8-opponent panel plus a generated-map arm.** Never tune against the weak
  matchup alone (overfits: guard cap 4 looked +2 on two opponents, −5 on the panel).
- **Pre-register the prediction before the replication run.** It killed counter-battery and
  confirmed the escalating guard.
- **Both seats, always; frozen opponents, always; full runs only.**
- **Re-sweep constants after any change to what the bot spends on.** Treat every tuned-constant
  comment as "measured for a bot that no longer exists".
- **Trace losses instead of guessing.** The guard cap, the ferry defects, the income watchdog,
  and the enemy-Core flip-flop all came from reading one replay closely, not from sweeps.
- **Ship defect fixes even when score-neutral** (a target that changes every round is a defect
  whether or not the panel can see it), but don't *tune* on neutral results: three consecutive
  ±3 washes means the instrument is exhausted — change mechanism or move to the cluster's
  4,000-game samples.
- **The cluster is the instrument; the 42-game local gate is a screen.** Push to `x/luc` →
  ~3,900 matches in minutes; a freshly pushed bot waits two evaluator cycles; read
  `origin/x/tournament:tournament/runs/<run>/matches.csv`, and only when complete.
- **Grep fresh replays for `PLAN_FAILED .* NameError`** — `except Exception` around ammo
  conversion once hid a fatal typo through a 1/42 run.
- **`tools/generate_maps.py`** for anything claiming to be about unknown terrain (equal parts
  rotation/x-mirror/y-mirror; note the pool's designers prefer rotation 2:1, so generated-map
  scores understate the bot by whatever the symmetry guess is worth).
- **Never enumerate `tournament/custom_maps/`** — parsing the held-out set spends it.

Standing directives from Lucas, collected: "NEVER silently ignore missing data. Fix it." /
Explain plainly, define every bot and mechanic, no invented shorthand ("I have no clue what
refill means"). / Pushing is his call — it triggers the tournament ("DO NOT SUBMIT" to the
official ladder without his say; `fcode submit` *replaces* the team's active entry). / Protect the
CI; check work won't confuse discovery (`main.py` = a bot). / Mind the parallel agents: commit
only your own paths, never revert others' uncommitted work. / Don't burn compute idly (GPU
etiquette, half the cores while the rater runs).

---

## Where things stand (2026-08-04, ~02:00)

**heimdall** is the flagship: atlas-free, 0.905 on the 21-map pool against the eight strongest
bots (every opponent ≥ 0.81), 0.838 on generated unknown maps. Its stack: reactive home guard
(r²=64, chase 6, cap 4, escalating allowance on emplaced turrets), attacker-only ferry with
give-up, relay cap 2 / ring 1, income watchdog with miner replacement, sticky enemy-Core
inference. On the ladder the team entry (Jonathan's "Tempest Fast" v5) drifted 1703 → 1641,
rank 8 → 13 while local work raced ahead — the gap between local strength and the ladder entry is
unresolved business.

Open threads, in rough order of expected value:

1. **`r_cap3combo` measured 0.917 and is unshipped** (session cut off mid-flight; verify what it
   is before trusting it).
2. **Lucas's new bar: >80% on every *map*, not just every opponent** — jackpot, bridge, sprint
   currently fail. The remaining losses cluster in round-1000 economy tiebreaks on closed maps;
   the FORTIFY split was measured 2–12 *before* a working defence existed and deserves a re-test.
3. **heimdall has never received a cluster rating** (queue was administratively closed,
   `Open:Inact`) — the 0.905 is local-panel only.
4. **Pantheon throws *economy* Builders to distant ore; we only ever ferry attackers** — untested
   idea, flagged twice.
5. **Core-death projection** (Lucas's idea, in flight when the session died).
6. **The symmetry guess is wrong on exactly the two shared-edge maps** (sweden, vase);
   travel-distance ranking untested.
7. **vigil lineage overruns 10 ms** in real matches; any further work belongs on the ragnarok
   chassis until vigil's timing is fixed.
8. **pantheon_clone has uncommitted edits** (another agent's in-flight work — leave alone).
9. Secret-pool metric: only per-map Nash averaging is immune to both confounders; the site
   dropdown exists but the doctrine isn't folded into bot goals yet.

---

## Bot genealogy and cast

**Lucas's line** (bots/luc, x/luc): `bots/1` (Jul 28, first real bot) → *(via Jon's tempest)*
`tempest_reinforcements` (Aug 1, Tempest + reinforcement heartbeat + oracle atlas; unfair-class;
`@65ddc55` = the ammo-floor build, secret-pool #1) → `vigil` (Aug 2, turret-meta lineage, Lucas
hands-on; three generations in that day's top 4) → `prospect`/`prospect_rushonly` (fair vigil fork
+ map doctrine; A/B twin) and `janus` (round-0 dispatcher, prospect + vendored vanguard) →
`ragnarok`/`ragnarok_fair` (Aug 2, ablation-assembled composite, 85.2%/70.6%) → `valkyrie`
(ragnarok + ferry gate fixed to fire on *knowing* the Core; cluster 89.7%) → `warden` (valkyrie +
vigil's repair/write-off ports; highest raw win rate 0.8851) → `warden_walk` (+ Launcher caps;
Nash pillar) → side branches `aegis` (conditional cap — frontier slide, dead), `steward` (+ refill
— neutral), `bastion` (+ static guard — dead) → **`heimdall`** (atlas-free + reactive guard +
re-swept constants; current flagship). Parallel: `pantheon_clone` / `pantheon_replica_day3`
(replica studies), `tempest_reinforcements` variants, `valkyrie_atk2`/`_econ2` (headcount probes,
both regressions), `vigil_reinforcements`.

**Jon** (x/jon): `lockin` (the Jul 28 rival), `frontier`, `tempest` family (incl.
`tempest_oracle_ferry`, the 45–0 atlas bot), `mistral`, `undertow`, `vanguard` family (incl.
`vanguard_oracle`), `casemate`, `jonbot` (41/42 self-improvement Aug 1), `v233_*` probes.
**Elias**: `autistimusprime` (Nash-core member Aug 1), `e_*` atlas family, `BLD4`.
**Viktor**: branch watched by the CI since Aug 3; no discoverable bots yet.
**Ladder (external)**: `Pantheon` (#1, fixed catapult opening, 304–1,749 µs/turn), `Erebus`
(#2, no Launchers, tiebreak economy), `CtrlAltDefeat` (#4, survives rushes), `gobbleglitch`
(probed for engine exploits: none; source of the turn-order finding), `coinflip` (rescored as
true draws).

**Mechanics glossary**: *atlas* — bundled offline copy of the 21 published maps (house-rule
unfair; inert off-pool). *ferry/relay* — Launcher chain throwing Builders toward the enemy Core
(throw range r² ≤ 26, team-blind pickup). *ring* — Launcher sites screening our own Core.
*guard* — the ring Builder answering sighted intruders with aligned Gunners. *BLITZ/FORTIFY/RUSH*
— doctrine modes chosen at round 0 (cores-close all-in / closed-map economy+turtle / default
attack). *income watchdog* — Core detects titanium stopped arriving and respawns a miner.
*picket* — idle Builder posted as a forward sensor (measured: not worth shipping). *16-slot
store* — the only cross-unit channel; writes visible next round.

---

## Where the full detail lives

- `bots/luc/history/digest-A…K.md` — eleven per-chunk digests with per-session narratives, exact
  numbers, and timestamps (A: Jul 24–27 · B: Jul 28 · C: RL detour · D: Codex Jul · E: Codex
  Aug 1 day · F: Codex Aug 1–2 night · G: Claude Aug 1 · H: Claude Aug 2 · I: Aug 2 night–Aug 3 ·
  J: Aug 3 day · K: Aug 3 night–Aug 4).
- `bots/luc/NOTES.md` — the live working ledger (most current tactical detail).
- `git log` on x/luc — commit messages double as the lab notebook from Aug 2 onward.
- `tournament/README.md` — harness and CI operation.
