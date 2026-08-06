# Codex sessions, 2026-08-01, started 13:00–20:00 local (chunk E)

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

All timestamps below are UTC as recorded in the rollout files; local time (Europe/Copenhagen) is UTC+2. Six sessions, all in `/home/Ucals/projects/florent-code-league-llm-rl` (cwd), all Codex VS Code sessions (`codex_vscode`, cli 0.146.0-alpha.3). Sessions 2–6 overlap heavily in wall time; session 2 is the day's backbone.

---

## Session 1 — rollout-2026-08-01T13-37-46 (11:37:46Z–13:11:15Z; 13:37–15:11 local)

**Goal:** Two quick rules/tooling questions. No code changes.

- 11:37Z, Lucas: "How much can a bot heal per turn?" Answer from official docs: a Builder Bot heals **4 HP per friendly entity per turn, costing 1 titanium**; if a friendly bot stands on a friendly building, both are healed 4 HP — up to **8 total HP** from one action. Healing targets one orthogonally adjacent tile and consumes the bot's action.
- 13:11Z, Lucas: "How do we see the replays from our matches on the actual ladder?" Answer: the platform's Matches page or the `fcode` CLI — `fcode match list --type ladder --mine`, `fcode match watch MATCH_ID [--game 3]`, `fcode match replay MATCH_ID --game 3` then `fcode watch MATCH_ID_game_3.replay26` (omit `--game` to download the whole best-of-five series).

New mechanic facts: heal = 4 HP/entity/turn @ 1 Ti; stacked bot-on-building heal = 8 HP; ladder replays are `.replay26` files retrievable per game of a best-of-five.

---

## Session 2 — rollout-2026-08-01T16-15-49 (14:16:28Z–19:13:41Z; 16:16–21:13 local) — the backbone session

**Goal (evolving):** evaluate Jon's newest bots; then a full pooled overview with `x/luc/1`; then evaluate every untested commit; then build a live public rankings website plus a push-triggered evaluation pipeline; then a series of rating-methodology upgrades.

### Phase 1 — "Jon's newest bots against each other" (14:16Z–14:23Z)
Lucas: "Test Jon's newest bots against each other using the eval framework on this branch. Also, pull up 10 random matches of his newest bots against each other." Codex interpreted "newest" as `tempest@ba943b9` vs `mistral@ba943b9` and ran all 21 official maps in both player orders: **Tempest 25/42 wins (59.5%), Mistral 17/42 (40.5%)**, no draws, 79 harness tests passed. Ten seeded-random replays opened (Atoll, Bridge, Duel, Hive, Longship, Quarry, Sprint, String, Vase, Vault). Caveat: both bots emitted caught `TypeError` tracebacks when tuple comparison reached `Direction` values.

Lucas's corrections, verbatim in spirit:
- 14:21Z: "which bots are playing each other? Pretty important detail" — always name the matchup.
- 14:22Z: "But how do I know who is silver and who is gold in the replayed matches" — established convention: **player A is Gold, player B is Silver**; full Gold/Silver table for the 10 replays supplied.

### Phase 2 — pooled 45-bot challenger run with luc_1 (14:32Z–15:17Z)
Lucas 14:32Z: "Read agents.md, you need to test them against all previous bots and give a collected overview of who's best, and also put x/luc/1 in the pool." Reading AGENTS.md corrected "newest" to *bots whose Python actually changed*: challengers = `mistral@ba943b9`, changed `vanguard@ba943b9`, plus `luc_1@604349b` (Lucas's `bots/1` from `x/luc@604349b`, registered in `tournament/bots.toml`). The prior roster was a completed 42-bot tournament at snapshot `da3fd8a`.

- **5,418-match** challenger run submitted to DTU HPC as job **28999261** (271 array elements); ~600 matches/30s at 100 workers; slow tail isolated to `luc_1` vs the legacy unfair `lockin` bot on Quarry/Runestone at ~50–72 s/game.
- Pooled matrix: **45 bots, 990 pairings, 41,580 matches, exactly 42 games per pairing, zero engine errors**, 84 tournament tests passing.
- Two "best" definitions: **`tempest@da3fd8a` won all 44 opponent series (sole Nash-core agent; closest series 22–20 vs current Undertow)**; **`undertow@da3fd8a` had the highest mElo 2.5365 with 83.9% wins** but loses 20–22 to Tempest.
- New entrants: `mistral@ba943b9` rank 13/45, 81.7% win rate, series 42–0–2 — lost only to Tempest (17–25) and `v233_g` (20–22); beat current Undertow 25–17, new Vanguard 27–15, and Lucas's bot 42–0. `vanguard@ba943b9` 80.4%, behaviorally identical to four older Vanguard/v233 variants (split direct matches 21–21). `luc_1@604349b` rank 44/45, 20.9%, series 0–4–40.
- Replay correction: opened 10 random **Mistral vs new Vanguard** replays (with Gold/Silver and winners per map) since that was the real newest-vs-newest matchup.

### Phase 3 — deduplication reprimand and corrected overview (15:17Z–15:22Z)
Lucas 15:17Z: "The new ratings still have duplicates, doesn't the agents.md say to not include duplicates in the matches to save time? ... it should be part of the pipeline to check compliance as well. Also rank the newest additions to jons branch again. Can you sum up how luc performed in every match?"

Corrected run pruned six known duplicates before scheduling (129 → 111 pairings, **756 unnecessary rating matches saved**) and reused completed matches by content-addressed match ID. Final: **38 distinct strategies, 703 pairings, 29,526 matches**, 87 tests passing.
- `vanguard@ba943b9`: mElo #2/38, Nash #9, 83.7%, series 33–0–4, compliance **Pass, 1.670 ms max**.
- `mistral@ba943b9`: mElo #8, Nash #5, 83.5%, series 35–0–2, compliance **Exceeded, 10.119 ms max**.
- `luc_1@604349b`: mElo 37/38, Nash 36/38; overall **357–1,197 (23.0%)**; series 0–4–33; as Gold 218–559 (28.1%), as Silver 139–638 (17.9%); compliance **exceeded, 12.416 ms max, five watchdog timeouts**. Full per-opponent table produced: 21–21 vs Nemesis, Reaver, `vg_v1`, Lockin; down to 0–42 vs current Undertow, Undertow `1ac7ac4`, old Undertow, Vanguard, Tempest, Mistral, `v233_f`, `v233_g`.

(The compliance-probe capability referenced here was built in parallel by session 3 below and had just landed in AGENTS.md/pipeline.)

### Phase 4 — every untested commit ID on x/jon (15:36Z–16:07Z)
Lucas 15:36Z: "Will you please test the newest bots on jons branch. All commit ids we haven't tested yet, not just new names." Jon's branch had advanced `ba943b9` → `de18549` (later `ca710da`). Nine entrants found: five successive Vanguard commits plus **`tempest_fast`, `mistral_fast`, `tempest_ferry`, `tempest_oracle_ferry`** (new Jon variant names). Schedule: 9 challengers × 38 distinct = 378 pairings, 15,876 rating matches + 27 compliance probes; DTU job **29000386**, 796 elements.

Lucas process directives mid-run: 15:42Z "Only report back when its done"; 15:56Z "It's done"; 16:00Z "Just give me the overview."

Overview (10 previously untested commit IDs, 17,808 rating matches, zero engine errors, all passed 10 ms compliance):
- `vanguard@9932bec` mElo rank 1 (81.8%, 40–1–4); `vanguard@17ad456` rank 2 (83.0%, 44–0–1 — lost only one series, called "best fair competitive bot"); `vanguard@26e6792` and duplicate `vanguard@c407e79` rank 3 (79.6%, 37–0–8); `vanguard@259c188` rank 4 (77.6%).
- `tempest_oracle_ferry@12802b8` rank 10 (84.7%, **45–0–0**) — **best overall and sole Nash core, but explicitly unfair**; `@7196487` is a deployment-only behavioral duplicate (reproduced all 1,890 shared game outcomes, split direct match 21–21).
- `tempest_ferry@26b5aa1` rank 12 (80.8%, 43–0–2); `tempest_fast@eb1f0f3` rank 13 (79.1%); `mistral_fast@26b5aa1` rank 15 (76.3%).

### Phase 5 — Oracle vs Vanguard analysis (16:04Z–16:07Z)
Lucas: "Make an analysis of tempest_oracle_ferry@12802b8 vs vanguard@9932bec." Result: **Oracle 28–14 (66.7%)**; strongly side-dependent — Oracle 11–10 as Gold, **17–4 as Silver**; Silver won 27 of 42 overall. Oracle swept 11 maps (duel, fjord, hive, pinch, runestone, showdown, sprint, string, twins, vase, vault); Vanguard swept 4 (bridge, jackpot, quarry, sweden — Bridge included a 1,000-turn titanium victory); six maps split 1–1, every split won by Silver. Oracle wins averaged 41.7 turns (median 36; fastest Showdown 21, Duel 24). Mechanism: Oracle's `atlas.py` embeds the published official maps, so it knows terrain, resources, and the enemy Core immediately — no scouting, direct ferry attack, up to five Gunners on known firing lines. Vanguard spends titanium/turns on robustness (scouting, economy, defense, launcher pickets, two-hop ferrying, launching enemy Builders away) that buys nothing against a perfect-information rush.

### Phase 6 — ranking methodology Q&A (16:14Z–16:26Z)
Lucas 16:16Z: "No I mean we are ranking based on melo_r, but not using nash averaging?" Confirmed: the numbered leaderboard sorts by `melo_r` (average dominance); Nash is a second interpretation — Nash-core bots have `nash_average = 0` and `nash_prob > 0`, so it is not a full ordering. Current tension: `vanguard@9932bec` #1 by mElo; `tempest_oracle_ferry@12802b8` #10 by mElo but `nash_prob = 1.0`.

Lucas 16:25Z: "Run again on only the newest bots+commits" → newest-only 8-bot field re-rated from 1,176 existing matches: `tempest_oracle_ferry@12802b8` #1 by both (70.4%, 7–0, mElo r 0.7674, sole core p=1.0); then `tempest_ferry@26b5aa1` (0.2531), `vanguard@17ad456` (0.1652), `tempest_fast@eb1f0f3` (0.0457), `vanguard@9932bec` (−0.0720), `mistral_fast@26b5aa1` (−0.2968), `vanguard@26e6792` (−0.3179), `vanguard@259c188` (−0.5447). Field intransitivity 0.371.

### Phase 7 — truly-unseen push + first automation talk (16:28Z–16:51Z)
Lucas 16:28Z: "No I mean bots we haven't seen before. He should have pushed something new. ... By the way, can we automate that process so that a new bots are sent to evaluation as soon as they are pushed?"

- Incident: the discovery command *writes* the registry rather than listing it and replaced the working registry with Jon's tree; caught immediately and reconstructed from the run manifest.
- Three genuinely new behaviors found: new fair Vanguard (source change `bb03f14`, "rotate idle Vanguard Gunners") plus unfair **`undertow_oracle@75591b7`** and **`vanguard_oracle@75591b7`**; `v233_j` byte-identical to that Vanguard. 5,922 rating matches + 9 compliance probes ran as DTU job **29000498**.
- Pinning gotcha: Jon's `BOT_VERSION.toml` pointed at `bb03f14` but the live Vanguard Python had changed after it — the actually-pushed bot was `vanguard@818f3b4` (byte-identical to archived `v233_j@818f3b4`). A corrective sweep (2,019 jobs) covered it. Lesson recorded: automation must hash the actual `.py` tree at the pushed SHA, never trust `BOT_VERSION.toml`.
- Final matrix: 7,950 jobs total, **48 bots, 47,376 matches**, all timing probes passed. `vanguard@9932bec` remained global mElo #1 at 2.3529; `vanguard_oracle@75591b7` #2 (82.6%, 2.3486); `vanguard@818f3b4` #3 (2.3401, behavioral duplicate of `vanguard@17ad456`, 21–21 direct); `undertow_oracle@75591b7` #6 (79.0%, 2.1582); `tempest_oracle_ferry@7196487` sole Nash core (nash_prob = 1.0), mElo #11.
- Automation sketch: push-triggered, idempotent commit-derived tournament IDs, hash-based dedupe, compliance probes, distinct-matrix rebuild. Blocker: no GitHub workflows and DTU auth needs an interactive eight-hour SSH master.

### Phase 8 — the botrankings website and the (disabled) evaluator (16:59Z–18:03Z)
Lucas 16:59Z: "Nah let's run it from this computer. First let's host the results on my website lucasrgpedersen.com/botrankings live, and then build a workflow that detects pushes with bots ... test them, see if they are duplicates (in which case remove them from the results) and then reevaluate all metrics and display on the website." Plus drill-downs: per-bot vs one other bot, per-map, and map+opponent specific.

- Site: the existing Astro portfolio at `/home/Ucals/projects/portfolio`, served by a Cloudflare Worker. Generator emits a small ranking index + one ~400 KB detail JSON per bot (48 files, ~20 MB bundle) with aggregate opponent records, map records, and the exact two side-swapped games per opponent×map cell.
- While testing the detector, **Jon pushed again: branch at `fdc1e1f`, 13 unseen Python implementations including `tempest_frontier`** — kept in dry-run; enabling would have started ~29,000 local matches.
- Lucas 17:09Z: **"Don't actually run any tests before I tell you to launch the eval CI, but do build it."** Evaluator built as disabled systemd user units: timer polls every two minutes, one-shot and resumable, file-lock against overlap (originally eight local workers at low priority — this is the ancestor of the later `botrankings-evaluator.timer`).
- Lucas 17:11Z: host *all* views on the site; and "we should use the dtu hpc, if it fails it should just return an error that I need to log into the dtu ssh again. It's only once every 8h so it's fine." Evaluator switched from local workers to DTU-only, stopping with an explicit `ssh dtu true` login instruction on auth failure — no local fallback.
- Lucas 17:12Z: "I mean I want to be able to get the overview on the website not some ass json" → four human-facing deep-linkable views: `/botrankings/bot/<bot>`, `.../vs/<opponent>`, `.../map/<map>`, `.../vs/<opponent>/map/<map>`.
- Deploy fights: Cloudflare didn't auto-pick-up the GitHub push; its static-redirect validator rejected the deep-link fallback as a loop (moved into the Worker router). Lucas 17:21Z: "I see nothing" — Astro had pre-rendered the interactive component on the build machine where the browser-relative data URL is invalid, embedding the failed state; fixed by true client-only rendering + loading fallback.
- Lucas 17:30Z: "Also show nash average and automatically sort after that but also allow sorting after melo_r if needed." Done — Nash average became the default leaderboard order.
- Lucas 17:33Z: "Do we automatically use the newest data?" — No; only once the evaluator is launched.

### Phase 9 — compliance percentiles and censored timings (17:37Z–18:03Z)
Lucas 17:37Z: "Display the min, 25% percentile, 50% percentile, 75% percentile and max for the compute time." Existing data only carried `max_turn_us`, so the probe format was versioned to **compliance v4**, retaining per-turn microsecond samples. Lucas 17:42Z: "Can we just run this test on all bots? It should be pretty quick" → **48 distinct bots × 3 probe maps = 144 probes** on DTU, zero rating matches. Result: **42 passed, 6 exceeded**: `tempest@da3fd8a`, `mistral@ba943b9`, `jonbot_190003d@da3fd8a`, `jonbot@9713344`, `luc_1@604349b`, `lockin@9713344`.

Lucas 17:56Z: "why does mistral@ba943b9 say comp time exceeded when it says max time is 6.888" — because 6.888 ms was the max among *completed* turns; Mistral also had **124 timed-out turns** (killed by the 12 ms watchdog before emitting an end timestamp). Lucas 18:00Z: "Ah that should also be included in the percentiles, you can write >12ms" → timeouts treated as censored `>12 ms` observations with nearest-rank percentiles. Mistral's corrected line: min 0.013 ms, p25 0.038 ms, median 1.181 ms, p75 >12.000 ms, max >12.000 ms, 124 timeouts of 380 observed turns. No matches rerun.

### Phase 10 — map-task Nash (agent-vs-task) as the default rating (18:19Z–18:36Z)
Lucas 18:19Z: "We should consider each agent+map combo as one match for the nash average (we can compute both, the default is agent+map combo for views and then one can switch to aggregate over maps). Melo_r is just the same. Recompute rankings and update agent.md and the general scripts."

Implementation: the Balduzzi agent-vs-task construction — evaluated bot is the agent, each `(opponent bot, map)` is a task; the two Gold/Silver games collapse into one side-balanced task score. The 48-agent × 1,008-task max-entropy solve was too slow in exact primal form; replaced with the **48-variable convex dual**, cutting the full-field solve to ~6 seconds — fast enough for the polling pipeline. Under the new default, **`tempest_oracle_ferry@7196487` is #1 by both mElo and Nash tie-break** (aggregate mode preserves its old mElo #11 / Nash #1). Committed and pushed to `x/tournament` as **`70ce34f` "Add automated map-task bot rankings"** (AGENTS.md, `rate`, reporting, automation, CSVs, website schema all updated; no games rerun).

### Phase 11 — unfair tag and coinflip draws (18:37Z–19:13Z)
- Lucas 18:37Z: "Also add the tag to luc1 that it's unfair" → `luc_1@604349b` tagged `unfair`; metadata precedence fixed so the registry overrides stale tags in historical manifests. Commits: tournament `44b37cd`, website `77d1f56`.
- Lucas 19:05Z: "Do we record what the win_reason was for each match? Cause ties are currently broken randomly but we should treat it as a tie (since we can handle that)." Audit: `win_condition` is persisted; the canonical distinct dataset has **128 `coinflip` outcomes** — games where core destruction, titanium delivered, harvesters, and titanium stored were all tied and the engine chose a winner at random. All 128 now score 0.5–0.5 everywhere (mElo, Nash, duplicate detection, summaries, match details) with the raw `engine_winner` retained. A second bug found during validation: the CSV's W/D/L summary inferred draw counts from aggregated half-points, losing pairs with an even number of draws — replaced with an exact draw-count matrix. Portfolio repo's `main` had no upstream configured (publish chain stopped silently); fixed. Pushed: eval framework `1073c1d`, website `0e57536`. Verified live: all 128 coinflips (256 bot perspectives) display as draws.

---

## Session 3 — rollout-2026-08-01T16-42-39 (14:43:16Z–15:01:45Z; 16:42–17:01 local)

**Goal:** Lucas: "To the eval pipline add compliance check to all named bots, just a short check on a few matches whether they ever exceed the 10ms limit or come close. Store the data permanently of course."

Built the timing-compliance subsystem (the one session 2 then consumed):
- Every `--bots` entrant gets **three instrumented probe matches on atoll, duel, and quarry**; the rating path's `--tle 0` is untouched so machine load cannot contaminate ratings; compliance matches never enter ratings.
- The engine result records only timeout outcomes, not per-turn timings, and each unit has isolated wrapper state — so the probe writes start/end timing markers into the replay for every unit-turn (using the official `get_cpu_time_elapsed()` clock) and parses them before the replay is deleted. A start-without-end at the 10 ms watchdog is a clean timeout signal; a 100 ms guard stops pathological hangs.
- Distinguishes deliberate entity termination (e.g. Vanguard's launcher self-destruct) from a true timeout by checking whether the entity runs again in a later round.
- Classification: **≥9 ms = "close", >10 ms or timeout = "exceeded"**. Durable outputs `compliance.csv` (per-bot summary) and `compliance_matches.csv` (per-match evidence, samples, maxima, timeouts, exceptions, host, timestamps). New command `uv run python -m tournament compliance --tid <tid>`; `rate` prints the summary. Core files: `tournament/compliance.py`, `tournament/plan.py`, `tournament/run_match.py`. **87 tests passed.**

---

## Session 4 — rollout-2026-08-01T17-21-37 (15:21:42Z–15:44:31Z; 17:21–17:44 local)

**Goal:** (a) "Does tempest always win on the same maps?" (b) "look through the newest changes and push."

(a) Using the clean `jon-new` dataset — exactly **1,722 Tempest rating matches** (41 opponents × 21 maps × both orders), no gaps: not a fixed winning set, but a very strong map profile. Tempest's win rates: **pinch 81/82 (98.8%), showdown 81/82 (98.8%), sprint 81/82 (98.8%), runestone 79/82 (96.3%), vault 79/82 (96.3%), sweden 57/82 (69.5%), quarry 53/82 (64.6%), bridge 14/82 (17.1%)**. On bridge, 30 of 41 opponents beat Tempest in both orders; on each of its three best maps it lost only once. Overall 1,443/1,722 (83.8%).

(b) Review-and-push of the concurrent work: a new `jon-unseen-commits` run and bot registrations appeared in the worktree mid-review — treated as concurrent user work, not committed while partial (5,217/15,876 rating matches fetched at exclusion time). Found and fixed a consistency issue: `tempest@ba943b9` was in the head-to-head manifest but missing from the pinned registry; also ignored two stray zero-byte replay lockfiles. Verified both completed rating tables reproduce exactly from persisted matrices and the dedup rerun agrees with the original on all 4,662 shared matches. Pushed **`23ed2e0` "Add timing compliance probes and latest tournament results"** to `x/tournament`; 87 tests passed.

---

## Session 5 — rollout-2026-08-01T18-26-04 (16:27:00Z–16:42:37Z; 18:26–18:42 local)

**Goal:** map-specific Nash winners from existing results, which turned into AGENTS.md policy work.

- "Run the standard analysis on the already gotten results but map-specific. Just tell me the bots with best nash average." All 21 maps had complete coverage: 47 bots, 1,081 pairs, both orders. One map exposed a numerical degeneracy in the max-entropy solver, resolved from a feasible interior point. Output: per-map lists of bots tied at map-specific `nash_average` 0 (e.g. longship: only Tempest variants; bridge: Undertow/v233/Vanguard variants, no Tempest).
- "Make a simple map -> model overview" → a family-collapsed table (e.g. longship → Tempest; pinch → Mistral, Tempest; sweden → Undertow, Vanguard).
- Lucas 16:35Z: "Why are you writing multiple models? Are they tied?" (yes — tied at Nash average 0) and then: **"Duplicates should never be part of any overview! As stated in agents.md? is it not clear?"** The analysis had included the duplicate pair `tempest_oracle_ferry@12802b8`/`@7196487`; `12802b8` was pruned, keeping the deployable `7196487`, and family-collapsing of genuinely distinct versions was retracted.
- Lucas: "It was a real question whether it was clear, otherwise we should rewrite agents.md to make it more clear." Verdict: it was NOT clear — the old text said every duplicate copy remains a separate entrant "on purpose" and never distinguished raw data from user-facing summaries. AGENTS.md updated: raw evidence retains duplicates; rankings/comparisons/winner lists/overviews never do; dedupe the pooled full-map dataset before map-specific slicing; keep distinct versions separate.
- Lucas: "Is it also clear that duplicates should be pooled to one version in new evals? I.e. we keep the raw data we already have, but do NOT make new duplicate data." Previously only implied by `--dedupe-from` and contradicted by other wording; AGENTS.md made categorical: preserve existing duplicate matches, never schedule new ones for a known duplicate, one representative per group in all new evaluations.
- "Push" → **`e5744a7`** to `origin/x/tournament` (AGENTS.md only).

---

## Session 6 — rollout-2026-08-01T19-33-04 (17:33:05Z–20:23:15Z; 19:33–22:23 local)

**Goal:** build Lucas's first serious bot under `bots/luc/` — `tempest_reinforcements` — in three iterations, then push.

1. 17:33Z, Lucas: "On the x/luc branch make a bot that works like tempest, except make sure that there are always bots on the map. If we have above x titanium spawn bots." The shared checkout was on `x/tournament` with uncommitted work, so Codex used a **separate worktree for `x/luc`** (this is the multi-branch pattern later codified in CLAUDE.local.md). Base Tempest creates four opening builders then stops forever. New bot `bots/luc/tempest_reinforcements` (Luc's older bot is `bots/1`; the `bots/<owner>/` layout was newer): keeps Tempest's four-builder opening; **spawns extra builders whenever titanium is strictly above 120** (subject to affordability, space, and the engine's 50-unit cap); plus a **heartbeat that replaces the last missing builder as soon as 30 titanium (the current builder cost) is available**. Commit `926bfdf`. 4 focused tests passed; engine smoke on duel/twins/vault. One pre-existing suite failure noted: `bots/1` loses to starter on `twins` where an old test expects a win.
2. 17:40Z, Lucas: "And for the next update make sure bots are always doing something, if they cannot pathfind somewhere they could consider building launchers." Generalized the `tempest_ferry` idea (which gave one preselected attacker one opening hop): any builder with **three consecutive failed route attempts builds a temporary launcher** (60-titanium reserve, cooldown against launcher spam), publishes its ID and true destination via reserved communication slots, hops, then resumes its task; secondary local-motion fallback when a launcher is unaffordable or capped (prefer unseen tiles / progress toward target); patrol instead of idling when exploration is exhausted; scrap unusable launchers after six idle rounds. Also fixed a base-Tempest defense bug found in smoke tests: distant defenders queried a remembered core position after walking out of vision, throwing/catching `Position out of vision range` every round — they now path back toward the core. Commit `dde957c`; 8 focused tests; debug self-play on atoll/quarry/vault exception-free; suite 48 passed.
3. 18:38Z, Lucas: "Also apply the best from tempest_oracle_ferry." Ported the **atlas** (not the oracle's older one-off ferry code): validates the published official map against every visible tile before trusting it; preloads known walls and ore; publishes the exact enemy-core location immediately; attackers spawn facing the known core; the first attacker gets one proactive atlas-directed ferry hop on long approaches (bounded to one hop, first attacker only); unknown/mismatched maps fall back to observation-only logic. **This intentionally makes the entrant `unfair`/oracle-class**, like `tempest_oracle_ferry`. Commit `87724ec`; 12 focused tests; suite 52 passed.
4. 20:22Z, Lucas: "Is it pushed?" — no, three commits ahead. "push!" → **`origin/x/luc` at `87724ec`** (20:23Z).

---

## Chunk synthesis

Load-bearing insights, each with evidence:

1. **This chunk contains the birth of the public botrankings site and the (still-disabled) evaluator that later became `botrankings-evaluator.timer`.** Session 2, 16:59Z–17:21Z: Lucas ordered results hosted live at lucasrgpedersen.com/botrankings with a local push-detection workflow; the evaluator was built as disabled systemd user units polling every two minutes, per Lucas's explicit "Don't actually run any tests before I tell you to launch the eval CI, but do build it" (17:09Z). At chunk close it had never been launched.
2. **The evaluator must run on DTU HPC only, with a human relogin loop.** Lucas 17:11Z: on auth failure "just return an error that I need to log into the dtu ssh again. It's only once every 8h so it's fine." No local fallback.
3. **`tempest_oracle_ferry` (Jon) is the day's strongest bot but explicitly unfair**: its `atlas.py` embeds the official maps (immediate enemy-core knowledge, no scouting). Sole Nash-core agent (nash_prob = 1.0) in every pool it entered; 45–0–0 series in the 10-commit run; beat mElo-#1 `vanguard@9932bec` 28–14 head-to-head (session 2, 16:02Z–16:07Z).
4. **mElo and Nash deliberately disagree, and the default was changed twice.** The leaderboard sorted by `melo_r` (average dominance) with Nash as the exploitability view (16:16Z); Lucas then made Nash average the default sort on the site (17:30Z) and finally made **agent+map-task Nash the default formulation** (18:19Z), each (opponent, map) a separate task, Gold/Silver combined into one side-balanced score. Under map-task rating `tempest_oracle_ferry@7196487` is #1 by both metrics; in aggregate mode it is mElo #11 / Nash #1. Commit `70ce34f`.
5. **The 1,008-task max-entropy Nash solve was made pipeline-fast via the 48-variable convex dual: ~6 seconds** for the full field (session 2, 18:28Z–18:30Z). Without this the polling evaluator could not republish ratings.
6. **Duplicate policy became categorical after two reprimands from Lucas** (session 2, 15:17Z; session 5, 16:35Z–16:41Z): keep existing duplicate evidence, never schedule new matches for known duplicates (756 matches were wasted before the rule), and never show duplicates in any overview — dedupe the pooled dataset before map-slicing. AGENTS.md updated (commit `e5744a7`); Lucas explicitly asked whether the doc was unclear rather than just assigning blame — it was, and got rewritten.
7. **Compliance probing was built (session 3) and hardened to censored percentiles (session 2, phase 9) the same afternoon.** Three probes per bot on atoll/duel/quarry, per-unit-turn timings via replay markers, ≥9 ms "close" / >10 ms "exceeded"; v4 keeps raw samples; timeouts count as censored `>12 ms` observations (Lucas: "you can write >12ms"). Full-roster run: 48 bots × 3 = 144 probes; **42 passed, 6 exceeded** (`tempest@da3fd8a`, `mistral@ba943b9`, `jonbot_190003d@da3fd8a`, `jonbot@9713344`, `luc_1@604349b`, `lockin@9713344`). Mistral's "max 6.888 ms but exceeded" paradox = 124 watchdog-killed turns of 380.
8. **`coinflip` ties (full four-way ties randomly broken by the engine) are now true draws**: 128 such matches in the canonical dataset were rescored 0.5–0.5 across all consumers, with `engine_winner` retained; an exact draw-count matrix replaced lossy W/D/L inference (session 2, 19:05Z–19:13Z; commits `1073c1d` framework, `0e57536` website).
9. **Never trust `BOT_VERSION.toml`; hash the actual `.py` tree at the pushed SHA.** Jon's metadata pointed at `bb03f14` while the live Vanguard was `818f3b4`; a corrective 2,019-job sweep was needed (session 2, 16:45Z).
10. **Lucas's `luc_1@604349b` (old `bots/1`) is weak and non-compliant**: 37/38 mElo, 357–1,197 (23.0%), 0 series wins, 12.416 ms max with five timeouts; byte-identical Python to legacy `lockin` yet behaviorally distinct (code-hash pruning had to be overridden); Lucas had it tagged `unfair` (18:37Z).
11. **`tempest_reinforcements` is Lucas's first bot in the `bots/luc/` layout** (session 6): Tempest + continuous spawning above 120 Ti + 30-Ti heartbeat replacement + stuck-builder launchers (3 failed routes, 60-Ti reserve) + anti-idle patrols + ported oracle atlas (making it unfair-class). Pushed to `origin/x/luc` as `87724ec` at 20:23Z. Along the way a genuine base-Tempest defense bug (out-of-vision core query loop) was found and fixed.
12. **Tempest's map profile is extreme and Bridge is its kryptonite**: 98.8% on pinch/showdown/sprint but 17.1% on bridge, where 30 of 41 opponents beat it from both sides (session 4, 1,722-match dataset).
13. **Side matters**: in Oracle-vs-Vanguard, every split map went to Silver and Silver won 27/42 overall; Oracle's record was 11–10 as Gold vs 17–4 as Silver. Convention fixed this chunk: player A = Gold, player B = Silver.
14. **Jon's development tempo was ferocious**: within one afternoon the tested frontier moved `ba943b9` → `de18549` → `ca710da` → `fdc1e1f`, adding tempest_fast, mistral_fast, tempest_ferry, tempest_oracle_ferry, vanguard_oracle, undertow_oracle, and (unevaluated) tempest_frontier plus 12 more unseen implementations.
15. **Match-cost reality** (AGENTS.md snapshot embedded in these sessions): mean 8.8 s, median 6.0 s, p99 39 s, max 63.9 s over 36,162 real matches; DTU `hpc` queue caps ~100–120 concurrent slots. The 41,580-match pooled matrix and 47,376-match final matrix were only feasible on the cluster.
16. **Reporting norms Lucas enforced personally**: name the exact matchup ("Pretty important detail"), include Gold/Silver mapping, no JSON as a user interface ("not some ass json"), and "Only report back when its done" for long cluster runs.

Loose ends at chunk close (~19:13Z session 2 / 20:23Z session 6):
- The eval CI/evaluator is fully built but **disabled** — awaiting Lucas's explicit launch order.
- Jon's `fdc1e1f` push (13 unseen implementations incl. `tempest_frontier`) is detected but **unevaluated**.
- `tempest_reinforcements@87724ec` is pushed but **has no tournament rating yet**, and it is oracle/unfair-class — its fairness tagging in the registry/website was not shown being set in this chunk.
- The `Direction` tuple-comparison `TypeError` inside Mistral (and once Tempest) remains an unfixed opponent-side bug that may distort its results.
- The legacy suite failure (`bots/1` expected to beat starter on `twins` but loses) was left standing in all session-6 test runs.
- Compliance history: pre-v4 checks can never reconstruct percentiles (labeled "unavailable" on the site); only maxima exist for them.
