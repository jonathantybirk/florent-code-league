# Codex sessions — 2026-08-01 evening (21:00 local) through early 2026-08-02

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

Chunk F of the historical digest. These are the LAST Codex CLI sessions on record; after 2026-08-02
work moved entirely to Claude Code. All in-log timestamps are UTC; session filenames are local
Europe/Copenhagen time (UTC+2). Both are given below where useful. Several sessions ran
concurrently with each other and with Claude Code sessions on the same checkout.

Recurring identities (defined once): **tempest_oracle_ferry@7196487** — Lucas's bot combining the
tempest line with an embedded map atlas ("oracle") and a Launcher ferry mechanic; its live source
tree is `bots/luc/tempest_reinforcements`. **tempest_reinforcements** — the active working
descendant of tempest_oracle_ferry that session 7 develops. **vanguard_oracle@902be71** — the
strongest vanguard-family bot, new #1 mid-chunk. **autistimusprime@ecd4d24** — a top-scoring
opponent bot. **v5** — Lucas's currently active ladder submission (never changed this chunk).
**AvA** — agent-vs-agent rating (pool all maps per bot pair, then logit); **AvT** — the
agent-vs-(opponent,map)-task rectangular rating that this chunk deletes.

---

## Session 1 — rollout-2026-08-01T21-09-28 (21:09 local; UTC 19:09:38 → 22:49:58, ~3h40m)

**Goal (evolving):** understand Nash averaging → simplify the rating model to AvA-only → rebuild
and repeatedly deploy the public rankings website → publish newest tournament data → investigate
the Gold/Silver side balance.

**Narrative.**
- Opened as Q&A: "How are the full nash averages calculated?" Codex explained the then-default
  rectangular AvT construction (bot × (opponent,map) tasks, add-half smoothing
  P = (W+0.5)/(G+1), centered log-odds, maxent Nash of the zero-sum game; `nash_average_i =
  (S q*)_i`) and the aggregate AvA alternative (`A = logit(P)` antisymmetric, `nash_average = A p*`,
  core bots tie at 0).
- 19:15:45Z, Lucas: "Remove the bot + map task angle, I thought we collapsed the 48 matches to a
  single win or lose when doing nash averaging but we don't." Codex **deleted the rectangular AvT
  solver entirely** — AvA pooled probabilities became the sole mElo/Nash path; the website's
  rating-view switch and all `aggregate_*` columns were removed; `AGENTS.md` was rewritten (the
  new AvA-only text already appears in session 2's context at 19:25Z). 95 tests passed, including
  a new regression proving a 2–1 result across three maps contributes three match scores yielding
  smoothed probability 2.5/4, not one binary "series win". Canonical
  `tournament/runs/jon-vanguard-818f3b4/ratings-distinct.csv` regenerated.
- 19:31–19:46Z, website restructure per Lucas: Nash core cell shows `#1` instead of `100.0%`;
  by-opponent / by-map / opponent×map become separate routed pages; map labels get dimensions
  (e.g. `Atoll (18×18)`); new map-centric ranking pages computed from that map's two side-swapped
  games per opponent; official visualizer reused (128×64 dimetric projection + packaged sprites)
  for map renders and hover previews. A real numerical edge case surfaced: two maps' two-game
  matrices have highly degenerate Nash polytopes and the SLSQP maxent solve stalls — an
  entropy-dual fallback was added to the core AvA solver. 96 tests pass; all 21 map datasets had
  48 entrants × 94 games each.
- 19:50Z, Lucas: "Locally? No, edit for the live website." Deploy saga: push `878e19b` to
  portfolio `main` → Cloudflare Pages build failed (a Pages-style `_redirects` rule rejected as an
  infinite loop) → rule removed, Worker's own fallback extended to `/botrankings/map/...` →
  deployed directly via Wrangler; success at commit `a4d7f3b`, Cloudflare version
  `25b55baf-cb5f-4070-ac04-0064ef0e274a`. Live at lucasrgpedersen.com/botrankings/ (Atoll page
  verified: 48 rankings, 94 games per bot).
- 20:06Z, Lucas's UI spec: remove the Nash-rank column; highlight Nash average as the best metric;
  make ratings explanations a dropdown with both short and deep mathematical explanations; remove
  the three overview boxes; put "Every distinct bot plays every official map as both Gold and
  Silver. All match scores are pooled into one head-to-head probability per bot pair before mElo
  and Nash averaging." into the expanded box; keep the statistics "48 distinct bots · 47,376
  matches / 21 maps · updated 8/1/2026, 9:43:14 PM". Also reported: the large map viewer showed a
  random image and shuffled core placement — root cause was stale derived SVG state (thumbnails
  mount per map, the large viewer is reused across routes); made projection data reactive.
  Deployed as commit `8e7f101`, version `2cd632b3-9e0e-4089-b1dd-52f991ecd371`.
- 20:19Z: "Copy inspection prompt" button added — samples up to 10 matches from the current view
  (2 for an exact opponent×map). Commit `058a95d`. 20:39Z: Lucas wanted it smaller/in the table —
  compact per-row "Copy prompt" action added (commit `7e484b0`). 20:45Z Lucas corrected the
  content: not a preselected evidence list but an operational instruction — "Open 10 random
  matches between name@commit and name@commit [on map]" plus how to do it with the documented
  `fcode run BOT_A BOT_B [MAP] --watch` (Codex settled on
  `uv run fcode run … --seed 1 --tle 0 --watch`, fallback `uv run fcode watch <replay>`). Commit
  `1ff2ce8`. 20:52Z: remove point 5 (analysis/reporting) from the prompt; map optional; random
  maps use `--map-random` (omitting the path without it selects the first map). Commit `abe2c8a`,
  version `d7036d29-44ea-4b51-83a8-77530687a246`.
- 20:28Z "Push, and afterwards push the newest data" → 20:29Z correction: "Sorry, I meant the
  changes to x/tournament." Pushed in order: `bcd449f` (AvA rating migration on x/tournament),
  `c814f7b` (newest completed evidence: run `new-code-fdc1e1f` adds 14 challengers to the 48-bot
  field; four redundant newcomers removed by the incumbent-first duplicate policy → **58
  deduplicated bots, 69,426 matches, 21 maps, exactly 2,394 games per bot**; the schedule's
  `vanguard@c407e79` proxy normalized to canonical `vanguard@26e6792` in the distinct matrix only),
  `24f319d` (regenerated website data; version `30407f6f-4c3f-4495-9f3d-6a0242961b7a`). The
  in-flight Elias run was **22.1% complete** and deliberately left unpublished.
- 21:03Z "When the current eval run is done upload results to the website." Codex found a
  completion-accounting edge case: the run id had been replanned, and **4,259 stale result files**
  from the earlier schedule made the watcher declare completion while **167 matches** of the
  current schedule were missing; exactly those gaps were resubmitted (five unusually long matches
  last). The finished challenger schedule had used three previously proven duplicate aliases;
  these were canonicalized in `matches-distinct.csv` only, the removed training bot
  `opponent_luc` was excluded, and the newly confirmed duplicate `v233_i@902be71` collapsed.
  Result: **69 distinct bots, 98,532 rating matches, all 2,346 pairs at exactly 42 games; new #1:
  vanguard_oracle@902be71**. Commits `00d1fe1` (tournament), `9c82958` (website), deployment
  `65db3d2b-0193-43e4-9c4d-97b988f12f09`; 96 tests pass.
- 22:30Z (after local midnight), Lucas: is the Team A/B → Gold/Silver mapping correct? "I
  consistently see bots doing better as team silver." Verified end-to-end: `BOT_A` → engine Team A
  → website "Gold"; the mapping is right and **the Silver advantage is real**: Team A/Gold scores
  48.99%, Team B/Silver 51.01%; **43 of 69 bots do better as Team B**; map-dependent — Team A
  scores 42.63% on Strait but 56.99% on Atoll; vanguard_oracle@902be71 scores 77.59% as A vs
  89.01% as B. Separately found a **visual bug**: official terminology is A/Orange and B/Blue, but
  the site's map preview assigns the blue/silver core artwork to A and orange to B (calculations
  unaffected). 22:48Z follow-up: confirmed from a replay's update order that **Team A acts first
  each round**, so the first-moving side does slightly worse: Gold 48,267 wins (48.99%) vs Silver
  50,262 (51.01%), 3 draws — though causation (move order vs starting position vs team-specific
  bot logic) was explicitly left unproven.

**Lucas's directives recorded here:** kill the AvT rating view; deploy to the live site, not
locally; the exact overview text and preserved statistics line quoted above; inspection prompt as
operational instruction with `fcode run --watch`; push meant x/tournament, not portfolio data.

---

## Session 2 — rollout-2026-08-01T21-25-31 (21:25 local; UTC 19:25:34, minutes)

**Goal:** one question — "What is nash core?" Codex defined it: the set of bots with positive
probability in the maxent Nash mixture; `nash_prob = 0` means core bots cover that bot's
strategic value; cited the repo's example of tempest being 11th by mElo yet sole Nash-core bot.
No code changed. (Notable only as evidence the AvA-only AGENTS.md rewrite from session 1 had
already landed by 19:25Z.)

---

## Session 3 — rollout-2026-08-01T21-38-00 (21:38 local; UTC 19:38:40 → 19:56:29, ~18m)

**Goal:** explain why tempest_oracle_ferry ranks #1 by Nash but 11th by mElo, then put those
explanations on the website.

**Narrative.**
- The data: tempest_oracle_ferry is the **unique Condorcet winner** — it won **all 47 head-to-head
  series**, closest 25–17 against vanguard_oracle — so `nash_prob = 1.0` and it ranks first by
  Nash; its mElo is only **1.9129 (11th)**. `vanguard@9932bec`, #1 by mElo at **2.353**, lost
  **14–28** to Tempest but recorded **22 perfect 42–0 sweeps** (Tempest had only four). After
  smoothing, a 42–0 sweep contributes **+4.443** log-odds while the 14–28 loss contributes only
  **−0.676** — mElo rewards average dominance, Nash asks "can you be counterpicked". Underlying
  row: `tournament/runs/jon-new-818f3b4/ratings.csv`.
- Lucas: "Can you describe these and the melo_r on the website?" Codex added a visible "How to
  read the ratings" guide plus hover text on table headings (Nash weight is not confidence; core
  bots score zero; mElo rewards lopsided series). This session, running concurrently with session
  1, hit the same Cloudflare failure and actually produced the diagnosis both sessions used: the
  pending map-page work's catch-all `_redirects` rule rewrites its own target; Cloudflare rejects
  it as an infinite loop, and per Cloudflare docs `_redirects` is not applied to Worker-served
  requests anyway — the rule was removed and Worker-based deep-link routing kept as the single
  mechanism. Explanations deployed live.

---

## Session 4 — rollout-2026-08-01T22-34-03 (22:34 local; UTC 20:34:11 → 20:35:32, ~1m)

**Goal:** Lucas: Claude (Code) is running `uv run python -m tournament hpc submit --tid
new-code-elias-902be71 …` — "Can you see what status is without interfering."

**Narrative.** Read-only checks only: the submit process was alive ~6 minutes; array 1 accepted as
LSF job `29003316` with all **1,000 elements pending**; it was waiting for `bsub` to accept array
2 (**642 elements**); across the tournament LSF showed **219 running and 3,375 pending** elements.
Verdict: consistent with the cluster's submission/pending-job throttling, not a crash. Nothing
was signaled, modified, submitted, or cancelled. (Direct evidence of Codex and Claude Code
operating the same repo simultaneously, with Lucas coordinating them by hand.)

---

## Session 5 — rollout-2026-08-01T23-32-23 (23:32 local; UTC 21:32:25 → 21:42:24, ~10m)

**Goal:** execute three website-generated inspection prompts (the button built in session 1) —
open replays via `fcode run --watch`.

**Narrative.**
- "Open 10 random matches between `vanguard_oracle@902be71` and `tempest_oracle_ferry@7196487`":
  42 eligible rating rows existed (21 official maps × both orders); sampled maps vault, string,
  hive, vault, bridge, strait, quarry, hive, aurora, jackpot — six Tempest-as-Gold, four
  Vanguard-as-Gold. Match IDs `b73535ebb21dae9f`, `5794dc32e5ca85a9`, `54f066782e2a2c80`,
  `4c3f7d04fa93e338`, `adb5e43f2415e70c`, `3ab6f51a61a8d0ed`, `94e589a509697bf9`,
  `e98467f4d4017b15`, `b380cd110246446e`, `aa0677eafdf0ff21`. All ten reran with exact staged
  commits, seed 1, TLE 0; ten local visualizer servers left live.
- "Open 2 random matches between `vanguard_oracle@902be71` and `autistimusprime@ecd4d24`": drew
  strait (`655e3f7a34867de5`) and crossfire (`2cc162dcaa3f6656`); autistimusprime was Gold in
  both sampled rows.
- "Open 2 random matches for `tempest_reinforcements@87724ec`": drew `undertow_oracle@fdc1e1f`
  (Gold) vs Tempest on strait (`f48a55196bc479c3`) and `e_condc@6db8844` (Gold) vs Tempest on
  sweden (`a0d700d880aaf062`).
- Prompt-template quirk noted twice: the copied text says "sample 10" even when the headline asks
  for 2; Codex treated the headline count as authoritative.

**New names:** `undertow_oracle@fdc1e1f`, `e_condc@6db8844` (opponent bots);
`tempest_reinforcements@87724ec` (pinned pre-session-7 revision); maps sweden, crossfire, string,
vault, hive, bridge, aurora, jackpot, quarry, strait.

---

## Session 6 — rollout-2026-08-01T23-47-08 (23:47 local; UTC 21:48:15 → 21:49:39, ~1.5m)

**Goal:** Lucas: "I think a lot of things that are gitignored on x/tournaments isn't on x/luc, can
we fix that?" (then "And push ofc").

**Narrative.** The intended ref is `x/tournament` (singular — no `x/tournaments` exists). Its
extra ignore rules — generated tournament staging, maps, results, logs, replays, scheduler files,
automation state — were carried onto `x/luc` while preserving x/luc's broader ignores; durable
manifests/ratings/match/compliance CSVs remain trackable. The previously untracked `tournament/`
noise vanished from `git status`. Commit `e9a35e1` "Ignore generated tournament artifacts",
pushed to origin/x/luc.

---

## Session 7 — rollout-2026-08-01T23-49-17 (23:49 local; UTC 21:49:30 → 23:52:17, ~2h; the chunk's big bot-development session)

**Goal:** understand tempest_oracle_ferry's communication-store protocol, then implement Lucas's
launcher-relay redesign in `bots/luc/tempest_reinforcements`, iterating from replays.

**Narrative.**
- **Store map (at commit 7196487), all 16 global communication slots:** 0 = monotonic Builder
  ticket assigning roles (Builder 0 economic, later ones attackers/scouts); 1–8 = packed
  ore-position claims (deconfliction); 9–10 = shared 3-bit masks of rejected map-symmetry
  hypotheses (fallback when the embedded atlas can't identify the map); 11 = expiring construction
  lease serializing long conveyor routes; 12 = Core-damaged alert; 13 = packed enemy-Core position
  (from oracle, sighting, or symmetry); 14 = packed friendly-Core position (lets new Builders
  identify the map via the atlas); 15 = ferry request (entity ID of the Builder asking to be
  launched). The full oracle map is NOT in the store — it's static in `atlas_data.py`. Gunners and
  Sentinels don't use the store; titanium/ammo are engine-managed pools.
- 21:54Z, Lucas's relay spec: build launchers all the way to the enemy base, but only construct
  one if none is visible to the agent; otherwise announce the agent's id and a destination (8
  compass directions suffice; the launcher should launch maximally in that direction); prioritize
  being first at the enemy base — unless the enemy base is close ("within 7 units or something").
  Engine facts verified: Launchers have no facing, pick up an adjacent Builder, and throw within
  **radius² 26** from the Launcher. Implemented: relay chain in the lead attacker; no construction
  while a friendly Launcher is visible; direction encoded in a store slot; Launcher picks the
  legal landing tile with maximum forward projection; relaying stops within **7 Chebyshev units**
  of either Core; relay construction may spend down to the Launcher's actual cost while ordinary
  "I'm stuck" ferries keep the old **60-titanium reserve**; old Launchers self-clean after six
  idle rounds. Launcher suite 10 passed; wider suite 57 passed + 15 subtests (one pre-existing
  nondeterministic `bot_1` vs `starter` failure, untouched).
- 22:04Z: stuck-path fallback ordered: (1) build a launcher if possible, (2) kill blocking enemy
  units with a turret. Also: open 2 matches vs autistimusprime; benchmark vs top scorers
  vanguard_oracle@902be71, autistimus_prime, tempest_oracle_ferry@7196487. Then 22:09Z, Lucas,
  urgently: **"DO NNot SUBMIT!"** Codex confirmed nothing was submitted and that any unrated
  challenge would use the already-active **v5**; all benchmarking stayed local (mirrored 42-game
  set per opponent = 126 games, seed 1, 10 ms turn limit).
- First benchmark run invalidated by a pre-existing deterministic crash in Tempest's
  gunner-placement tie-breaker (raw `Direction` objects compared on ties); fixed, rerun. The two
  requested Crossfire games vs AutistimusPrime were **lost in 28 and 24 turns**. Clean 126-game
  benchmark: **17–25 vs AutistimusPrime, 14–28 vs Tempest Ferry 7196487, 10–32 vs Vanguard
  Oracle 902be71**. Lucas watched the two Crossfire games (ports 36045/36307).
- 22:28Z, Lucas from frame 5 of the 36045 game: any launcher should throw enemies in range as far
  from our base as possible; a new bot role should build a **row of launchers spaced with 2 tiles
  between** (so enemies can't pass); and fix that only one attacker uses the relay — "bot with id
  8 could have gotten launched but ends up walking." Codex verified **Launcher pickup is
  team-blind** (the official docs wrongly say friendly-only), found the exact bug — `_opening_ferry`
  excluded every attacker except Builder index 1, and the store had only one request slot — and
  replaced it with **seven stable per-Builder request slots**. Launchers now shove adjacent
  enemies away from the friendly Core before servicing the friendly queue; the fifth opening
  Builder builds a center-out Launcher screen at pitch three. The mirrored Crossfire check
  **flipped 0–2 → 2–0** (wins at rounds 270 and 130). Rebenchmark (after fixing three contaminated
  games: a stale call to the removed self-scrap helper, plus the same Direction tie-break in
  defensive placement): **25–17 vs AutistimusPrime, 27–15 vs Tempest Ferry, 20–22 vs Vanguard
  Oracle** (from 17–25 / 14–28 / 10–32).
- 22:39Z, Lucas: the wall builder stops executing — it should finish the wall then build
  harvesters; bots should navigate around enemy launchers and consider launching themselves over
  them; **"No reason to do the full benchmark before I ask for it. Also, commit for every change
  we make. So commit and push now."** Implemented (wall completion releases the builder into the
  economy state machine; the eight pickup-adjacent tiles around remembered enemy Launchers are
  navigation hazards; emergency self-ferry built on a safe adjacent tile). Commit `2073835a0`
  "Improve Tempest launcher coordination and recovery", 25 focused tests.
- 22:45Z, Lucas: if no safe launch exists (nowhere without launchers), build turrets where
  reachable; if the enemy core is unreachable, build a turret to destroy the enemy launcher
  first, then use the freed space. Implemented as a full fallback chain: unsafe maximal landing →
  shorter safe landing → explicit rejection carrying the blocking Launcher's coordinates in the
  per-builder slot → reachable Core-firing Gunner → dedicated Launcher-demolition Gunner. Commit
  `f7ccf69a8` "Add safe launcher assault fallback", 29 tests.
- 22:55Z, Lucas: in game 36849 Builder id 3 is stuck most of the game ("maybe not enough
  titanium?"). Replay diagnosis: not titanium — a **diagonal-adjacency bug**: `_goto` treated
  squared distance 2 as build range, but construction is cardinal-only, so
  `can_build_harvester()` was false and the builder no-opped from round ~2 through round 269 even
  with titanium at 60–70. Fixed; in the exact geometry the builder moves round 4, builds the
  Harvester at (1,14) round 5, and the reproduction wins at turn 193. Commit `e1dc31634` "Fix
  diagonal harvester approach stall". Two fresh games vs autistimusprime opened: **won turn 193
  and turn 190** (a first — the same matchup was 0–2 earlier in the session).
- 23:05Z, Lucas: Builders 3 and 15 both stand still all game; add fallback logic for all blocked
  builds (wait a few ticks if the blocker is mobile), prioritize not building on ores, and add an
  automated flag when a bot stands still >5 ticks. Diagnosis: Builder 15 waited for wall-Launcher
  titanium while standing ON ore (5,13); Builder 3 wanted a Harvester on that same occupied ore —
  a mutual stall. The new diagnostic then exposed a second stall class: indefinite affordability
  waits ("needs 51 titanium"). 23:15Z, Lucas: **"No titanium is a fair stall"** — affordability
  waits exempted from the alarm. 23:16Z, Lucas: don't build turrets when team ammo **< 20**
  (ignore titanium), and don't build a turret whose shot is obstructed. All implemented: waiting
  builders vacate ore; mobile blockers get a 3-turn grace then replan; permanent invalid sites
  rejected; >5-round non-titanium inactivity emits a replay diagnostic (id, position, phase,
  task, target, reason); every Gunner placement needs ammo ≥ 20 and a clear hypothetical shot.
  The reproduction match now **wins at turn 108**. Commit `edf93ad3e` "Recover blocked builds and
  gate gunner placement", 36 tests.
- 23:19Z compliance (run via the x/tournament worktree): **704 unit-turn samples on atoll, duel,
  quarry; median 0.126 ms; p75 0.809 ms; max 5.778 ms** against the 10 ms limit ("close" marked
  at 9 ms); zero timeouts/exceptions. No speedups warranted.
- 23:22Z, Lucas ran the crossfire match himself: unit 15 stalls. Diagnosis: a **resource-policy
  deadlock** — round 9: 21 Ti vs launcher cost 49; round 64: 60 Ti vs cost 61; round 107: 60 Ti
  vs cost 68. The Core converts titanium above a hardcoded 60 reserve into ammunition while
  scaling keeps raising the launcher cost past the reserve, so the wall builder can never afford
  it (and the stall detector correctly suppressed it as a titanium wait). A blunt fix (reserve
  the current cost) built at round 64 but regressed the match 108 → 145 turns, so it was NOT
  committed at that point; Codex proposed spawning the wall builder earlier and making ammo
  conversion construction-aware instead.
- 23:36Z, Lucas: turrets must also not block other turrets that are hitting their target; Builder
  3 stuck again despite ample titanium; and "Bots should print debug information if they fail…
  and write why." Implemented `PLAN_FAILED` replay records (unit, round, phase, action, target,
  reason, resources vs scaled cost, retry count); the firing-lane safeguard applied to defensive,
  blocker, core-attack, and launcher-demolition Gunner paths; and the Core reserve changed to
  **track the current scaled Harvester/Launcher cost** (Builder 3's Harvester had scaled 51 → 57
  → 68 while conversion pinned the team at 60). Builder 3 now builds at round 76; the match still
  wins but takes 145 turns instead of 108 (more titanium retained for construction). Commit
  `51ad53062`; 50 tests; compliance re-run max 6.126 ms.
- 23:45Z, Lucas: online validation says tempest_reinforced goes over time in the worst case (10 ms
  max; p75 was 2 ms). Reproduced exactly: **Atoll round 32, attacker Builder 8, 10.670 ms**
  during turret-site selection — 100+ per-candidate whole-map BFS runs plus per-candidate
  firing-lane rescans. 23:46Z, Lucas: "Seems easy to just use an a_star instead of bfs?" — Codex
  pushed back: the problem is repetition, not per-search cost; **one BFS distance map per
  planning pass** beats 100+ A* searches and preserves the same shortest paths. Result: Atoll
  worst case 10.670 → **1.503 ms**; Vault 9.378 → 1.955 ms; sweep of all 21 official maps:
  **16,502 unit-turns, worst 2.671 ms, zero TLEs**; compliance max 1.647 ms, p75 0.515 ms. Also
  fixed a zero-direction Launcher exception found on Strait (announcing a launch at a Launcher
  already occupying its target). Commit `025dd519f`; 52 tests + 15 subtests. **No submission was
  ever made; no post-fix full benchmark was run (per Lucas's standing instruction).**

**Lucas's directives in this session:** the relay design spec; stuck fallback order
launcher-then-turret; "DO NNot SUBMIT!"; launcher wall spaced 2 apart; fix the frame-5 launch
miss; commit-and-push for every change; no full benchmarks unless asked; "No titanium is a fair
stall"; ammo <20 gates turrets; debug prints on failed plans; the A* suggestion (successfully
argued down to a single-BFS distance map).

---

## Session 8 — rollout-2026-08-02T01-38-54 (01:38 local Aug 2; UTC 23:42:11 → 23:57:39, ~15m)

**Goal:** Lucas: "our rankings allow strategies that go over time. We should add a toggle to
include strategies that go over time or not, default should be off (we will have to recompute
benchmarks for both)."

**Narrative.** Codex recognized this needs two independently rated fields, not a client-side row
filter — removing timed-out strategies changes mElo AND Nash for everyone remaining. Implemented
a default "within time" benchmark (compliance status `exceeded` excluded) plus an
"including over-time" benchmark, for overall and all 21 per-map rankings (each map matrix solved
twice). Work was done against the `x/tournament` code while the checkout sat on `x/luc` with
unrelated in-progress bot edits, which were left untouched; changed files were in the
`florent-code-league-ci` worktree (`site_data.py`, `test_site_data.py`) plus portfolio
`BotRankings.tsx`. Mid-regeneration **a scheduled evaluator started independently and published a
newly completed 73-bot run through the same data directory** — Codex let its lock-protected run
finish rather than interrupt (first sighting of the automated ladder timer in this chunk). Field
counts moved during the session as the new run landed: initially 59 compliant of 72, finally
**61 compliant strategies by default; 73 including 12 over-time strategies**. All 120 tournament
tests pass; portfolio build clean; all 21 map data variants validated.

---

## Session 9 — rollout-2026-08-02T01-47-48 (01:47 local Aug 2; UTC 23:48:35 → 23:56:19, ~8m — the final Codex session on record)

**Goal:** Lucas: "make a pass over all 72 maps published currently and double-check whether they
are fair or not? I.e. do they use knowledge of the known maps or not? … Correct the tags where
relevant." (He said "maps"; the published set is 72 **bot implementations** — Codex flagged the
wording and audited the bots.)

**Narrative.** Audit criterion made concrete: general runtime sensing and symmetry inference =
fair; bundled `.map26` files, embedded atlas data, map-name conditionals, or pre-scouted
enemy-core/terrain seeding = unfair. Only 25 entries had explicit fair/unfair tags before (the
rest carried provenance labels like `legacy`, `archive`, contributor names). Findings: all seven
Elias snapshots actively call an offline atlas; all three Lucas challengers load bundled official
maps; **every Tempest Reinforcements revision embeds the published-map atlas**. Final
classification: **50 fair, 22 unfair**; corrected 47 missing/effective classifications (34 fair,
13 unfair); newly identified unfair: six Elias atlas bots, three Claude challengers, three
Tempest Reinforcements revisions, and `opponent_luc`. Every roster entry now has exactly one
fair/unfair tag in the canonical `florent-code-league-ci/tournament/bots.toml`, enforced by a new
regression test (121 passed). Changes staged for the next publisher run; the already-dirty
portfolio output was deliberately not overwritten or deployed. An unrelated in-progress edit in
`tempest_reinforcements/builder.py` (another agent's) was noticed and left alone.

---

## Chunk synthesis

The evening's arc: Lucas spent his final Codex hours on three fronts at once — (a) simplifying
and publishing the rating system and its public website, (b) turning tempest_reinforcements into
a launcher-relay assault bot through rapid replay-driven iteration, and (c) instituting
governance (over-time toggle, fairness tags) that reframes his own best bot as "unfair".

**Load-bearing insights, with evidence:**

1. **The AvT (bot×(opponent,map) task) rating view was deliberately deleted on Lucas's order** at
   19:15Z Aug 1 ("Remove the bot + map task angle…") — AvA pooled-probability mElo/Nash became the
   only rating path, AGENTS.md was rewritten, and the aggregate_* schema/UI removed (S1; 95→96
   tests). Any later mention of "the" rating is post-this-change AvA.
2. **Pooling ≠ collapsing:** a purpose-built regression proves a 2–1 across three maps enters as
   three match scores → smoothed P = 2.5/4, never one binary series result (S1, 19:20Z).
3. **The ladder leader changed twice within hours as evidence accumulated:** 58 bots/69,426
   matches at 20:36Z, then 69 bots/98,532 matches with **vanguard_oracle@902be71 the new #1** at
   21:15Z (S1). Earlier that same evening tempest_oracle_ferry@7196487 was the sole Nash-core bot
   (nash_prob 1.0, all 47 series won, mElo only 1.9129/11th vs vanguard@9932bec's 2.353) (S3).
4. **The Silver/second-mover advantage is real and confirmed, not a labeling bug:** Gold/A/first
   48.99% (48,267 wins) vs Silver/B/second 51.01% (50,262), 3 draws; 43 of 69 bots better as B;
   map-dependent (A: 42.63% on Strait, 56.99% on Atoll). Team A verified to act first from replay
   update order. Cause not established (S1, 22:30–22:49Z).
5. **Launcher pickup is team-blind, contradicting official docs** — verified in-engine (S7,
   22:31Z) and immediately weaponized (launchers throw adjacent enemies as far from our Core as
   possible). Throw range is radius² ≤ 26; Launchers have no facing.
6. **The frame-5 relay bug was a protocol flaw:** `_opening_ferry` allowed only Builder index 1
   to be ferried and the store had a single request slot; seven per-Builder slots fixed it and
   flipped the mirrored Crossfire 0–2 → 2–0 (S7, 22:28–22:35Z).
7. **The session's benchmark swing is dramatic and honest:** before fixes 17–25 / 14–28 / 10–32
   vs AutistimusPrime / Tempest Ferry / Vanguard Oracle; after the relay-protocol + defense fixes
   25–17 / 27–15 / 20–22 (S7, 22:38Z). No benchmark was run after the later commits — Lucas
   forbade unrequested full benchmarks (22:39Z).
8. **Two silent-stall root causes in tempest_reinforcements were found from replays:** a
   diagonal-adjacency bug (squared distance 2 accepted as build range though construction is
   cardinal-only — builder no-opped rounds ~2→269) (S7, 22:58Z, commit e1dc31634), and a
   Core-conversion deadlock (Core converts Ti above a hardcoded 60 reserve to ammo while scaled
   Launcher/Harvester costs rise 49→61→68 past it) fixed by making the reserve track the current
   scaled cost — at a measured cost: the reproduction win slowed from turn 108 to 145 (S7,
   23:34–23:44Z, commit 51ad53062).
9. **The real 10 ms TLE culprit was repeated search, not slow search:** Atoll round 32, Builder 8,
   10.670 ms from 100+ per-candidate BFS runs during turret placement; Lucas's A* suggestion was
   argued down to one BFS distance map per planning pass — worst case 1.503 ms on Atoll, 2.671 ms
   across 16,502 unit-turns on all 21 maps, zero TLEs (S7, 23:45–23:52Z, commit 025dd519f).
10. **"DO NNot SUBMIT!"** (S7, 22:09Z) — hard standing rule; the active ladder submission stayed
    `v5` all night, and every Codex report thereafter explicitly affirms "no submission".
11. **Lucas's stated working preferences** (this chunk): commit and push every change; no full
    benchmarks unless asked; "No titanium is a fair stall" (affordability waits are legitimate);
    ammo < 20 blocks new turrets; turrets need a clear shot and must not block friendly firing
    rays; failed plans must print why (`PLAN_FAILED` diagnostics); auto-flag >5-tick non-titanium
    stalls.
12. **The website inspection-prompt loop closed the same evening:** the button was built,
    corrected to an operational `fcode run --seed 1 --tle 0 --watch` instruction (S1), then its
    output was executed verbatim in S5 to open 14 replays — one of which (frame 5, port 36045)
    directly drove the S7 relay fix. Known quirk: the template says "sample 10" even for 2.
13. **Run bookkeeping can lie:** a replanned run id left 4,259 stale result files that made the
    watcher declare completion while 167 scheduled matches were missing; only exact
    scheduled-ID accounting caught it (S1, 21:07Z).
14. **Fairness audit reframed the field:** 50 fair / 22 unfair of 72 published bots; every
    Tempest Reinforcements revision, six Elias atlas bots, three Lucas/Claude challengers, and
    opponent_luc are "unfair" for embedded map knowledge (bundled .map26, atlas data, map-name
    conditionals). Enforced by a bots.toml regression test (S9 — the last Codex session).
15. **Over-time strategies are now excluded from the default rankings** via independently
    recomputed mElo/Nash benchmarks (61 compliant vs 73 with 12 over-time included); a
    client-side filter was explicitly rejected as mathematically wrong (S8).
16. **The automated evaluator was already live and racing the humans:** during S8 a scheduled
    evaluator independently published a completed 73-bot run through the same data directory
    (23:55Z) — the botrankings timer later documented in CLAUDE.local.md.
17. **Multi-agent reality:** S4 has Codex passively monitoring a Claude Code HPC submission (job
    29003316; 1,000 pending elements, array 2 of 642 waiting; LSF 219 running/3,375 pending);
    S9 notices and preserves another agent's uncommitted `builder.py` edit.
18. **The tempest_oracle_ferry communication-store protocol is fully documented** (16 slots:
    role ticket, 8 ore claims, symmetry masks, construction lease, core alert, both Core
    positions, ferry request) — the map atlas itself lives statically in `atlas_data.py` (S7,
    21:50Z).

**Loose ends at chunk close (23:57Z Aug 1 / 01:57 local Aug 2):**
- tempest_reinforcements at `025dd519f` carries five commits of fixes (2073835a0, f7ccf69a8,
  e1dc31634, edf93ad3e, 51ad53062, 025dd519f) whose combined strength was never benchmarked — the
  last full benchmark predates them all.
- Nothing was submitted; the ladder still runs `v5`.
- The wall-builder titanium deadlock got the "blunt-adjacent" fix (reserve tracks scaled cost),
  which slowed the reproduction win 108 → 145 turns; Codex's proposed better fix (earlier wall
  builder spawn, construction-aware ammo conversion) was not implemented.
- The Silver (second-mover) advantage is confirmed but unexplained; the map-preview core-artwork
  color swap (A shown blue instead of orange) was identified but not fixed.
- Fairness tags are committed to ci `bots.toml` but not yet published to the website ("ready for
  the next publisher run"); the implication that Lucas's whole atlas-based line is "unfair" is
  unresolved.
- The Elias run (`new-code-elias-902be71`) went from 22.1% complete to fully published as part of
  the 73-bot field during the evening, but no per-bot analysis of its results happened in Codex.
- The flaky `bot_1` vs `starter` test failure (with the starter's out-of-bounds engine error)
  remains unaddressed.
