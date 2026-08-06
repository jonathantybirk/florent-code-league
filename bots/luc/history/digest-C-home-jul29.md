# Digest C — HOME session 62ed4cbb, 2026-07-28 → 2026-07-29

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

**Transcript:** `/home/Ucals/.claude/projects/-home-Ucals/62ed4cbb-4892-462a-ac19-e731c161d963.jsonl` (1823 lines, cwd `/home/Ucals`)
**Span:** first user message 2026-07-28T13:11:01Z → last activity 2026-07-29T19:28:50Z (ends on a user interrupt mid-debug). Two `/compact` events: 2026-07-28T14:09 and 2026-07-29T19:02.

## Verification: this is NOT the evaluator-timer session

The chunk briefing guessed this session set up `botrankings-evaluator.timer` / the `florent-code-league-ci` worktree. **It did not.** Greps over the full JSONL: `botrankings` 0 hits, `florent-code-league-ci` 0 hits, `mElo` 0 hits. The 1300+ "competition" mentions are the repo path `florent-code-league-llm-rl` recurring in tool output. The only systemd content (9 hits) is a Cisco VPN daemon fix. **This session is the genesis of the RL side project** — it created the very clone (`~/projects/florent-code-league-llm-rl`, branch `x/llm-RL`) that the present digest task is running from.

## Goal (Lucas, 13:11): 
> "I kind of want to try to do an alphago/openai five inspired RL-model on the game in florent-code-league… create a new branch… Call it x/llm-RL… also copy over the hpc docs."

A self-play PPO bot for the Florent Code League game, developed in a second clone so as not to disturb ongoing `x/luc` work, trained on DTU HPC, eventually exportable to the ladder.

## Narrative

### Phase 1 — Scaffold (Jul 28, 13:11–13:43)
- New clone at `~/projects/florent-code-league-llm-rl`, branch `x/llm-RL` off `main`, pushed. HPC docs copied from `~/projects/case-crunch-2026/docs/HPC-docs.txt` into `docs/hpc/`.
- RL scaffold built and smoke-tested end-to-end (commit `315d789`): `rl/policy.py` (shared-trunk actor-critic, per-entity-type heads), `rl/ppo.py` (clipped PPO + GAE), `rl/features.py` (7×7 local grid ×6 channels + 12 scalars + type one-hot; macro-actions per entity type), `rl/self_play.py` (training loop), `bots/rl/main.py` (bot entrypoint), `bots/opponent_luc/` (copy of the `x/luc` bot `bots/1` as fixed training opponent), `scripts/hpc_train.sh` (bsub script).
- **Two engine constraints discovered the hard way:**
  1. The fcode engine runs each unit's bot in its own **Python sub-interpreter**; torch/numpy (any single-phase-init C extension) cannot be imported twice per process → inference moved into `rl/inference_server.py`, a Unix-socket server; the bot itself is pure stdlib.
  2. Running `fcode_engine.run_game` in the same process as torch autograd broke `.backward()` (GIL conflict) → each match runs as a subprocess (`rl/play_one_game.py`).
- Baseline: full 1000-round match vs the x/luc bot in ~7–9s locally; untrained policy loses every game (expected).

### Phase 2 — "Will it run on their server?" judgment call (13:47–13:53)
Lucas: "Make a judgement call on whether this will run on the AWS server… also log progress to wandb."
- Verdict: **the socket-based bot will not work when submitted.** Ladder matches run on AWS Graviton3 under a 10ms-per-turn CPU limit; sandboxed judges don't allow sockets/subprocesses. (Later confirmed via docs: "Each unit gets 10ms CPU time per turn (with a small rolling 5% buffer)" — the budget is per-unit-per-turn.)
- Fix (commit `f975887`): shrunk net 256/128 → 64/32; new `rl/export_pure_python.py` bakes a checkpoint into `bots/rl_deploy/` — stdlib-only, JSON weights, manual matmul/relu/argmax. Measured **~0.56ms per forward pass**; a full 1000-round match under `--tle 10` finished with **zero timeout penalties**.
- wandb wired as opt-in (`--wandb`; `WANDB=1 bsub < scripts/hpc_train.sh`).

### Phase 3 — DTU HPC access plumbing (13:56–14:09, sysadmin, summarized)
Teammate **jonathantybirk**'s SSH notes were pasted in; then: Cisco Secure Client VPN failure fixed (disabled `vpnagentd.service` had spawned an unprivileged daemon; sudo script: `pkill` + `systemctl enable --now vpnagentd`); dedicated key `~/.ssh/gbar` generated and installed (gotchas: `transfer.gbar.dtu.dk` was SFTP-only → use `login1.gbar.dtu.dk`; `DISPLAY=:0` silently routed passwords to a missing GUI askpass → `SSH_ASKPASS_REQUIRE=never`); `~/.ssh/config` `Host dtu` with `ControlMaster auto` / `ControlPersist 8h`. Result: no-VPN HPC access (key passphrase + DTU password) and a persistent control socket the agent reuses without prompts. First `/compact` here.

### Phase 4 — First HPC training runs and four pipeline bugs (14:12–14:48)
- Repo **rsynced** to HPC rather than cloned (repo is private; avoided GitHub auth on gbar). `uv` installed; `module load python3/3.13.14` → `3.13.11` (3.13.14 doesn't exist there; commit `2d0c868`). Lucas pasted his wandb API key directly in chat; Claude flagged it should be rotated at wandb.ai/settings.
- **Job 28975482** (gpuv100 queue) crashed: `run_game`'s `seed` is a strict `int` (default `1`), but `play_one_game.py` passed `args.seed` positionally — `None` whenever `--seed` was omitted. Fixed via conditional kwargs (commit `c61c5d4`); **job 28975507** resubmitted — 20 iterations / checkpoint saved within ~6 minutes.
- **GPU was pure waste**: no `.cuda()`/`.to()` anywhere in `rl/`; also the installed `torch==2.13.0+cu130` wheel lacks kernels for the V100's compute capability 7.0. Lucas interrupted: **"Don't allocate gpu time if you don't use it!"** → job moved to CPU-only `hpc` queue, GPU directives and `cuda/12.6` module dropped (commit `1909175`, job **28975560**).
- **wandb silently absent**: LSF `bsub` does not inherit the submitting shell's env; `WANDB=1 bsub < script` never reached the job. Fix: `bsub -env "all"`.
- **Single-core training**: `bstat -C` showed **18.4% CPU efficiency on 4 cores** — `self_play.py` ran matches strictly sequentially. Lucas: "It is very slow then, are we utilizing multiple cores?" → "Yes" to the fix. Implemented parallel match collection (`ThreadPoolExecutor`, worker count from `LSB_DJOB_NUMPROC`), threaded the inference server's connection handling, and added replay archiving (`runs/replays/archive/iterN.replay26` every `--save-every`; previously the sole replay was overwritten each match). Local check: 3 matches concurrently in ~12–16s total vs ~4–5s each sequentially (commit `f648743`). **Job 28975588**, 8 cores.

### Phase 5 — Model Q&A (14:18–14:43, exact mechanics)
Answers to Lucas's questions, read from code not memory:
- Original action space: CORE 9 (NOOP + spawn ×8 dirs), BUILDER_BOT 14, GUNNER 4 (NOOP/FIRE/rotate L/R), SENTINEL 2 (NOOP/FIRE), LAUNCHER 1 (NOOP only — throwing builders via `ct.launch()` a flagged known gap).
- Reward (`_team_round_rewards`): dense per-round **+1/200 per titanium gained, +1/10 per net unit gained**, terminal **±5.0** win/loss (draw ±0); same team-level reward to all units that acted (no per-unit credit assignment).
- `match/winner_is_a` is 1/0 (0.5 on draw); one `wandb.log` = one complete match (up to 1000 rounds).
- Opponent: every match vs `opponent_luc`; `--opponent self` mirror-mode exists but was never used this session.
- Maps: `random.choice` from a 15-map pool per match.

### Phase 6 — First learning check (15:28): losing catastrophically
From the wandb API (stdout was buffered): entropy falling 2.58 → ~2.0 over 48 iterations (builder_bot) — a real learning signal — but **0 wins / 384 losses / 0 draws**, `avg_a_titanium: 14.625` vs `avg_b_titanium: 17841.75`, `avg_a_units: 3.375` vs `avg_b_units: 6.25`. Claude's read: not "early training," but a structurally broken economy loop (the untrained smoke test still held its 3000 starting titanium; the *trained* bot bleeds to ~zero).

### Phase 7 — The big redesign (15:57–16:15, commit `0ed7b99`)
Lucas's detailed spec (verbatim core): different actions; "a very information dense network given our 10ms constraints… the current version runs in appx 1ms right?, so we can easily 5x the size"; pass the map **as computed by the x/luc bot** (and update that algorithm to the newest version from the other branch) every turn with a staleness layer and the recognized map filled in, highlighting the controlled unit; feed the global communication store and let the model write per-slot; conveyor always placed beneath with chosen direction; turrets always directly north with 8-way facing; harvester in closest cell; heal; sabotage/destroy; sentinels buildable like turrets; **individual model per entity type**.

Claude answered with analysis first, flagging engine-API conflicts ("misses") before writing code:
1. `ct.fire()` can never target the builder's own tile → "sabotage the unit it's standing on" is impossible; implemented as fire-north-else-scan-cardinals.
2. `ct.fire()` only damages **buildings**, never units — the engine simply has no builder-kills-unit capability.
3. Conveyor facing is cardinal-only (4-way); turret facing is 8-way — asymmetric by rule.
4. Sentinel facing is **permanent** (`rotate()` is Gunner-only) — a one-shot, irreversible build decision PPO may underweight.
5. Fixed-direction placement silently no-ops when the target tile is blocked (accepted trade-off, kept deliberately dumb rather than re-hiding the decision behind heuristics).
- **Feasibility math that shaped the design**: maps range 10×10 to 28×20; naive full-map flatten ≈ 5,600 input floats ≈ est. 80–100ms in pure Python — would blow the 10ms budget. Chosen hybrid: 7×7 local patch + **8×8 coarse whole-map grid** (max-pooled channels + recency `1/(1+age)` + self-mask), with terrain backfilled once map identity is inferred — the map-identity trick ported from x/luc's `bots/1/utils/map.py` into new stdlib-only `rl/map_memory.py`.
- Comm store (16 team-private int slots, one-round commit delay, last-writer-wins): write implemented as **macro-actions restricted to Core and Builder Bot** (B_BROADCAST_POS → slots 0/1; C_BROADCAST_COUNT → slot 2), deferring the full factored 16-slot write head.
- New shapes: `NUM_ACTIONS = {CORE: 10, BUILDER_BOT: 34, GUNNER: 4, SENTINEL: 2, LAUNCHER: 1}`; `RICH_OBS_DIM = 839`, `LIGHT_OBS_DIM = 27`; per-type independent nets `HIDDEN_DIMS = {CORE: (48,24), BUILDER_BOT: (96,48), GUNNER: (16,8), SENTINEL: (16,8), LAUNCHER: (8,8)}` (shared trunk abandoned).
- `opponent_luc` refreshed from x/luc's committed HEAD `83771dd` ("Fix deletion upon impossible command") — deliberately not the uncommitted WIP seen earlier.
- Measured pure-Python timings: CORE **0.984ms**, BUILDER_BOT **2.172ms**, GUNNER/SENTINEL **0.018ms**, LAUNCHER **0.010ms**; map-memory: local_patch 0.015ms, coarse_grid worst case 0.193ms, aging 676 tiles 0.022ms. Real match on `aurora` under `--tle 10`: no TLE, no crash (winner: B, 1000 turns). Old checkpoints incompatible → wiped; **job 28976582** (8 cores, wandb run `qfyswdhj`).

### Phase 8 — Core-scaling saga (17:19 → 20:12)
- Progress check at 17:19: **68 iterations / 544 matches, still 0 wins**; ~8 titanium vs opponent's ~10,500; ~3 units vs ~12. Same collapse pattern before and after the redesign.
- Lucas: "you can scale up to way more cores, like 50?" → job **28976740** at 50 cores, `span[hosts=1]` (thread-pool parallelism needs one node) + `rusage[mem=32GB]` (commit `58702f0`). It **pended 2.5 hours (9051s) and never scheduled** — most standard `hpc`-queue nodes have 32/40 cores; the queue had ~8,200+ jobs. Killed; resubmitted at **32 cores** (job **28976890**, commit `6f9ab9f`). Still `PEND` at ~20.3 min when Jul 28 activity ended. (Several "user" messages in this stretch are scheduled check-in prompts Claude had queued for itself — e.g. "Check job 28976890… if pending longer than ~20-30 minutes, propose dropping further (e.g. to 16 cores)…" — not hand-typed Lucas text.)

### Phase 9 — Jul 29 resume: kill it and debug (19:02–19:28)
- Second `/compact`; Lucas: "Is it still going?" The 8h ControlPersist socket had expired; Lucas re-established it ("i did").
- Job 28976890 had been **running 8:09:37** (wandb run `h1cyllzm`) — but **CPU efficiency only 23.31% on 32 cores** (barely above the pre-fix 18.4%; suspected inference-server/thread-pool serialization, unresolved).
- Training verdict, exact wandb history at `_step 556`: `record/wins: 0, record/losses: 17792, record/draws: 0`, `match/avg_a_titanium: 354.875` vs `avg_b_titanium: 9081.4375`, `match/avg_a_units: 0.625` vs `avg_b_units: 11.90625`, `avg_turns: 491.34375`. **Zero wins in 17,792 matches**, and average own units alive dropped below one.
- Claude recommended killing the job and debugging locally; Lucas: **"yes kill it."**
- Decision-log dig on one 921-round match: Core picked action 8 in **465/922** logged turns; unit count oscillated 1→2→1 all match; **~230 successful spawns but only 2 Builder Bot decisions logged in total** — Builder Bots are destroyed within about one round of spawning, so the policy's builder net almost never even acts. Claude also noted the reward's unit-count delta term "could be reinforcing degenerate behavior" (spawn/die churn), but called the fast builder deaths the deeper question. It was about to run a fresh local match to catch runtime exceptions in the builder decision path (discarding a stale pre-redesign checkpoint) when **Lucas interrupted at 19:28:50Z — the session ends there, root cause unfound.**

## Lucas's stated directives and preferences
- **"Don't allocate gpu time if you don't use it!"** — standing correction; all subsequent jobs CPU-only.
- Secrets typed by him only, and in a separate real terminal (the embedded `!` channel mangled password entry: "It's not working in this gui, I need a seperate terminal").
- Comfortable pasting his wandb API key in chat despite the rotation warning (`wandb_v1_2Yo9…` now in transcript history; rotation never confirmed).
- Approve-then-delegate pattern: analysis first, then "give it a shot" / "Yes" / "yes kill it".
- Wants observability: replays watchable (`fcode watch`), one-liner rsync commands to his Downloads folder, wandb dashboards, honest "is it learning anything?" reads.

## New names (one-liners)
- **`x/llm-RL`** — new branch/clone (`~/projects/florent-code-league-llm-rl`) hosting the RL effort, isolated from `x/luc`.
- **`bots/rl`** — the RL bot entrypoint (pure stdlib socket client during training).
- **`bots/rl_deploy`** — generated, gitignored ladder-ready export: JSON weights + manual matmul, no torch/numpy/sockets.
- **`bots/opponent_luc`** — frozen copy of the x/luc bot `bots/1`, the fixed training opponent (refreshed to HEAD `83771dd` mid-session).
- **`rl/inference_server.py`** — Unix-socket action server dodging the engine's per-unit sub-interpreter torch/numpy import limit.
- **`rl/map_memory.py`** — stdlib port of x/luc's persistent map memory + map-identity inference over bundled `.map26` files.
- **Global communication store** — 16 team-private int slots, one-round write delay, last-writer-wins; read by all types, written only by Core/Builder macro-actions.
- **DTU HPC / gbar** — LSF cluster (`bsub`/`bstat`/`bhist`, queues `gpuv100`, `hpc`); jonathantybirk = teammate whose SSH notes seeded the access setup.

## Chunk synthesis

**Load-bearing insights:**
1. **Misattribution corrected**: this session is the RL project's origin, not the ladder-evaluator setup — zero transcript mentions of `botrankings`, `florent-code-league-ci`, or mElo. Any digest of continuous-evaluation infrastructure must come from a different session.
2. **Ladder deployability drove the whole architecture**: 10ms CPU per unit per turn on Graviton3, no sockets/subprocesses → mandatory pure-Python export path. Measured margins: 0.56ms (small net), then post-redesign 2.172ms worst case (Builder), both validated by full matches under `--tle 10` with zero violations. The "we can easily 5x the size" budget reasoning is anchored to these numbers.
3. **Engine facts with permanent value** (verified against docs/API, not guessed): per-unit sub-interpreters break torch/numpy re-import; `ct.fire()` never targets own tile and only damages buildings; conveyors face cardinals only, turrets 8-way; Sentinel facing is permanent; `rotate()` is Gunner-only.
4. **HPC/LSF gotchas** (each cost a training run): `bsub` doesn't propagate env without `-env "all"`; `span[hosts=1]` at 50 cores never scheduled in 2.5h on a congested queue (32 fits standard nodes); GPU queue was pure waste for CPU-bound self-play; sequential match collection left efficiency at 18.4% — and even after parallelization only **23.31%** on 32 cores, an unsolved bottleneck.
5. **The RL bot never won a single game**: 0/384 (pre-redesign), 0/544 (early post-redesign), **0/17,792** (final). The failure sharpened from "economy collapse" to a precise symptom: ~230 spawns per match, Builder Bots dead within ~a round, only 2 builder decisions logged in a 921-round game — the builder policy effectively never gets to act, so nothing downstream can learn.

**Loose ends at session close (2026-07-29T19:28):**
- Root cause of instant Builder Bot deaths — unknown; the local repro run was interrupted by the user before it started.
- Suspicion that the +1/10 unit-count-delta reward reinforces a degenerate spawn/die loop — unexamined.
- 23.31% CPU efficiency on 32 cores — suspected inference-server serialization, not investigated.
- wandb API key sits verbatim in chat history; rotation advised, never confirmed.
- Launcher remains NOOP-only (`ct.launch()` never wired); mirror self-play (`--opponent self`) built but never exercised; opponent diversity risk (all training vs one fixed x/luc snapshot) flagged but unaddressed.
- HPC job 28976890 killed; no training job running at session end.
