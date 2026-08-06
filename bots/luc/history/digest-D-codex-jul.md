# Codex CLI sessions digest — chunk D (2026-07-25 → 2026-07-28)

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

Source: five Codex rollout JSONL files under `/home/Ucals/.codex/sessions/2026/07/`. All
timestamps below are UTC (the `Z` timestamps in the records); filenames use local
Europe/Copenhagen time (UTC+2). Working directory at the time was
`/home/Ucals/projects/florent-code-league` (the repo's remote is
`https://github.com/jonathantybirk/florent-code-league` — Jon owns the shared repo). Codex ran as
"Codex, an agent based on GPT-5" from VS Code (`codex_vscode`, cli 0.146.0-alpha.3), in parallel
with Claude Code sessions on the same checkout.

---

## Session 1 — map-pool documentation question
**File:** `2026/07/25/rollout-2026-07-25T16-34-37-019f99b3-....jsonl` (92 KB)
**Span:** 2026-07-25T14:35:04Z → 14:35:44Z (one exchange)

Lucas asked: "In the docs or in fcode, is there any information about whether there will be more
than the 15 default maps in the final tournament". Codex searched the repo docs and the installed
`fcode` 2.2.0 package and concluded:

- `MAPS.md` calls the 15 maps "every map in the competition pool".
- `docs/game-rules/game-rules-how-matches-work.md` says the map pool "gets announced when
  competitions begin and may be adjusted between rounds".
- No statement anywhere promises extra, hidden, or final-only maps.

Conclusion: 15 is the documented pool, but additions/replacements between rounds remain possible.
No code changes.

---

## Session 2 — 64-byte map encoding design; per-agent map memory; branch `x/luc` created
**File:** `2026/07/25/rollout-2026-07-25T16-58-48-019f99c9-....jsonl` (864 KB)
**Span:** 2026-07-25T14:58:49Z → 2026-07-27T07:19:27Z (resumed across three days; 7 session_meta
resume records)

### Part A (Jul 25, ~14:58–15:29Z): compact map representation for the 64-byte global store
Lucas's goal: design a wire format so all units can share the map through the global
communication store ("common information registry", also called "the grapevine") — only 64 bytes
(sixteen 32-bit slots) are available. His opening ideas: sparse representation, wall-block
corners with 2 bits for hollow/filled/diagonal, exploit 180° symmetry of walls/ores/bases to
store only half the map; he predicted `hive` (dispersed lattice walls) would be the problem map.

Codex measured against the real maps and overturned that prediction:

- All maps are at most 28×26, so a raw coordinate costs 10 bits (5+5); after rotational
  canonicalization (`canonical = min(i, width*height-1-i)` on flattened index), one coordinate
  needs at most **9 bits** (`ceil(log2(338)) = 9` for the largest 26×26 canonical half).
- **hive is not the limiting case**: after canonicalization hive has 17 canonical walls + 6
  canonical ores (34 walls, 12 ores total); **aurora is worst** with 39 positive terrain cells
  (32 walls + 7 ores).
- Packed fixed-width coordinates incl. a 32-bit header (valid/complete/overflow flags, format
  version, revision, wall count, ore count, own core x/y): hive 239 bits / 8 slots, aurora 383
  bits / 12 slots, strait 374 bits / 12 slots, longship 284 bits / 9 slots. Everything fits in
  48 bytes.
- Enumerative "combinadic" (combinatorial number system) encoding — rank the wall set among
  C(M,W) and the ore set among C(M-W,O) — shrinks that to: hive 164 bits, aurora 227 bits,
  strait 207 bits, longship 182 bits, i.e. every map under 29 logical bytes, all inside eight
  32-bit slots with eight left over.
- Hard information-theoretic limit: an arbitrary symmetric 26×26 ternary map needs
  `log2(3^338) ≈ 536 bits` — more than the entire 512-bit store — so no lossless format covers
  all arbitrary maps; the design needs an overflow/partial flag.
- Cheapest option of all if the pool stays fixed: broadcast a 4-bit map ID and hardcode the
  atlas, since each map is identifiable from `(width, height, own core position)`.
- Operational caveat: a packed snapshot should have a single publisher (the Core) because store
  writes are buffered and visible one round later; scouts submit small discovery records.

Lucas mid-thread contributed his own hand count of full-map coordinate costs (both halves):
atoll 14, aurora 24, crossfire 20, duel 10, fjord 22, hive 48, longship 30, pinch 16, quarry 32,
runestone 22, skerry 26, sprint 8, strait 20, twins 21, vault 16 — worrying hive alone would
consume the memory. Codex pointed out his hive count double-counted the rotational halves (hive
needs only 24 canonical coordinates ≈ 27 bytes).

Lucas's stated directive: "Right now let's just focus on the representation of the map to use
the least amount of bits and discuss that design."

### Part B (Jul 25, 16:30–20:58Z): Plan Mode → per-agent ground/actual map memory
Lucas defined the terminology used from then on: **ground map** = map without any temporary
entities (conveyors, bots, …); **actual map** = full map including entities. He requested: a
player class holding `self.map` per agent; `utils/map.py` with `update_map` (ingest all tiles in
visual range each round) and a scaffolded `decode_map_info` (future registry decoding, output
shaped like `ct.get_nearby_tiles`); matching observations against the 15 known maps and snapping
to the unique candidate; `rounds_since_last_seen` per tile; a discovery-source tag
(VISION/REGISTRY/KNOWN_MAP) so a false atlas inference can be purged without losing observed
tiles; ground-map violations trigger forgetting all atlas-derived tiles.

Lucas raised one objection — "it's not true that some maps will be recognized immediately due to
dimensions as the units have limited vision" — and Codex corrected him: `ct.get_map_width()` /
`ct.get_map_height()` are global metadata every unit can call, so the 12 uniquely-dimensioned
maps identify instantly; only the three 24×24 maps need terrain/Core evidence. Lucas accepted.

Implementation (Default mode, ~20:51–20:58Z), in **`bots/starter`**:

- `bots/starter/utils/map.py`: `DiscoverySource`, `EntitySnapshot`, `TileObservation`,
  `TileState`, `MapMatchState`, `update_map`, `decode_map_info` (still `pass`), a dependency-free
  protobuf-wire `.map26` parser, atlas matching and invalidation.
- All 15 `.map26` maps bundled under `bots/starter/maps/`; `self.map` integrated into
  `bots/starter/main.py`.
- 9 regression tests in `tests/test_map_memory.py`, all passing; parser parity for all 15 maps;
  a full 1,000-turn engine smoke match completed within the 10 ms TLE.
- Known limitation noted: cooldowns and turret ammo of *other* units are not queryable by
  entity ID, so shared entity snapshots cannot include them.

### Part C (Jul 27, 07:09–07:19Z): branch creation
Lucas: "Let's move the local changes to a new branch x/luc" (asked three times across aborted
turns). Codex created and switched to **`x/luc`** with all local changes intact and uncommitted.
This is the birth of the branch that later becomes the canonical home of all Lucas bots.

---

## Session 3 — extract Jon's docs from `x/jon`, push to `main`, merge into `x/luc`
**File:** `2026/07/28/rollout-2026-07-28T12-07-11-019fa831-....jsonl` (278 KB)
**Span:** 2026-07-28T10:07:40Z → 10:11:59Z

Lucas: "my friend pushed updates to the docs as well as other things to x/jon. I only want the
updates to the docs pushed to main and merged into my branch." Codex:

- Treated "docs" as the `docs/` directory only (excluded Jon's bots, maps, config, root
  `README.md`, `AGENTS.md`).
- Built the docs-only commit in an isolated temporary clone (100 changed paths, all under
  `docs/`; docs tree verified identical to `x/jon`), pushed it to `main` as **`a7035ef`**.
- Rehearsed the merge against a copy first, then stash-merged-restored on the real dirty
  `x/luc`: merged `main` into `x/luc` as **`2b2a213`**, preserving all staged/unstaged/untracked
  work. Lucas's own local docs edit was auto-relocated to Jon's new path
  `docs/llm-slop-docs/api-reference/api-types.md`.
- Left `x/luc` two commits ahead of `origin/x/luc`, unpushed.

Notable: Jon's docs restructure puts the API reference under a directory literally named
`docs/llm-slop-docs/`.

---

## Session 4 — two more docs-only pushes to `main`
**File:** `2026/07/28/rollout-2026-07-28T12-45-31-019fa854-....jsonl` (202 KB)
**Span:** 2026-07-28T10:45:41Z → 10:54:12Z (sandbox disabled/unrestricted this session)

Lucas: "merge only the /docs directory into main", then "push too", then "Also push the newest
changes made to the docs to main."

- Isolated docs-only commit `ab46dc0` from the dirty worktree → applied to `main` as
  **`7cd9a84` "Update documentation"**, verified docs-only, pushed.
- The newest extra change was a one-line clarification in `docs/agents/agents-md.md` → pushed as
  **`40650fc` "Clarify core spawn radius documentation"**. During amend, an already-staged test
  rename from Lucas's unrelated work briefly leaked into the commit; Codex caught it in
  verification and removed it while preserving the rename in the index.
- Unrelated bot/test changes on `x/luc` untouched throughout.

---

## Session 5 — THE GIANT: building bot `1` all day, Jon's `lockin` crisis, and the Codex-vs-Claude autonomous arms race
**File:** `2026/07/28/rollout-2026-07-28T12-18-25-019fa83b-....jsonl` (11 MB; 15 in-session
compactions)
**Span:** 2026-07-28T10:21:09Z → 19:53:08Z (~9.5 hours, task_complete at 19:53Z)

This session develops Lucas's first serious bot, living in **`bots/1`** on `x/luc` (ancestor of
the later bot lineage; the map-memory `utils/map.py` from Session 2 is present in it).
Interleaved commits by other sessions/Lucas landed on `x/luc` during the day
(`4a4f66e "improve s…"`, `2f4d593`/`cc25add "Fix strat1"`, `83771dd "Fix deletion upon impossible
command"`, `2ce9ee8 "Fix gitignore"`).

### Phase 1 (10:21–11:00Z): Sentinel mechanics and damage table
Lucas asked how the "sentinal" works — answer: autonomous but must be commanded via
`ct.fire(target)`; `bots/1` had no SENTINEL branch, so it never fired. Codex implemented
closest-enemy targeting (`bots/1/entities/sentinel.py`), handling the rule that a Builder Bot on
top of a building receives the hit (avoid friendly fire). 11 unit tests + full match passed.
Also gave the run command: `.venv/bin/fcode run 1 starter twins --tle 10 --watch`.

Damage overview compiled from installed `fcode 2.2.0` (repo docs contained conflicting historical
descriptions — Codex explicitly distrusted them):

| Attacker | Build cost | HP | Damage | Cost per attack | Reload | Range/pattern |
|---|---:|---:|---:|---:|---:|---|
| Builder Bot | 30 Ti | 40 | 2 | 2 global Ti | 1 round | own tile only (r²=0) |
| Gunner | 10 Ti | 40 | 10 | 2 local ammo | 1 round | straight facing ray, r² ≤ 13 |
| Sentinel | 30 Ti | 30 | 18 | 10 local ammo | 3 rounds | ~3-tile-wide facing corridor, r² ≤ 32, shoots through walls |

Other mechanics recorded: Gunner rotates post-build for 10 global Ti + 1-round cooldown; Sentinel
facing is fixed forever; turrets hold at most one 10-Ti stack and accept a new one only when
empty; a cardinal-facing turret cannot receive ammo from its facing side; Harvester 20 Ti base,
emits a 10-Ti stack immediately and every 4 rounds; Conveyor 3 Ti, Splitter 6 Ti, Barrier
(30 HP); build-cost scaling `floor(scale × base)` with per-entity increments (conveyor/splitter/
barrier +1%, harvester +5%, gunner/launcher +10%, builder bot/sentinel +20%); Core 500 HP
(50 Gunner shots / 28 Sentinel shots); minimal Gunner setup ≈ 66 Ti vs Sentinel setup ≈ 91 Ti;
Launchers and the Core deal no damage — a Launcher only repositions (throws) Builder Bots;
Builder self-destruct deals zero damage; `destroy()` works only on allied buildings, so killing
an enemy conveyor takes ten 2-damage builder attacks vs its 20 HP.

### Phase 2 (11:15–12:16Z): full role-based strategy, then the map-inference bug
Lucas dictated a strategy: Core announces attacker-vs-infrastructure role on the store's last
bit; 2 attackers spawn closest to the enemy Core; first builds a Launcher; attackers relay
through Launchers while faster than walking, then build ammo-fed turrets at open conveyor ends;
infrastructure bots claim distinct ores, build Harvesters, connect conveyors to the nearest
Core-bound line; unknown maps raise an error. Codex implemented it (store slot 15 = role+spawn
sequence, slots 13–14 = attacker IDs) — Twins kill of the starter Core on turn 104, then 94.

Then the notable debugging exchange: Codex had "fixed" attackers losing the inferred map by
locking the first identification. **Lucas pushed back**: "it should not be possible that the
inferred cache is wrong since we only choose it when we are sure of the map type. That points at
a bug in the code." Codex investigated and confirmed him: at round 80 the diagnostic opponent
`resign()`ed, destroying its Core; both attackers then observed enemy Core tile `(2,17)` empty,
and `_observation_matches_map()` compared the static map Core against live occupancy
(`FixedCore(...) == None`), wrongly rejecting `twins`. The lock was masking a broken evidence
model. Lucas's ruling: a missing Core may reject the hypothesis (it only happens on the winning
frame) — warn, never raise. Implemented: one `RuntimeWarning` per unit, strategy skipped for
that frame.

Second directive burst (11:58Z): prefer Gunners over Sentinels when they can hit the Core;
destroy the last conveyor of a full enemy harvester→core line and put a turret there; first bot
places the Launcher, launch the first 2 bots instantly; more attackers at bots 5, 8, 11;
slot 14 ("14th digit") = titanium-pressure signal pausing Core spawning; note that a bot can
build and move in the same turn; a launch-request protocol (bot announces id+destination — Lucas
wanted it in a byte; Codex packed a 16-bit ID token + destination into one u32 slot instead);
chokepoint tiles filled with Core-facing conveyors; near-Core ore prioritized; enemy harvesters
connected into our lines. Result after fixes (empty `GunnerMixin` stub had silently never fired):
Twins kill turn 57 → 40. An experiment fully parallelizing infrastructure routes raised mining
to 960 titanium / 40 buildings but delayed the Twins kill from ~40 to 172 — reverted to "one
unfinished route at a time"; final: Twins kill turn 53, 110 titanium mined, 14 buildings,
19 tests green.

### Phase 3 (12:25–12:36Z): the undo incident and session-history restore
Lucas suspected the changes made things worse and asked for a benchmark; there was no committed
"before" checkpoint (all evolution uncommitted; HEAD far older). He clicked the IDE's undo —
Codex determined the undo was only **partial** (auto-fire reverted to `pass`, pacing and fixes
gone, but the big strategy rewrite still present). Lucas: "I just want to go back to the way the
code was before I wrote [the 11:58 message]". Codex reconstructed the exact pre-message state by
replaying the local session edit history into a temp tree, restored 4 files byte-for-byte
(builder.py, core.py, launcher.py, common.py), kept the discarded newer version recoverable at
`/tmp/fcode-before-rollback.HorIfX`. Restored bot: Twins kill turn 135.

### Phase 4 (12:37–15:58Z): iterative behavior fixes driven by Lucas watching replays
- Conveyor linking: prefer existing friendly conveyors over building parallel lines. First
  version required chains proven to reach the Core; **Lucas**: "You're overengineering it. Let's
  just make a bot route the conveyors to the nearest friendly conveyor without any communication.
  Speed is key, so waiting is bad." Simplified accordingly (Twins win, later 1,050 titanium /
  47 buildings).
- Offensive fallback for isolated harvesters: route titanium *toward the enemy Core*, end in a
  Splitter feeding up to 3 Core-facing Gunners (Twins kill turn 96); then "gunners instead of
  sentinals if right next to the enemy core" (turn 43).
- Conveyor loops (two builders routing into each other): Codex proposed removing conveyors as
  sinks entirely; **Lucas disagreed**: keep the linking rule, but if a route ever points away
  from the target, fall back to the direct shortest path. Hybrid implemented (turn 43).
- "Teleporting bot" mystery (frames 13–14): bot 5 was launched by three Launchers in one
  simulation turn — `(7,4)→(6,4)`, then launched to `(8,9)`, `(13,13)`, `(16,18)` — legal
  same-turn launcher chaining; the replay shows only final state. But Lucas noticed it was an
  *infrastructure* bot: a role-assignment race (single shared assignment slot overwritten before
  the newborn's first read). Two rounds of fixes: first a one-round-ahead pre-announcement
  (Lucas: the very first builder needs no announcement — it can infer "attacker 0" from the
  untouched slot); when the race persisted (spawned bots execute one frame later than assumed —
  frame-9 evidence: bot 5 became infrastructure, and attacker bot 3 built a useless Gunner 41 at
  `(19,6)` fed by a dangling conveyor that never received titanium in 109 frames), Lucas
  specified the final protocol: the Core announces the spawned bot's ID as it spawns; the bot
  reads it next round. Implemented as a stable per-spawn-index ID registry — no spawn delay, no
  overwrites. Gunner endpoints re-ranked: verified-fed first, then titanium-observed, then
  dangling (still allowed as disruption).
- Conveyor routing polish: avoid ore tiles when possible; recompute when blocked; sabotage an
  enemy belt when detouring around it costs more than 5 extra belts (Hive: 31 conveyors, none on
  ore; kill turn 64).
- Bot 9 "gave up on finishing the conveyor" after frame 67: its own unfinished belt was accepted
  as a zero-length valid sink (`_friendly_conveyors()` included the bot's own line). Fixed:
  sinks must have a verified directed downstream chain to our Core.
- Idle infrastructure surveying: patrol serpentine grid, finish dangling lines, route orphan
  harvesters home, leech enemy harvesters via unused sides. **Lucas's design ruling**: "There's
  no reason to handle enemy conveyors and own conveyors differently, same for harvesters. Treat
  them equally … you can literally just ignore the team." Logistics became fully
  ownership-agnostic (mixed-team chains traced as one); team checked only for the removal API
  (`destroy()` vs attack).
- "Bots delete themselves": bot 19 at frame 101 crashed with `GameError: Position out of vision
  range` (queried a planned conveyor tile before walking close enough); the engine removes a
  unit whose `run()` throws, which looks like self-deletion. Guard added.

### Phase 5 (16:10–17:37Z): Jon's `lockin` decimation and the counter
Cross-branch testing (seed 1, 10 ms TLE, all 15 maps, replays saved under
`match-replays/`):

- `x/luc/1` (commit `83771dd`) vs `x/jon/mybot` (`606a480`): **15–0** to Lucas (4 maps hit the
  1,000-turn cap: crossfire, duel, quarry, vault).
- `x/luc/1` vs `x/jon/adaptive_v1`: **15–0** again (cap maps: crossfire, duel, quarry, skerry,
  vault).
- Jon pushed `adda72a` adding **`bots/lockin`** (Lucas asked "Check out again" three times until
  it appeared): **`lockin` won 8–7** (lockin: duel, hive, longship, quarry, skerry, strait,
  twins, vault; luc/1: atoll, aurora, crossfire, fjord, pinch, runestone, sprint), all matches
  within 74 turns.

Lucas, verbatim: "LOCK THE FUCK IN, HE LOOKED AT OUR CODE AND ***DECIMATED*** us. LOOK AT HIS
CODE FROM THE VERY NEWEST COMMIT AND DO BETTER."

Codex found Jon's newest commit (`a82a069`) was a **targeted counter built on a copy of Lucas's
architecture**, adding map-and-side-specific attacker counts and spawn delays. Baseline of
current Lucas bot vs it: **1–14 as Team A** (2/30 both orientations). The sweep that followed:

- 3 attackers/2 infra: recovers crossfire, duel, hive as Team A but mirroring it overall only
  4/30 (equal code mostly hands the win to Team A).
- 4 attackers: 7/30; 5 attackers/no economy: dead end (first two maps stalled to 1,000 turns and
  lost). 10-round and 20-round spawn-delay holds: no flips — timing was not the lever.
- Found a bug inherited from Jon's copy: attacker #3 walks to launchers that will never
  recognize its ID, waits 15 rounds; split roles so extra pressure bots walk directly.
- Replay tracing revealed Jon's real kill mechanism: wait for Lucas's first completed
  harvester→core line, destroy the final conveyor, replace it with an ammo-fed Gunner, compound
  turrets around the Core.
- **The decisive counter**: park an infrastructure Builder Bot *on* the final core-feeding
  conveyor (bots may stand on conveyors without blocking titanium; enemies must stand on a belt
  to attack it) — physically denies the takeover. Atoll and aurora instantly flipped;
  2/30 → 12/30, then map-specific configs (4-bot pressure on quarry/sprint as Team A, lean 2-bot
  opening on Team-B pinch) → **11–4 as Team A vs `lockin` (from 1–14)**, reverse side 6–9,
  **17–13 overall**.
- Reproducibility caveat Codex flagged: several path/launcher tie-breaks iterated Python sets,
  whose order varies across processes, making results non-reproducible even at game seed 1; the
  acceptance run was repeated with a fixed Python hash seed and reproduced 11–4 exactly.
- Mid-benchmark, Jon pushed again (`4d85b48`, new bot **`frontier`**). The lockin-specialized
  version beat frontier 10–5, but the *untouched* old bot beat frontier 13–2 — the
  specialization had regressed sprint, twins, vault. Hybrid (lean two-attacker opening restored
  on those three maps): **13–2 vs frontier and 11–4 vs lockin simultaneously** (twins held,
  vault flipped to a win, only sprint reverted).

### Phase 6 (17:37–19:53Z): the unattended Codex-vs-Claude arms race
Lucas's parting directive: "Push when you are done with commit message that codex attempted
improvement. Then spawn a claude code agent to win against your bot, etc. and then you try to
win against it, etc. until I'm back. Push for every version. Claude can create a new bot
directory."

Commit chain pushed to `x/luc` (from `2ce9ee8`):

1. **`7e0cb63` "codex attempted improvement"** — the hybrid counter above (4 files, +119/−31).
2. **`e7b79f9` "claude attempted improvement"** — Claude Code's `bots/claude_challenger_1`
   (25 files, +2,736): copied the champion, added universal final-belt takeover denial and
   path-aware launcher landings (its aggressive first variant overcommitted and was rolled back
   by Claude itself). Verified 11–4 as Team A but **4–11 as Team B** (only reverse-side core
   kill: sprint); heavily side-sensitive (duel's turn-56 core kill flips to whoever owns
   Team A). Claude's first attempt stalled ~5 minutes in pure analysis and had to be restarted
   with an implementation-first prompt; later it looped rerunning an identical baseline and had
   to be nudged again.
3. **`1820079` "codex attempted improvement v2"** (3 files, +64/−2) — Codex's counter. A
   sixth economy-only spawn failed (turn-cap replays showed zero titanium delivered to either
   core, so "more economy" could not pay back); the winning idea was the **lean Team-B
   economy** — skip the second infrastructure project entirely and bank the builder/harvester/
   belt costs: atoll, hive, longship flipped with stored-titanium margins +32, +132, +84; twins
   flipped after matching the two-attacker opening (banked 2,827 vs 2,712). Also: attacker
   recognizes a guarded final belt and cuts the penultimate belt instead. Result: 11–4 Team A /
   8–7 Team B, **19–11 combined** vs challenger 1 (prior symmetric 15–15).
4. **`4078dda` "claude attempted improvement v2"** — `bots/claude_challenger_2` (25 files,
   +2,769), pushed *despite losing*, per Lucas's "push for every version". Its journey: a
   "reinforcement uncapping" idea (Core replaces lost builders) was cut down after cost-scaling
   analysis; a guard-everywhere rule lost 12–18 combined and was reverted. Codex then suspected
   a harness bug — both bots use top-level module names like `utils.common`, possible cross-bot
   import leakage — and **disproved it** with adversarial helper modules (the loader isolates
   import namespaces). The real problem was a **CPU cliff**: at 10 ms the bot sat inert (atoll:
   1,000 turns, zero mining), at 15 ms it rushed and won. Profiling (no-TLE instrumented
   replay): sensing averaged 0.08 ms, but the first Core strategy call cost **21.1 ms** and each
   new infrastructure builder repeated 15–21 ms; the culprit was `ordered_ores` running one
   full-map BFS *per ore tile* (plus every newly spawned entity parsing all 15 bundled `.map26`
   files on its first turn — fixed by a static dimension index + lazy single-map load, which was
   correct but insufficient alone). Replacing per-ore BFS with **one reverse BFS from the Core
   perimeter** (identical ordering verified on all 15 maps) flipped atoll at 10 ms from the
   zero-mining stalemate to a core kill on turn 88. But the challenger's strategy experiments
   still lost the 30-game gates: 8–22, then (champion strategy restored + speedups) 5/30 — the
   remaining drift isolated to Claude's entity-driven map-memory rewrite, which had dropped
   empty-visible-tile records that path/occupancy logic relied on; with map semantics restored
   too (champion + one-BFS optimization only, 41/41 tests) it still scored **7–23**, because
   Team A tends to win regardless of which directory carries the optimization.
5. At 19:50Z Codex spawned a third Claude challenger (`bots/claude_challenger_3`, target: >15/30
   at 10 ms, explicit permission for map/team-specific counters, aimed at the champion's Team-B
   early-core-destruction losses). **The session log ends at 19:53Z with challenger 3 still in
   analysis** — its outcome is not in this chunk.

---

## New names introduced in this chunk (one-liners)

- **`bots/starter`** — the tutorial/starter bot; received the per-agent map memory on Jul 25.
- **`bots/1`** — Lucas's first real bot (entities/{core,builder,launcher,sentinel,gunner}.py +
  utils/{common,map}.py), developed all of Jul 28; ancestor of the later lineage.
- **`x/luc`** — Lucas's bot branch, created 2026-07-27 in Session 2.
- **`x/jon`** — Jon's branch; the shared repo lives under Jon's GitHub account
  (`jonathantybirk/florent-code-league`).
- **`mybot`, `adaptive_v1`** (+ ~4 sibling variants added in one commit) — Jon's early bots;
  both swept 15–0 by `bots/1`.
- **`lockin`** — Jon's Jul 28 bot built by copying Lucas's architecture and counter-tuning
  (map/side-specific attacker counts and spawn delays); first bot to beat Lucas (8–7, then
  14–1 vs the pre-counter bot as `a82a069`).
- **`frontier`** — Jon's next bot the same evening (`4d85b48`); weaker vs Lucas (2–13).
- **`claude_challenger_1/2/3`** — Claude Code-authored challenger bots in the unattended arms
  race; 1 and 2 pushed as `e7b79f9` and `4078dda`, 3 unresolved at log end.
- **Sentinel** — fixed-facing turret: 18 damage, one 10-Ti ammo stack per shot, r² ≤ 32,
  3-round reload, ~3-tile-wide corridor, shoots through walls.
- **Gunner** — rotatable ray turret: 10 damage, 2 ammo per shot (5 shots/stack), r² ≤ 13,
  blocked by first building/bot and by walls.
- **Launcher** — building that throws Builder Bots toward a destination; deals no damage;
  same-turn multi-launcher chaining is legal.
- **Ground map / actual map** — Lucas's terms: static terrain+cores only vs. everything
  including temporary entities.
- **Grapevine / common information registry / global communication store** — the 64-byte
  (16 × 32-bit slots) shared store; writes visible one round later.
- **Combinadic map encoding** — combinatorial-number-system ranking of wall/ore sets; every
  known map ≤ 29 bytes.
- **`fcode`** — the game engine/CLI (v2.2.0 at the time); `.map26` map files (protobuf wire);
  `.replay26` replays; 10 ms TLE; 1,000-turn cap decided by stored-titanium tiebreak;
  `resign()` destroys own Core.

## Chunk synthesis

1. **Jon owns the shared repo** (`github.com/jonathantybirk/florent-code-league`); Lucas's
   `x/luc` branch was only created 2026-07-27 (Session 2 end), and `main` was updated by
   cherry-extracting Jon's `docs/` from `x/jon` (Sessions 3–4, commits `a7035ef`, `7cd9a84`,
   `40650fc`).
2. **The 15-map pool is documented as complete but mutable between rounds**; no promise of
   hidden final maps (Session 1). This premise underlies both the atlas hardcoding (4-bit map
   ID) and all "known map" logic.
3. **Rotational canonicalization + combinadic sets beat clever geometry**: every known map fits
   in ≤ 29 bytes of the 64-byte store; aurora (227 bits), not hive (164 bits), is the worst
   case; arbitrary maps provably cannot all fit (3^338 ≈ 2^536 > 2^512).
4. **Map identity vs occupancy must be separate evidence classes**: the resign-destroys-Core
   incident (twins, round 80, tile `(2,17)`) showed a missing Core must not refute a map
   hypothesis mid-game — Lucas's insistence that "the inferred cache cannot be wrong" was
   vindicated, and the lock "fix" was a masking workaround.
5. **The engine removes any unit whose `run()` raises** — crashes look like self-deletion
   (bot 19, frame 101, `GameError: Position out of vision range`). Every "bots delete
   themselves" report in this chunk was an exception, not `self_destruct()`.
6. **Store writes land one round later**, which caused the role-assignment race twice; the
   stable protocol is per-spawn-index ID slots written at spawn time and read on the newborn's
   first turn. Lucas personally specified the final protocol.
7. **Same-turn launcher chaining is legal and powerful**: sequential launcher execution can
   relay one bot across the map in a single frame (`(6,4)→(8,9)→(13,13)→(16,18)`).
8. **Lucas's recurring style directives**: simplicity over coordination ("You're overengineering
   it… Speed is key, so waiting is bad"), ownership-agnostic logistics ("literally just ignore
   the team"), keep heuristics but add fallbacks rather than replacing rules wholesale ("keep
   the rule but… default back to going there manually").
9. **Jon's `lockin` won by architecture theft + targeted counter-tuning** (map/side-specific
   attacker counts and spawn delays), beating the then-champion 8–7 and its successor 14–1;
   Lucas's response direction — "look at his code and do better" — legitimized reading
   opponents' pushed code.
10. **The single most valuable tactical discovery of the chunk**: parking a Builder Bot on the
    final core-feeding conveyor denies the supply-line takeover entirely (bots on belts don't
    block titanium; belts can only be attacked from on top). This one change moved 2/30 → 12/30
    and anchored the 11–4 comeback.
11. **Attacker-count sweeps showed pressure count matters more than spawn delays**, but has a
    hard ceiling: 5 attackers/no economy loses outright; the winning shape was map/side-specific
    allocation plus economy preservation.
12. **Fixed-strategy benchmarks were nondeterministic due to Python set-iteration order**; only
    fixed-hash-seed repeats made the 11–4 acceptance reproducible. (Whether the unstable
    tie-breaks were actually removed from the bot is not confirmed in-log.)
13. **The 10 ms TLE is a cliff, not a slope**: at 10 ms challenger 2 sat inert (zero mining,
    1,000-turn loss), at 15 ms it won by rush. Startup costs dominated: first Core strategy call
    21.1 ms; per-ore full-map BFS in `ordered_ores` (fixed by one reverse BFS from the Core
    perimeter — atoll went from stalemate to a turn-88 kill) and all-15-map parsing per spawned
    entity.
14. **Turn-cap games are decided by stored titanium**, and "more economy" can be fake: turn-cap
    replays showed zero titanium delivered to either core, so skipping the second infrastructure
    project (banking the costs) flipped atoll/hive/longship/twins with margins +32/+132/+84 and
    2,827 vs 2,712.
15. **The matchup is strongly side-asymmetric**: identical or near-identical bots mostly hand
    the win to Team A (duel's turn-56 kill flips with side); every acceptance gate from
    ~17:00Z onward required both orientations (30 games).
16. **The benchmark-harness "module leak" scare was disproved** by direct adversarial test: the
    in-process runner gives each bot an isolated import namespace — worth remembering before
    re-suspecting it.
17. **Codex restored uncommitted pre-change code byte-for-byte from its own session edit
    history** after a partial IDE undo — the day's work was uncommitted for hours, and the
    interim "before" states existed nowhere in git.
18. **The unattended arms race produced 4 pushed versions in ~2.5 hours** (`7e0cb63` codex v1 →
    `e7b79f9` claude v1 → `1820079` codex v2 → `4078dda` claude v2 at 7–23, pushed only because
    Lucas said push every version); champion `bots/1` at codex v2 was never beaten in-log.

### Loose ends at chunk close (2026-07-28T19:53Z)
- `claude_challenger_3` was mid-analysis (target >15/30 vs champion `1820079`); no result, no
  codex v3, and Lucas had not yet returned.
- `decode_map_info` (registry → map updates, i.e. actually *transmitting* the map over the
  store) is still a `pass` scaffold; the combinadic encoding was designed but never wired in.
- The one-BFS `ordered_ores` optimization and lazy map loading live only in
  `bots/claude_challenger_2` — the champion `bots/1` still carries the slow startup path.
- Unstable set-iteration tie-breaks flagged as making results irreproducible; removal was stated
  as intent, not confirmed done.
- Jon was actively pushing (`lockin` → `frontier` within hours); all scores in this chunk are
  against moving targets `a82a069`/`4d85b48`.
- The `bots/adaptive_v1` directory sitting in Lucas's *workspace* (noticed at 16:17Z when Lucas
  said "adaptive") had unexplained provenance — likely Jon's bot copied locally, never resolved
  in-log.
