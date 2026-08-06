# Digest J — Claude Code sessions, afternoon/evening of 2026-08-03

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

Three sessions. Sessions 1 and 2 ran **concurrently** (session 1: 14:30–21:29 UTC; session 2: 17:57–21:59 UTC) — session 1's late-evening confusion about unfamiliar bots is session 2's (and a third, off-chunk heimdall agent's) work appearing in the shared tree, and it is the direct origin of the multi-agent rules now in `CLAUDE.local.md`.

---

## Session 1 — 39d8568b-cea1-4484-b092-bc245e6d0979
**Start 2026-08-03T14:18:24Z (/clear; first real prompt 14:30:58Z), last dialogue 21:29:23Z. ~7 h. Branch x/luc.**

**Goal:** Lucas's opening brief (14:30:58): the online meta splits games into *rush* and *collect* stages; belts have throughput 1 titanium/tick and each harvester mines at 0.25, so max 4 harvesters can feed the last belt into the base; iterate a new bot with the meta in mind while he works out. Fetch online games of the top players **Pantheon, Erebus, CtrlAltDefeat** (example match IDs `accc644f-81b0-4fc9-9f5e-e63036711011`, `44349540-16bf-41a8-b098-e79b6058cbb7`). **Not allowed to submit bots online** (reveals information). Push to x/luc → evaluated in ~20–30 min on x/tournament. Compliance: max 10 ms per unit turn. At 14:33 he added: our online version is `tempest_fast`, internally ranked low — the best information is top-vs-top matches.

### Replay decoding and ladder findings
- Recovered the full `.replay26` protobuf schema from JSON embedded in the visualiser JS; decoded 20 games of Pantheon (#1), Erebus (#2), CtrlAltDefeat (#4). Our ladder rank at the time: #9/92 (v5 "Tempest Fast").
- **Pantheon's opening is identical on every map**: Builder round 0 → Launcher round 1 at radius 2 on the enemy-facing side → one throw per round on rounds 2–5 → Launcher razed round 6. Two throws carry raiders to the enemy Core; **two carry economy Builders to distant ore**. Throws cross walls (r²=26); on `pinch` it kills the Core on round 24.
- **Erebus builds no Launcher at all** and takes games on the round-1000 titanium tiebreak — all-in isn't forced at the top.
- **The rush is beaten by surviving it**: every CtrlAltDefeat win over Pantheon ran long (1000, 867, 470 rounds). Whoever has turrets around their own Core before the enemy's forward turrets land, lives; a tie goes to the attacker.
- Our `ragnarok` relay chain already lands a Gunner beside the enemy Core on **round 12** of aurora vs Pantheon's 32 and CtrlAltDefeat's 43 — "stop treating the ladder's opening as the thing to copy."

### valkyrie (pushed 4a5b44050, ~15:08)
First fork attempt (`spearhead`, on vigil) was abandoned: vigil loses 10–32 to ragnarok, and the vigil lineage TLEs (~0.3/game) where ragnarok doesn't. Rebased onto ragnarok as **valkyrie** with (1) pad-first spawn order and (2) ferry-gate fix (`_opening_ferry` began `if p.atlas is None: return False` — on any unpublished map the whole relay silently switched off). Measured-and-rejected en route: Pantheon's single-catapult opening replacing the relay chain 18/42 vs 23/42; capping the ring at one pad site 18/42 vs 20/42; ferrying at the symmetry *guess* 17/42 vs 21/42 atlas-free; vigil-lineage rebuild 12/42. Compliance: 0 turns over 10 ms, worst 3,993 µs locally.

- 15:59 Lucas: "did you not push? I don't see it on the website." Push confirmed (`origin/x/luc = 4a5b44050`); valkyrie was **queued** behind `tournament/runs/secret-eval-1` — a hand-submitted 13:02 HPC run (4,283 elements, DTU jobs 29015696–29015700, 92 bots staged, 0 results 5 h later). Also clarified: the public ladder is untouched by design (no submissions).
- 16:02 Lucas: "Did you say we can see pantheon's debug prints?" — **caught a false claim.** Verified: downloaded ladder replays strip `stdout` (648 `BotOutput` messages, 0 stdout events); only local replays keep it. What survives is **`execTimeUs` per unit per round** — Pantheon runs 304–1,749 µs, well under the 10 ms budget. Corrected in NOTES.md, valkyrie README and memory; pushed `30d049116`.

### Barrier tactic (Lucas's 16:31 observation)
Lucas: Pantheon places walls in the line of sight of enemy turrets (with a turret-id/turn-order argument) and in the way of conveyor lines. Verified against replays: **31 of 33 Pantheon barriers sit directly in an enemy Gunner's ray**, and turn order is id order **421/421 turns**. But the use is offensive: every barrier is deep in enemy territory (distance 2–5 from their Core), rebuilt on the same tile (e.g. (1,3) rebuilt T7, T10, T20, T23, T26, T30 — 18 shots absorbed) — a regenerating damage sponge: 3 Ti absorbs 30 damage = 3 Gunner shots = 6 enemy ammo. Derived rule: only barrier a tile in an enemy ray that is in no friendly ray. Added to valkyrie as siege barriers: first attempt 17–25 (worse — soaking ordered before battery-building), reorder → 20–22, neutral because rare (11 siege barriers/42 games; median game 48 turns). Pushed `d25d55db7`.

### The 70% bar and the panel workflow
- 16:38 Lucas (queued `/goal`): "keep iterating until I come back, push every once in a while once you feel you have a contender or a risk of regression."
- **16:42:58 Lucas (queued): "I want only the best bot ever. You have to beat all other bots on at least 70% of maps. To test this, first beat the best, ragnarok@79582fc, vigil@e267eeb on 70% of maps, then push and when the results come back check that it beats everyone on 70% of maps."** This is the session's governing metric.
- Found the repo's 252-game panel (vigil, tempest_reinf, prospect, mistral, vanguard, gobbleglitch × 21 maps × 2 seats). It exposed the headline change as a regression: **pad-first order costs 25 games** (ragnarok 209/252 = 82.9%; valkyrie with pad-first 184/252 = 73.0%; without, 209/252) — the pad pushes the miner from spawn index 0 to 2, first harvester round 7→9, collected 696→470. Fix pushed `d1813124b`.
- Calibration: a ragnarok-vs-itself mirror splits 9/12 across 21 maps (no seat edge; outcomes deterministic and map-structural), so winning a map 2-0 vs a near-equal needs ~84% per-game win rate; valkyrie stood at 48% (24%/29% of maps 2-0).
- **16:55 Lucas: "You do know that when you push the bots gets ranked against all other bots automatically… Don't run the full ablation on my laptop locally lol. The CI workflow uses a hpc and everything."** (Laptop was at load 24 on 16 cores.) Local compute stopped; free salvage: `norush` ablation 203/252 vs 209 — FORTIFY corner doctrine mildly load-bearing.

### Cluster round 1: valkyrie, econ2/atk2, two misreads, warden
- valkyrie@d181312 went to DTU as job **29021928** (3,927 matches / 197 array elements, run `auto-33ccb918e602`). Result: **89.7% overall, 0 timeouts, 0 exceptions, max turn 5,944 µs** (vs 3,993 µs locally — the cluster hardware is materially slower).
- **Partial-run misread #1:** at 3,038/3,906 matches, reported "the ragnarok line loses to the vigil line" off a 2/10 sample vs vigil@e267eeb; the full sample is **24/42 (57%)**. Retracted (`eec645f42`); rule recorded: a run is partial until matches.csv hits the planned count. The surviving anomaly inverted: **ragnarok_fair beats valkyrie 25/42 while ragnarok itself only draws 21/42.**
- Bridge hard bug: ragnarok mines **0 titanium in both seats on bridge** — `COMBAT_AMMO_FLOOR` converts down to `EMERGENCY_RESERVE = 10` while scale ~2.4× makes a harvester cost 47 Ti (T17: "needs 47; available=14"). The fix attempt first scored 1/42–2/42 because a missing import (`FIRST_HARVESTER_RESERVE_ROUNDS`) threw `NameError` every round inside a broad `except Exception` — **the bot played the whole game with 0 ammunition without ever crashing**. Import fixed, then the reserve measured as a real regression anyway (vs vigil@e267eeb 24/42 → 15/42): firepower beats the marginal harvester. Reverted.
- **4-builder opening rejected in both directions** (full 3,990-match samples): `valkyrie_econ2` (2nd miner) 81.1%, `valkyrie_atk2` (2nd attacker) 83.2% vs valkyrie's 89.7%, both 12/42 head-to-head. Ragnarok's 3-builder constraint vindicated; Pantheon's 4 builders are not the lever.
- **vigil regression found and fixed:** working-tree vigil = `vigil@e267eeb` + one commit (`64e40cba4`) flipping `RING_COVER_SHELL` False→True; it was losing 15/42 to its own previous commit. Off again → exact 21-map 1-1 mirror. Pushed `c71a543fc`; cluster validated at 4,032 matches: 88.7% overall, 21/42 vs e267eeb — local gate and cluster agree exactly.
- **warden** (`bad5964d1`): port of two capabilities ragnarok lost when assembled — vigil's `_repair_network` (mend a shot conveyor; one 3 Ti tile restores a whole belt's income) and `_write_off` (`self_destruct` a stuck builder, refunding its +20% scale). Cluster full sample: **89.0% (3587/4029), 21/42 exact draw vs valkyrie — neutral** (the 90.5% partial read at 2,407 matches was **misread #2**).

### The launcher-cost insight (the session's one real lever)
Chasing why ragnarok_fair wins: it *cannot* ferry (atlas-gated), so it walks — ending aurora with 3 Launchers / 2 Harvesters / 7 Gunners vs valkyrie's 6 / 1 / 4. **Every Launcher costs 20 Ti plus a permanent +10% on every future price, and the bill lands on the only two things that win: Gunners and Harvesters.** Both optima are interior:
```
MAX_RELAY_LAUNCHERS   0: 16/42 vs rag (14% worst-map)   1: 25/42 (29%)   2: 25/42 (24%)   uncapped: 21/42 (5%)
RING_MAX_SITES        1: 24%   2: 33% (26/42 rag, 24/42 vigil)   3: 29%   8: 29%
```
Worst-target map rate moved **5% → 33%** — the largest movement on the 70% bar all session. `warden_walk` pushed `3318ffdf3` (ring cap later at `c5c0b8962`). Checked and kept: siege Sentinel earns its +20% (29% without vs 33%); FORTIFY field gunners earn theirs (24% without); attack-Gunner cap doesn't bind above 7. Side effect: worst builder turn 4,198 → 2,994 µs. Enemy-ray-avoiding gunner placement (Lucas's own scratchpad idea) added +2 games vs vigil (24→26).

### The full ledger and the redefined bar
18:05, run `auto-f11bf027e3d4` complete: **98 bots, 285,183 matches**:
```
1  vigil@18b749d        melo 457.0  wr 0.8731  nash 0
2  vigil@e22eda8        456.0       0.8832     nash 0.500001
3  vigil@e267eeb        452.0       0.8824     0
4  warden@3318ffd       451.5       0.8851     0   ← highest raw win rate in the field
5  ragnarok@79582fc     451.1       0.8839     0
6  valkyrie@d181312     450.0       0.8834     0
7  warden_walk@3318ffd  435.1       0.8698     nash 0.499999  (+6 places)
13 ragnarok_fair        347.0       0.7899     0   (−5)
```
**warden_walk displaced both ragnarok and ragnarok_fair from the Nash core** — but with the lowest mElo and win rate of the top seven: the caps bought Nash support *by specialising* (sold 40/42 matchups to buy 21/42 ones). Per-opponent: caps help ragnarok_fair +14pp, valkyrie +12pp, ragnarok +10pp; hurt vigil@60d5afa −24pp, vanguard_oracle −19pp, casemate_oracle −12pp, prospect −10pp.

**18:11 Lucas: "But remember you have to beat ALL other bots by 70%, so you have to both have the highest mElo but ALSO be the single nash core bot."** — the bar became: highest mElo AND sole Nash-core agent.

### aegis, steward, bastion (all pushed, none rated this day)
- **aegis** (`5709fbf90`): conditional cap on warden — `_opening_ferry` capped at 1, stuck-recovery `_step` uncapped. Measured: the trade is **conserved** (a frontier, not a knob): warden 30+18=48, aegis 27+20=47, aegis-threshold-5 26+23=49, warden_walk 26+24=50 (vs prospect / vs ragnarok_fair, of 42 each).
- **steward** (`e55aab5a0`): builder-respawn bug fix. `core.py` gates respawn on a heartbeat proving only *one* builder alive; losing 2 of 3 → never replaced. Sweden trace: T15 Ti=154 3 builders → T45 139 1 → T90 298 1 → **dies T103 holding 358 banked Ti**, beaten by an opponent that mined nothing. Fix: treat a ≥110 Ti idle bank (12-round cooldown) as the respawn signal. After: survives to T138, mines 360 vs 150; across 38 gate losses **zero** now end holding ≥100 Ti.
- **19:22 Lucas (queued): "How come you are measuring against prospect and ragnarok_fair only by the way?"** — exposed the narrow probe. Adding the real worst casualty vigil@60d5afa: warden 79/126, warden_walk 72/126, bastion 84/126 — warden_walk's −9 there reproduces the cluster's −24pp; and bastion gives up 2 games (29 vs 31), so "off the frontier" was an overstatement.
- **bastion** (`52c1492c8`): home-defence timing. Data: wins have first home turret at median T14, losses T20, the enemy plants at T10 either way, and **12 of 38 losses never build a home turret at all** (`_defend_core` is purely reactive, firing only after the Core is damaged). Converts the second ring site from Launcher to Gunner facing the approach; lands T10. Local: prospect 30, ragnarok_fair 25, total 55, gate worst 29%.

### The multi-agent collision and the evening postscript
At 19:54 the ledger showed **heimdall** and **pantheon_replica_day3** — bots this session never created — plus uncommitted `pantheon_clone` edits (6 files, +144/−24) and an unfamiliar HEAD (session had been compacted). It read the current NOTES and relayed the (other agent's) heimdall results: reactive guard (`_guard_home`: on sighting an enemy within r²=36, immediately build an aligned Gunner) scores **147/168 (0.875)** vs control warden_walk **118/168 (0.702)** on the 168-game panel; on 24 generated symmetric maps heimdall 65/96 (0.677) while warden_walk, valkyrie and ww_fair all landed **exactly 46/96 (0.479)** — the atlas is *inert* off-pool (worth 11–13pp on known maps, zero on unknown; the guard worth ~20 points there; replicated on a 30-map set 0.617 vs 0.417). Also relayed: the "ferry at the symmetry guess is worse" result doesn't hold off-atlas (119 off vs 128 on) — a flag measured on a bot with the oracle is not measured for a bot without it. And it reported that the held-out `tournament/custom_maps` pool had been enumerated for dimensions/Core positions (a breach of the do-not-open rule).

**21:04 Lucas:** "You got confused since other agents are working alongside you… Please note somewhere that's not git tracked and which other agents will check that multiple agents are working at the same time and not to be thrown off by that and just minds one own business. Furthermore, it's fine that map size and core placement was read. Agents shouldn't do it again, but it's fine that it happened, you can remove the note." → wrote the "Several agents work this repo at once" and "Do not open the held-out evaluation maps" sections into `CLAUDE.local.md` (untracked via `.git/info/exclude`, auto-loaded); removed the breach note (`dd2de13d2`).

**21:14 Lucas: "Is there a reason you gave up on the bastion lineage?"** — answer: no decision was ever made; bastion/steward/aegis were **never rated** (deferred behind the queue). Ran the 168-game panel to settle it (control reproduced exactly at 118/168):
```
warden        107/168  0.637   ← correct control
steward       109/168  0.649   + builder refill        → +2, noise
bastion       110/168  0.655   + static home guard     → +1, noise
warden_walk   118/168  0.702   launcher caps
heimdall      136/168  0.810   atlas-free + reactive guard
```
Three corrections fell out: (1) the refill is **neutral** on this chassis, not −9 (that used the wrong control) — and the NOTES contradiction resolves: refill is harmless where builders rarely die, ruinous (147→85) beside a reactive guard that makes both sides trade bodies; (2) **a static guard is worth +1 where the reactive guard is worth +29** — pre-placing a turret facing a guess is not the same mechanic as answering a seen intruder; (3) "steward is off the frontier" was a narrow-panel artefact (84/126 on three hand-picked opponents; noise on the standard four-bot panel) — the very failure Lucas had flagged minutes earlier, reproduced on the next result. Committed `3abb2de97` (NOTES.md only). Verdict: bastion isn't broken, it's flat — correctly dead versus a chassis 26 games ahead; the one unexplored combination is heimdall + refill gated to when the guard isn't trading bodies.

**21:28 Lucas: "You need to explain some more context when explaining your findings. I don't have your context, remember that. E.g. 1 I have no clue what refill means."** — preference saved; findings re-stated with every bot and mechanic defined.

### Lucas's directives in this session (summary)
- No submitting bots to the public ladder (reveals information). Push to x/luc; the CI/HPC ranks them — don't grind ablations on the laptop.
- The bar, twice sharpened: beat ragnarok@79582fc and vigil@e267eeb on 70% of maps → beat ALL bots on ≥70% of maps → **highest mElo AND sole Nash-core bot**.
- Barrier/wall placement observation (16:31) — validated.
- "How come you are measuring against prospect and ragnarok_fair only?" — panels over probes.
- Multi-agent etiquette → CLAUDE.local.md; held-out map enumeration forgiven, not to be repeated.
- Explain findings with context; no unexplained shorthand.

---

## Session 2 — 05d146e7-6b75-4d33-a413-788991e5ff01
**Start 2026-08-03T17:55:43Z (/clear; first prompt 17:57:41Z), ends 21:59:44Z. ~4 h. Branch x/luc. Ran concurrently with session 1.**

**Goal (17:57 Lucas):** "Using the replays which are publically available, try to copy Pantheon's strategy as absolutely closely as possible… And you have to do it without submitting any good bots."

### Characterising Pantheon from 150 replays
Pulled 150 Pantheon replays (7.5 MB; Pantheon won 124). Full-schema decoder built (gotcha: terrain rows are *packed* repeated enums — silently breaks naive decoding). Findings, later validated on a held-out set:
- Opening 100% invariant across 150 games (Builder r0; Builder+Launcher r1; Builders r2–3; four throws r2–5 — two raiders at the Core, two economy Builders to far ore; Launcher gone r6).
- Throw range is **dist_sq ≤ 26 from the Launcher**, and Pantheon throws at max range. Landing tiles minimise *walking* (BFS) distance to the objective; tie-break = farthest tile — **103/103, zero counterexamples**.
- **The Launcher self-destructs after its fourth throw** — renting the range for ~5 rounds and handing back the +10% cost scale.
- **Median Pantheon game is 41 rounds**, ~110 Ti mined; 134/150 end inside 150 rounds. The economy is a hedge; the raid is the bot. Core damage is exclusively turret fire, 10 per hit, 500 HP (~50 shots).
- Round-0 rules found via exact reproduction: the Core spawn radius is **√8** (the Core is 2×2, so distance-1 tiles are unspawnable); the Launcher goes **one step further out along the 8-way ray** than the round-0 Builder (offset counts match one-for-one; 7/7 maps exact); only the round-0 Builder spawns deep, later ones adjacent.
- Atlas hypothesis refuted: wiring in ragnarok's map atlas improved rounds 1–2 (9→17/180 reproduced rounds) but made round 0 *worse* on five maps — Pantheon's round-0 tile is not aimed at the true enemy Core, so it isn't doing an exact map lookup.

**18:34 Lucas (queued) supplied the key test:** "are you watching our online matches with pantheon, and then testing if you can reproduce the matches locally by putting the bot online (tempest_fast) against your clone? Since the game is deterministic." Built exactly that (`tools/pantheon_analysis/repro.py`, tempest_fast from origin/x/jon, 15 real ladder games): the from-scratch clone matched only **17 of 180 rounds**, diverging within 0–2 rounds in every game — aggregate statistics had been flattering a bad copy. The from-scratch clone lost 1/42 to ragnarok, its own Core dying at median round 28 in 79/84 games.

### The pivot: fork ragnarok, add Pantheon incrementally
**18:58 Lucas:** push it even if imperfect, then "make the best bot possible within the constraint that you HAVE to follow pantheon's strategy." Pushed as `pantheon_clone`. Then **19:32 Lucas (after "Are you saying you only win 80% of the time against starter?"):** "Whatever you're doing right now is kind of hopeless. Starter is so bad it can barely mine titanium and places no turrets… see how we normally implement stuff… use that to jumpstart your replica… I can tell you that pantheon doesn't place turrets too far from the enemy core becuase they're dumb, it's specifically to target other turrets or launchers that are in their way." (The 81%-vs-starter number was 11 round-1000 timeouts lost on titanium collected — the economy delivered ~0.)

Forked ragnarok (which beats the from-scratch clone 41/42) and swapped in Pantheon behaviours stepwise, each measured on the panel (total / vs starter):
```
ragnarok fork baseline                     68.3%   100%
+ 4 Builders, pad built by index 0         65.1%   100%
+ pad Builder spawned on ring doorstep r1  60.3%   100%
+ Launcher self-destruct after 4 throws    58.7%   97.6%
+ Pantheon role order (first two raid)     49.2%   100%
```
Pantheon's opening costs ~19 points against our own bots across four measured steps. From-scratch clone 28.6% → fork 49.2%; kill 8/63 @ median round 278 → 32/63 @ 66. **19:16 Lucas (queued): name it `pantheon_replica_day3` for the push.** Two analysis corrections recorded: "raiders build exactly 4 gunners" was a truncation bug (real: median 3, tail to 53, no cap); "early gunner when rushed" was a map-size confound (all 49 early Gunners on maps with Cores ≤12 apart — **Pantheon has no reactive early defence**). Two engine facts fixed: `can_spawn` **raises** on off-map positions (one unguarded candidate silently aborted the Core's whole turn on corner maps — Cores at (0,0) spawned one Builder ever); the Core is 2×2.

### Matching the online signature vs tempest_fast
**21:13 Lucas: "Does it win against tempest_fast like the online version does? If not, find out why."** Real Pantheon vs tempest_fast: 14/15 (93%), kills ~round 38.
- At `PANTHEON_RAIDERS=2`: 35/42 (83%) @ median 42, and it lost `longship` (which plain ragnarok wins at r26). **Three raiders** → 88.1% (37/42) @ 37; longship W33; strictly better everywhere (panel 56.3%, was 49.2%).
- `showdown` (Cores 6 apart) exposed a doctrine clash: ragnarok's **BLITZ** (all-attack, no economy, nobody home) dies at r21, while Pantheon plays its same fixed opening plus home Gunners r6–9 and wins r42 — the opening is map-invariant 150/150, so BLITZ contradicts it. Routing close-core maps to FORTIFY: showdown L21 → W34. Result: **90.5% (38/42) @ median 37** vs the real bot's 93% @ ~38.
- **21:26 Lucas:** per-map deltas vs the real games are all worth exploring. The comparison found `twins +23`: the replica built relay Launchers r4/r9/r12 while **Pantheon builds exactly one Launcher per game (151 across 150 replays)** and its raiders walk. One-pad rule + doctrine-aware ring cap: twins 44 → 21 (**exact**), aurora 43 and longship 27 also exact; bridge needed the second pad back (L50 → W95; the real Pantheon doesn't kill on bridge either — its win ran to the r1000 tiebreak). `sweden` stayed +194 (r212 vs r18); a pad-siting heuristic by throw-disc *area* made other maps worse (twins 21→27, aurora 43→50) and was reverted as a measured failure.
- **21:40 Lucas's hypothesis: they choose the pad position to shorten the thrown bots' path.** Implemented as scoring ring sites by the shortest walk from the best reachable landing tile to the enemy Core — after fixing a missing `LAUNCH_RANGE_SQ` import whose `NameError` had been silently producing garbage — **sweden 212 → 33**. Final per-map: 3 exact matches (twins r21, aurora r43, longship r27), median delta +2 rounds, outcome agreement 12/13 (only `duel` diverges, in our favour). 90.5% @ 34. Wider panel 54.8% (100% starter, 23.8% ragnarok, 40.5% vigil).

### Held-out validation and the counter-battery negative result
**21:47 Lucas: "Continue analyzing, also pull in the latest matches again."** 70 new matches → 125 fresh replays (still Pantheon v16), used as a held-out set. Every measured constant replicated: Launchers per game = 1 (122/125); Launcher lifetime = 5 (122/125); pad one cardinal step from the r0 Builder (125/125); throws on r2,3,4,5 (129/132/131/109); max-range 62%; landing BFS-optimal 66%; opening r0–3 exact 82% (rest an r3-gunner variant); **farthest-tile tie-break 76/76 — 179 total confirmations, no counterexample**.

Lucas's turret hypothesis confirmed quantitatively: of Pantheon's Gunners built **>4 tiles from the enemy Core, 80% are aimed directly at an enemy gunner** (overall: 38% bear on an enemy gunner, only 15% on the Core) — counter-battery, exactly as he said. The replica: 0%. But three implementations all failed: `_engage_with_turret` cap 1 → 76.2% vs tempest_fast; cap 3 → 71.4% (it fires wherever a Builder stands, diverting raiders en route); siege-only fallback → 85.7% vs 88.1% and lifted far-gunner aim 0% → 67%, but cost vigil 40.5% → 23.8% (panel 49.2%). All reverted; `_build_counter_battery_gunner` left in the file **uncalled** with the measurements written above it. Missing: whatever makes those ~3 turrets per game affordable for Pantheon — next attempt should measure *when* it builds them, not guess placement a third time. Closing note: the ladder moved under both bots — Pantheon 1980 → 1940, us 1703 → 1641 (rank 8 → 13).

---

## Session 3 — 3c067fac-1c4e-4e05-b308-d4b751e0e270
**Start 2026-08-03T21:47:27Z, interrupted 21:54:28Z. ~7 min.**

Lucas: "Start a match in my browser between the pantheon clone and heimdall." The assistant began figuring out how to run a local match with a browser viewer; Lucas interrupted the request ~6 minutes in. Nothing was completed or concluded. (Related to the competition but effectively content-free.)

---

## Chunk synthesis

**Load-bearing insights (with evidence):**

1. **Every Launcher is +10% on every future price, and the bill lands on Gunners and Harvesters — the only things that win.** Found by chasing why atlas-less `ragnarok_fair` beats valkyrie 25/42 while `ragnarok` draws 21/42 (it cannot ferry, so it walks: 3 Launchers/2 Harvesters/7 Gunners vs 6/1/4 on aurora). Both cap optima are interior: relay cap 1 and ring cap 2; worst-target map rate 5% → 33%. (Session 1, ~17:40–17:52.)
2. **Nash support and mElo pull apart.** warden_walk entered the Nash core at 0.5 (with vigil@e22eda8) while carrying the lowest mElo/win-rate of the top seven — the caps sell 40/42 matchups (vigil@60d5afa −24pp, vanguard_oracle −19pp) to buy 21/42 ones (ragnarok_fair +14pp). Lucas then redefined the bar: **highest mElo AND sole Nash core.** (Ledger: 98 bots, 285,183 matches, 18:05.)
3. **The conditional launcher cap is a frontier, not a knob**: aegis (cap routine ferrying, uncap stuck-recovery) just slides along it — warden 48, aegis 47, threshold-5 49, warden_walk 50 on the prospect+ragnarok_fair pair. (Session 1, 18:40.)
4. **Builder-respawn bug (steward):** the heartbeat only proves one Builder alive, so a team losing 2 of 3 never replaces them — dies at T103 holding 358 banked Ti against an opponent that mined nothing. Bank ≥110 Ti as respawn trigger closes the mode (0 of 38 losses die holding ≥100 Ti). But the "off the frontier" claim was a narrow-panel artefact: on the standard 168-game panel refill is +2 (noise). (Session 1, 18:41 and 21:24.)
5. **Reactive home guard +29, static home guard +1.** heimdall's `_guard_home` (build an aligned Gunner on sighting an enemy within r²=36) scores 147/168 vs control 118/168; bastion's pre-placed guess-facing Gunner scores 110/168 vs warden's 107. Aiming at something seen ≠ aiming at a guess. Also resolves the refill contradiction: refill is neutral alone, ruinous (147 → 85) beside the reactive guard because both sides then trade bodies at +20% scale per replacement. (Session 1, 21:21–21:25.)
6. **The atlas (map oracle) is inert off-pool:** on 24 generated maps, warden_walk, valkyrie and ww_fair all score exactly 46/96 (0.479) while heimdall (fair + guard) gets 65/96; worth 11–13pp on known maps, zero on unknown. Corollary recorded: *a flag measured on a bot that has the oracle is not measured for a bot that does not* (ferry-at-guess re-measured atlas-free: 128 on vs 119 off, reversing the earlier 17/42-vs-21/42 rejection). (Relayed in session 1, 19:56, from the concurrent heimdall agent's NOTES.)
7. **Pantheon's opening is fully characterised and is a net cost against our field.** 100% invariant (150/150; 82% on 125 held-out with an r3-gunner variant); one Launcher per game (122/125), self-destructs after 4 throws (122/125); throws at max range dist_sq ≤ 26; landing tiles BFS-minimal with a farthest-tile tie-break (179/179). Faithfully adopting it costs ~19 panel points on a ragnarok fork (68.3% → 49.2%). (Session 2.)
8. **pantheon_replica_day3 matches Pantheon's online signature vs tempest_fast:** 38/42 (90.5%) @ median round 34 vs the real 14/15 (93%) @ ~38; per-map outcome agreement 12/13 with three exact kill-round matches (twins 21, aurora 43, longship 27) after (a) PANTHEON_RAIDERS=3, (b) one-pad rule, (c) close-core maps to FORTIFY not BLITZ, (d) Lucas's pad-position-by-delivery-path hypothesis (sweden 212 → 33). (Session 2, 21:13–21:45.)
9. **Pantheon's far turrets are counter-battery** (Lucas's hint, confirmed: 80% of Gunners >4 tiles from the enemy Core aim at an enemy gunner) — but three implementations all lost more than they gained (best: 85.7% vs 88.1% vs tempest_fast, vigil 40.5% → 23.8%); the affordability condition is unidentified. `_build_counter_battery_gunner` left uncalled with measurements. (Session 2, 21:49–21:59.)
10. **Deterministic replay reproduction beats aggregate statistics.** Lucas's idea: rerun our real ladder games (tempest_fast vs Pantheon) locally with the clone in Pantheon's seat and diff actions. It exposed a clone that matched every histogram yet reproduced 17/180 rounds, and yielded the √8 spawn radius, the launcher-one-step-out rule, and the 2×2 Core. (Session 2, 18:34.)
11. **Downloaded ladder replays have stdout stripped server-side** (648 BotOutput messages, 0 stdout across 20 replays) — the earlier "we can read Pantheon's debug prints" claim was false and was corrected in three places. What survives: **execTimeUs per unit per round** — Pantheon runs 304–1,749 µs, nowhere near the 10 ms budget. (Session 1, 16:02.)
12. **Partial cluster runs mislead — twice in one session**: "ragnarok line loses to vigil line" from a 2/10 sample (truth: 24/42), and warden at 90.5% partial (truth: 89.0%). Rule recorded: a run is partial until matches.csv reaches the planned count. Narrow opponent probes mislead the same way (steward), and Lucas called it out both times. (Session 1.)
13. **A swallowed exception nearly shipped a broken bot**: a missing import made `_keep_ammunition` throw NameError every round inside `except Exception`; the bot scored 1/42 with 0 ammo all game and never crashed. Same trap hit session 2 (`LAUNCH_RANGE_SQ` NameError almost falsified Lucas's correct pad hypothesis). Grep fresh replays for `reason=NameError` before trusting any run. (Both sessions.)
14. **Cheap regressions recovered on canonical bots:** working-tree vigil had been regressed 15/42 by its own last commit (`64e40cba4`, RING_COVER_SHELL True); flipping it back (`c71a543fc`) restored an exact 21-map mirror, validated on a complete 4,032-match cluster sample (88.7%). The 4-builder opening was rejected in both directions (econ2 81.1%, atk2 83.2% vs 89.7%). (Session 1.)
15. **Pantheon's barriers are offensive damage sponges** (31/33 in an enemy Gunner's ray, rebuilt on the same tile, 3 Ti soaking 6 enemy ammo), and turn order is exactly id order (421/421). Ported defensively-mirrored version is neutral on the short-game pool (11 occurrences/42 games). (Session 1, 16:31–16:38.)
16. **The multi-agent working agreement was born here**: session 1 mistook the concurrent sessions' bots (heimdall, pantheon_clone, pantheon_replica_day3) for anomalies; Lucas ordered the rules written to untracked `CLAUDE.local.md` (mind your own business; repo over stale memory; specific-path adds only) and forgave the held-out-map enumeration while barring a repeat. (21:04.)
17. **Cluster hardware is ~1.5× slower than the laptop** (valkyrie max turn 5,944 µs on cluster vs 3,993 µs local against the 10,000 µs limit) — local timing headroom overstates real headroom; the launcher caps incidentally bought CPU (4,198 → 2,994 µs worst builder turn). (Session 1.)
18. **Evaluator operational facts:** pushed bots defer behind in-flight runs (valkyrie sat behind the hand-launched `secret-eval-1`, 4,283 elements, jobs 29015696–29015700, stalled 5 h); a typical auto run is ~4,000 matches/bot and dispatches to DTU HPC within minutes (job 29021928: 3,040/3,906 collected in ~3 min). (Session 1, 15:59–17:05.)

**Loose ends at chunk close (2026-08-03 ~22:00 UTC):**
- **bastion, steward and aegis were never rated on the cluster** (deferred all day); warden_walk@285d32644 (ring cap + ray avoidance) and warden_walk@e55aab5 also unjudged at last check. The 70%/sole-Nash bar stood at 33% worst-case local, nowhere near met.
- The one unexplored combination from the guard/refill interaction: **heimdall + refill gated to when the guard isn't trading bodies**.
- Counter-battery: what makes Pantheon's ~3 mid-siege turrets affordable is unidentified; next step is measuring *when* it builds them.
- pantheon_replica_day3 remaining fidelity gaps: throws land r3–5 vs Pantheon's real r2–5 (the +2 median delta); the self-destruct rarely fires on the ragnarok chassis; sweden still +15; `duel` diverges (we win it, Pantheon lost it).
- Ladder drift: Pantheon 1980 → 1940, us 1703 → 1641 (rank 8 → 13) with tempest_fast still our online submission.
- Session 3's browser match (pantheon_clone vs heimdall) was interrupted before anything ran — presumably picked up in a later session.
- Uncommitted `pantheon_clone` working-tree edits (6 files, +144/−24, correcting the "92 raiders built exactly four" analysis artefact) were live at chunk close — matching this conversation's own git status, so still in flight the next day.
