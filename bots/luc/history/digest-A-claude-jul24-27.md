# Digest A — Claude Code sessions, 2026-07-24 → 2026-07-27 (earliest chunk)

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

Scope: 10 transcripts across two successive project clones — `~/projects/florent` (Jul 24 → Jul 25 morning) and `~/projects/florent-code-league` (from Jul 25 10:43). This chunk predates every named competition bot (no prospect/warden/etc., no jonbot/vanguard/tempest, no tournament harness). It is the learning-the-game phase: tutorial bots, engine-vs-docs discrepancies, map reverse-engineering, and execution-model research. Sessions chain via `/clear`, so each file's tail timestamp is the next file's head.

---

## Session 1 — 74db7399 (2026-07-24T14:36 → 14:39 active; file closes 15:07)
**Where:** `~/projects/florent`, via VS Code/Cursor IDE. **Goal:** code-organization advice for the tutorial bot.

Lucas wanted to add `update_core_pos` to the `Player` class of the starter/tutorial bot (`bots/starter/Tut1.py`, `bots/starter/utils.py`) and asked how to keep helpers out of the class file. Claude explained stateless helpers belong in `utils.py`, `self`-using ones in the class, and noted the existing `utils.py` was broken (`update_core_pos` references `self` with none; `cardinal_direction_to` takes `self` then overwrites it). Options offered: method in class (recommended), thin-wrapper split, or a mixin (`PlayerHelpers` in `helpers.py`); monkey-patching discouraged.

**Lucas directive:** he explicitly disagreed with "a file with one class + its methods is not messy" — "some of the methods contain actual logic and others are simple helper functions that I don't want to be taking up attention when I'm looking at the file." Claude then endorsed the mixin pattern for stateful helpers. Session ends before any edit is confirmed applied.

**New names:** `Player` class (bot entry point); `Controller` (`ct`, the game API); `bots/starter/` (the first bot, from the tutorial).

## Session 2 — 4cbba881 (2026-07-24T15:07 → 15:09; file closes 15:15)
**Goal:** tooling. Lucas asked how to make Cursor auto-activate the venv in every terminal. Claude created `.vscode/settings.json` with `python.defaultInterpreterPath: ${workspaceFolder}/venv/bin/python` and `python.terminal.activateEnvironment: true`. Not competition-strategy relevant beyond confirming the early setup used a plain `venv` (the later repo uses uv).

## Session 3 — 9bb235c7 (2026-07-24T15:15 → 15:16, interrupted; file closes 22:35)
**Goal:** explain a runtime bug — but Lucas interrupted before any answer was produced.

Lucas pasted output of the first recorded local matches, `fcode run starter starter` on `atoll.map26`, Seed 1, TLE off. Errors: `AttributeError: 'Player' object has no attribute 'get_position'` and repeatedly `AttributeError: 'Player' object has no attribute '_lay_conveyor_toward_core'` (from `main.py` line 42 in `_run_builder`) — almost certainly fallout from the session-1 helper reorganization. Exact match results pasted:
- Run 1: `Winner: starter (Harvesters (tiebreak), turn 1000)`; Titanium `12 (0 mined)` vs `13 (0 mined)`; Units 0/0; Buildings 1/2.
- Run 2: `Winner: starter (Titanium stored (tiebreak), turn 1000)`; Titanium `182 (0 mined)` vs `43 (0 mined)`; Units 23/24; Buildings 5/5.

These are the earliest match outputs in the archive; both games went the full 1000 turns and were decided on tiebreaks. `[Request interrupted by user]` — no analysis given.

**New names:** `fcode run` (local match CLI); `.replay26` (replay format); `atoll.map26` (the default map, as later confirmed).

## Session 4 — 7688cbab (2026-07-24T22:35 → ~22:44; file closes 22:58)
**Goal:** reconcile a tutorial ("Building an Army: Turrets & Combat · Step 3 of 5") with the installed engine — the tutorial referenced ammo methods that don't exist.

The tutorial claimed ammo is a team-wide balance filled by `ct.convert_ammo(amount)` at the Core (1:1 from titanium, once per turn), checked with `ct.can_convert_ammo` / `ct.get_global_ammo`. Claude grepped the type stub (`venv/.../fcode/_types.py`), the Python sources, and the compiled Rust engine: **none of the three methods exist anywhere**. Findings, the first major engine-truth discovery of the competition:
- Ammo is **per-turret and physical**, not a shared pool. Real methods: `get_ammo_amount() -> int`, `get_ammo_type() -> ResourceType | None` (`_types.py:265-271`).
- Ammo is **delivered by conveyors** (harvester mines ore → conveyors/splitters carry it → item loads into the turret). No titanium→ammo conversion exists. Engine symbols confirming: `consume_feed`, `receive_resource`, `feeder`/`receiver`, `assertion failed: self.ammo_amount == 0`. Starter-bot comment: "gunners need ammo delivered via conveyors to fire… that's an exercise for the player!"
- Correct tutorial bits: `GUNNER_AMMO_COST = 2` (`_types.py:94`), sentinels cost 10; `fire`/`can_fire`/`get_gunner_target` are real.

Follow-up Q&A on healing: `heal(pos)` heals **all** friendly entities on the tile by 4 HP each (`HEAL_AMOUNT = 4`, `_types.py:90`) for a flat 1 titanium (`BUILDER_BOT_HEAL_COST = 1`, `_types.py:89`) regardless of entity count; requires action cooldown == 0, ≥1 titanium, and at least one damaged friendly on the tile; range limited by `ACTION_RADIUS_SQ = 2` (`_types.py:52`). No named `HEAL_COOLDOWN` constant exists — "one action cooldown" is all the stub documents (exact value left unverified).

**New names/mechanics:** Gunner (2 ammo/shot), Sentinel (10 ammo/shot), Launcher (uses no ammo), harvester/conveyor/splitter supply chain, `heal` AoE-per-tile.

## Session 5 — 978f76fb (2026-07-24T22:58 → 23:44; file closes 2026-07-25T10:28)
**Goal:** fix splitter placement in tut5; then probe the engine's state-isolation model.

1. **Splitter fix.** Lucas: "inspired by how I implemented it in tut4 (i believe, or maybe starter) can you fix the splitter placement in tut5? It should point the same direction as the last conveyor." Claude ported the starter's `self.prev_d` pattern into `tut5/main.py` (record the direction of each successfully-built conveyor; build the splitter pointing `prev_d`, falling back to `d` if no conveyor was laid). Lucas pressed on splitter semantics; Claude checked `data/docs/spec.md:152` and issued an honest correction: **Splitter = 3 outputs (primary direction + the two adjacent), only 1 input (the back)**; its own earlier "change #2" (gunner-side exclusion) was wrong and could aim the gunner into the core tile on a turning path — fixed to exclude `d` (core) and `splitter_dir.opposite()` (back).
2. **Conveyor vs splitter, canonical statement** (after Lucas asked Claude to "explain the difference better than I did" than his Danish note to teammates): Conveyor = 1 output (facing), 3 inputs (all other sides); Splitter = 3 outputs, 1 input (back only). The sample code pointed the splitter at the core like a conveyor, so the belt fed an output face and was rejected — works only when the chain runs straight into the core, breaks when it turns on the final tile. Claude also produced a polished Danish rewrite of the teammate note.
   - **Lucas directive:** "Omg I wanted a concise description. Don't think for this one." — he wanted the short version, not an essay. Claude gave a 4-line answer.
3. **State model.** Confirmed from docs: "Each unit gets its own Player instance"; units run "an independent instance of the code that you submit." So `self.` attributes are per-unit. Cross-unit sharing only via the **Global Communication Store**: `write_store(index, value)` / `read_store(index)`, **16 slots** (`STORE_SIZE = 16`), each a **u32 (0 to 2³²−1 = 4,294,967,295)**, writes buffered one round (readable next round, even by the writer). Packing idiom: two 16-bit values via `(x << 16) | y`.
4. **Isolation deep-dive.** The engine runs bots in **`Py_NewInterpreterFromConfig` SHARED_GIL sub-interpreters** with a hardened sandbox (`_thread`/`threading` no-op'd, `importlib.reload` deleted). One **documented leak** (`_types.py:226-229`): Python methods on a Controller class pollute the Rust Controller's method resolution across sub-interpreters — **never name `Player` methods after Controller API methods** (`move`, `build`, `spawn_builder`, `read_store`, …). The unresolved question: sub-interpreter granularity per-unit vs per-team, which decides whether module-level globals are a hidden cross-unit channel. Claude added an `id(self)` print plus a `LEAK_PROBE` module-global counter to `tut5/main.py` to settle it empirically (Lucas: "Just insert print statements into main.py in tut5"). **The probe's result is never pasted back in this chunk — question left open.** Cleanup note: strip the probe before competing (per-unit-per-round print "will burn into your 10ms/turn budget" — first mention of the 10 ms CPU cap).

## Session 6 — 4f69e9cd (2026-07-25T10:28)
A lone `/clear`. Nothing else. Not relevant.

## Session 7 — df28cf5f (2026-07-25T10:43 → 13:50) — first session in `~/projects/florent-code-league`
**Goal:** mirror the official docs locally, then correct them against the engine.

1. Scraped **all 20 pages** under `https://game.code.florent.vc/docs/` into `docs/` (getting-started/, cli/ ×5, game-rules/ ×10, api-reference/ ×3 incl. `robot-api.md`, `api-types.md`, `global-comms.md`, agents/agents-md.md), with a README index and rewritten cross-links. Caveat noted: WebFetch markdown conversion isn't byte-exact.
2. Lucas: "In one of our previous convos, we discovered that the ammo system works differently than described in the docs. Can we fix that? … Also we can add in the docs for splitters that they only have one input side." Claude found the session-4 finding in the sibling `florent` project transcript, **re-verified against the currently installed `fcode`** (the three phantom methods still absent), and patched four files with explicit "Correction vs. the official docs" callouts rather than silent rewrites: `game-rules-core.md` (replaced the "Convert Ammunition" section), `game-rules-turrets.md`, `robot-api.md` (removed the 3 nonexistent methods, added the 2 real ones), `agents-md.md`. Splitter single-input made explicit in `game-rules-conveyors.md` and `api-types.md`. Notably: **the official website docs repeat the same wrong team-ammo model the fake-looking tutorial had** — so the discrepancy is docs-vs-engine, not just tutorial-vs-engine. Claude flagged the possibility the docs describe a different/newer engine build; installed `fcode` treated as authoritative.
3. **Lucas hand-edit + directive:** he rewrote the turrets paragraph himself — key clarification that **ammo *is* titanium** ("Gunners and Sentinels consume ammo (titanium) held inside each individual turret… deliver titanium to it via conveyors… 2 for a Gunner, 10 for a Sentinel… Launchers use no ammo") — and said "Standardize." Claude propagated "ammo is titanium" across all four callouts and updated its memory note.
4. 13:50: Lucas worried he'd accidentally overwritten `game-rules-turrets.md`; Claude verified all 70 lines intact.

## Session 8 — daec7bf5 (2026-07-25T14:08 → 15:44) — the 6.8 MB session
**Goal:** understand map selection, then build a visual atlas of all 15 maps matching the game's own renderers.

1. **Map selection mechanics:** `fcode run a b <map>` (name resolved in `maps/`, extension optional); with no map argument it uses `sorted(glob("*.map26"))[0]` → **atoll** (verified later in-session); `--map-random` picks randomly; `--seed N` for determinism; `fcode.toml`'s `maps_dir` only locates the folder. Remote `fcode match test`/`match unrated` with no maps: **the server picks 5 random maps** (ranked-ladder behavior). The 15 local maps: atoll, aurora, crossfire, duel, fjord, hive, longship, pinch, quarry, runestone, skerry, sprint, strait, twins, vault.
2. **`.map26` format reverse-engineered** (undocumented protobuf; parser hand-written since only bundled JS/wasm reads it): `width`, `height`, row-major tile bytes with `0=EMPTY, 1=WALL, 2=ORE_TITANIUM`, plus core positions. Verified on all 15 maps: `row=y, col=x`, maps rotationally symmetric, cores on empty tiles; `sprint` has **zero walls** (an open racing map).
3. **Rendering saga with three Lucas corrections:**
   - Claude began building an interactive artifact; **Lucas interrupted: "Toggle? I just wanted something like a .md file or pdf with each map name followed by screenshots. Ideally exact same visualization as in the replays."** Claude pivoted to static PNGs composited from the game's own bundled sprites.
   - Iso view built from the `dimetric/` tileset: **128×64 dimetric diamonds** (sprites 128×160, floor diamond centered at (64,127)), Core base a 3×3 `base_team*` sprite. Lucas: "you got the iso completely correct, but the square is wrong" → clarified the replay window's top-down mode uses the **root-level flat sprites** (`bg` floor, green `natural_wall`, `titanium_ore`, top-down `base_gold`/`base_silver` cores), while `dimetric/` is the **map editor's** style. Flat renderer rebuilt accordingly.
   - Lucas correction 2: on atoll, **gold belongs bottom-left** — Claude had team colors swapped. Confirmed from replay JS (`displayTeam===A ? gold : silver`): **Team A (owner 1) = gold, starts bottom-left; Team B = silver (flat) / blue (iso), top-right**.
   - Lucas correction 3: **the Core fills a 2×2 tile block and its stored coordinate is the block's top-left tile** — sprites must be centered on the 2×2, not the single tile. Fixed in both views (iso: +32px below anchor).
   - Final iso bug (Lucas: "In iso the core is now off-center, but flat is exactly as I wanted"): the `base_team*` art is authored for a **3×3 footprint** and the editor draws it at **`setScale(2/3)`** with origin `(0.5, ~0.794)` (anchor (192,381)) at `center(col+.5, row+.5)` — Claude had composited it full-size, 1.5× too big. Adding the 2/3 scale fixed it, verified against a red 2×2-outline debug overlay.
4. **Deliverable:** `MAPS.md` + 30 PNGs (~6 MB, e.g. `atoll-iso.png` at 1288×764), then moved to `docs/maps/map-atlas.md` with same-directory image paths (fixing VS Code preview loading) and finally reworked into side-by-side HTML tables (iso `width=460`, top-down `width=380`) per Lucas's request. Per-map stats: grid size, ore-tile count, wall-tile count, Core coordinates.
5. Hygiene: `uv add pillow numpy` had polluted the bot's runtime deps; Claude reverted to just `fcode`. **Lucas directive:** "Where is the scratchpad? please answer without thinking" — another instance of wanting terse, immediate answers.

## Session 9 — 647e4286 (2026-07-25T20:51 → 2026-07-27T07:38, two sittings) + subagent agent-a7e8e581dba386a8f
**Goal:** can the bot have "central command" instead of per-unit control?

**Jul 25 evening.** Lucas: "does anything prevent us from just saving information from each entity elsewhere and thus have central command instead of using the player class exclusively?" An Explore subagent produced the definitive execution-model report (embedded in the main transcript): one `Player` instance per unit, created at unit spawn, **not** re-instantiated per round; `run(ct)` called each round on every living unit **in spawn order, Core first**, with a fresh `Controller` each call; `self` persists for the unit's life and dies with it; the 16-slot buffered store is the only sanctioned cross-unit channel (team-isolated from the opponent); **CPU 10 ms per unit per round plus a banked buffer of up to 5%**, overrun interrupts `run()` mid-execution (unit skips the round); **uncaught exceptions permanently remove the unit from the match**; match ends on Core death or at round 1000; **unit cap 50/team including Core**; building costs scale with team entity count; remote matches run on **AWS Graviton3**. Claude's answer: true real-time central command isn't achievable through documented APIs — the workaround is the Core as pseudo-commander publishing packed summaries into store slots (one round stale). A module-global would work *if* units share a process, but that's undocumented and risky.

**Jul 27 morning.** Lucas pushed back hard: "You really dodged the question. Can't I just save and read from disk for each unit? Then it's just central." Claude conceded disk would mechanically give live intra-round shared state (units run sequentially), retracting its "not achievable" overclaim — but argued it's the worst version of the idea: (1) if units share a process a module-global object is strictly better (no I/O against the 10 ms budget), (2) disk I/O risks the CPU cap especially on remote hardware, (3) it stacks two undocumented assumptions (shared process + writable FS) that may not survive submission sandboxing. Offered a throwaway test bot to measure both assumptions — **not run in this chunk**. Lucas then asked for the Graviton3 reference (given: `game-rules-how-matches-work.md` "Remote Infrastructure" + `cli-submitting.md` upload flow; Claude flagged that "Graviton3 is slower than local" was its own inference, not documented — only "different" is documented, hence "profile remotely"). Final question: "Can we run rust, c or only python? I'm thinking if we need speedups" → **Python only, 3.12 or 3.13 (3.14 explicitly unsupported)**; no documented remote build step; Graviton3 is ARM64 so locally-built x86-64 `.so` files can't load; safe assumption is **pure Python, stdlib + `fcode`, nothing compiled** (even numpy not guaranteed remotely). Speedups must be algorithmic: cache in `self`, stagger heavy work across rounds/units, tight stdlib structures, profile with `ct.get_cpu_time_elapsed()` on remote test matches.

---

## Chunk synthesis

Load-bearing insights (evidence in parentheses):

1. **The official docs and tutorial lie about ammo; the engine is authoritative.** `convert_ammo` / `can_convert_ammo` / `get_global_ammo` exist nowhere (stub, sources, compiled Rust — session 4, re-verified session 7). Ammo is titanium stored per-turret, delivered via conveyors; Gunner shot = 2, Sentinel = 10, Launcher uses none. This is the founding "verify against the engine, not the docs" precedent for the whole competition.
2. **Splitter vs conveyor asymmetry** (spec.md:152, sessions 5+7): Conveyor = 1 output (facing) / 3 inputs; Splitter = 3 outputs (facing + adjacent) / 1 input (the back). Point a splitter the same way as the last conveyor (`prev_d`), never "toward the core" — the toward-core version only works on straight chains. Lucas relayed this to teammates in Danish; the sample code everyone starts from has this bug.
3. **One `Player` instance per unit, persisting across rounds** (subagent report, session 9; docs, session 5). `self` is per-unit memory; a fresh `Controller` arrives every `run()`. Units execute in spawn order, Core first, each round.
4. **The only guaranteed cross-unit channel is the Global Communication Store: 16 u32 slots, writes buffered one round** (sessions 5, 9). Pack with `(x << 16) | y`. Central command is therefore "central summary, one tick stale" — Core as pseudo-commander.
5. **Sub-interpreter sandbox with one documented leak** (`_types.py:226-229`, session 5): bot-defined methods named like Controller methods get incorrectly bound across sub-interpreters. Rule: never name `Player` methods `move`, `build`, `spawn_builder`, etc.
6. **CPU budget: 10 ms per unit per round + up to 5% banked; overrun interrupts `run()` mid-execution; uncaught exceptions permanently kill the unit** (session 9). Exceptions are stricter than timeouts.
7. **Hard platform constraints** (session 9): Python 3.12/3.13 only; ranked matches on AWS Graviton3 (ARM64) — no native extensions, assume stdlib + `fcode` only; ladder pairings are best-of-five on 5 server-chosen random maps; unit cap 50/team; match ends at Core death or round 1000; building costs scale with team entity count.
8. **`.map26` is undocumented protobuf**, reverse-engineered in session 8: width/height, row-major tiles `0=EMPTY, 1=WALL, 2=ORE_TITANIUM`, core positions. (Direct ancestor of the later `.replay26`-is-protobuf finding in memory.)
9. **Map geography facts** (session 8): 15 shipped maps; default local map = `sorted(...)[0]` = atoll; all maps rotationally symmetric; sprint has zero walls; coordinate system (0,0)=NW, x→east, y→south.
10. **Core occupies a 2×2 block; its stored coordinate is the top-left tile** (Lucas's own correction, session 8). Team A (owner 1) = gold, starts bottom-left; Team B = silver/blue, top-right. Renderer detail: iso base art is a 3×3-footprint sprite drawn at scale 2/3.
11. **Two renderers ship in `fcode`:** the map editor uses the `dimetric/` iso tileset (128×64 diamonds); the replay window's top-down uses the root flat sprites. Distinguishing them took three correction rounds from Lucas.
12. **`heal(pos)` is an AoE-per-tile bargain** (session 4): +4 HP to every damaged friendly on the tile for a flat 1 titanium, range `ACTION_RADIUS_SQ = 2`, requires a damaged friendly present.
13. **Earliest match evidence** (session 3): starter-vs-starter on atoll goes the full 1000 turns and resolves on tiebreaks ("Harvesters" then "Titanium stored" — 182 vs 43 titanium in the second run). Also first bug class of the project: helper-refactor `AttributeError`s.
14. **Lucas's working style, established this early:** wants concise answers ("Omg I wanted a concise description. Don't think for this one"; "please answer without thinking"), calls out dodged questions ("You really dodged the question"), asks for source references before believing hardware claims, hand-edits docs and asks Claude to "Standardize", and prefers static `.md`/PDF deliverables over interactive apps. He also disagrees with one-class-per-file orthodoxy — helpers must live out of sight of strategy logic.
15. **Docs mirror with correction callouts** lives in `docs/` (20 scraped pages + `docs/maps/map-atlas.md`); corrections are explicit callouts, never silent rewrites, each page keeps a `Source:` line.

**Loose ends at chunk close (2026-07-27T07:38):**
- The **per-unit vs per-team sub-interpreter question is unresolved** — the `LEAK_PROBE` module-global counter was inserted into `tut5/main.py` (session 5) but its output never came back; likewise the offered test bot for module-global sharing and filesystem writability (session 9) was never run. Whether module globals are a usable cross-unit channel is still open.
- The **disk/module-global central-command idea is live but unproven**; Lucas clearly wants more shared state than 16 u32 slots.
- The `heal` cooldown's exact value was never pinned (no `HEAL_COOLDOWN` constant).
- Whether the website docs describe a newer engine (making `convert_ammo` real someday) was flagged and left unreconciled.
- The flat-view floor rendering (`bg.png` tiled per cell, subtle seams) was never confirmed against an actual replay window.
- **No competitive bot exists yet** — only `starter` and tutorial bots tut1–tut5; no tournament harness, no ratings, and no opponent (Jon/Elias/Viktor) has appeared in any transcript.
