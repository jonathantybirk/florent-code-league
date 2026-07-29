## 1. Ground truth infrastructure (day 1–2)

- [ ] 1.1 Create `probes/registry.py` — claim dataclass (id, text, status, probe, platform, fcode version,
      date, dependents) and a generator that renders `docs/ground-truth.md`
- [ ] 1.2 Seed the register with every claim currently in circulation, ALL as `ASSERTED`: the eleven-plus
      runtime corrections (builder zero-damage, turret friendly fire, magazine-refill-at-zero, harvester
      blocks movement, fixed harvester output with round-robin splitting, sentinel 17-tile arc,
      spawn-next-round, global scale, rotate 10 Ti flat, sub-interpreter isolation, `main.py` entry point,
      13/15 ore-adjacent gunner spots, per-map symmetry table)
- [ ] 1.3 Set up WSL: `pip install fcode==2.2.0` on the manylinux wheel, confirm a match runs and
      `get_cpu_time_elapsed()` returns non-zero
- [ ] 1.4 Fix `docs/cli/cli-submitting.md` (`bot.py` → `main.py`) with a note citing the engine's
      `importlib.import_module('main')`

## 2. Priority-zero verifications (day 1–3, parallel with group 1)

- [ ] 2.1 **Builder damage on Linux** — the single highest-stakes open question; decides whether
      raiding/sabotage exists. Run the adjacency probe (vs enemy Core, Barrier, Conveyor, Harvester,
      Builder Bot) on WSL; record per-platform results
- [ ] 2.2 **Turret friend/foe** — friendly builder walked into a fed Gunner's ray; log target, team, HP
      trace. Also: friendly building in ray (jam), and own-Core-in-ray
- [ ] 2.3 **Magazine semantics** — ammo trace over 100+ rounds; does resupply arrive only at exactly 0;
      what happens to a stack arriving at a full turret
- [ ] 2.4 **Ore-adjacent gunner spots** — recompute for all 15 maps from `.map26` parsing: positions from
      which a Gunner can hit the enemy Core footprint with an ore tile orthogonally adjacent; publish the
      per-map table (this is the offence doctrine's load-bearing number)
- [ ] 2.5 **Harvester passability + output splitting** — `is_tile_passable` and real `move()` onto
      harvester/conveyor/splitter tiles (own and enemy); measure delivered Ti with 1 vs 2 vs dead-end
      adjacent outputs (quantifies both self-sabotage and the parasite-conveyor attack)
- [ ] 2.6 **Entry point + validator** — package a probe as `bot.py` (expect failure) and `main.py`; trigger
      each AST-validator rule locally and record exact messages
- [ ] 2.7 Re-run the sub-interpreter isolation probe on WSL (globals, class attributes, `sys.modules`
      mutation) to close it out as `VERIFIED-LINUX`

## 3. Evaluation harness (day 2–5)

- [ ] 3.1 `arena/worker.py` — one-shot subprocess: batch of `run_game` calls, JSONL to stdout,
      `os._exit(0)`; `arena/runner.py` — fan-out, hard timeouts, crashed-worker → recorded losses
- [ ] 3.2 Antisymmetric mirrored scorer + exhaustive 15×2 sweep; assert bit-identical repeat runs
      (determinism gate)
- [ ] 3.3 `--strict` mode: traceback scan per game, fail on any own-unit deletion; Linux `--tle 10` pass
- [ ] 3.4 Zoo v1: `idle`, repaired `starter` (fix `main.py:369` bounds bug in a copy under `bots/zoo/`),
      `greed`; wire teammate bots in as they become runnable
- [ ] 3.5 Held-out map designation (3 maps, stratified: one short, one wall-heavy, one large) and separate
      reporting

## 4. Offence doctrine probes (day 3–7)

- [ ] 4.1 Reproduce the turn-77 kill from scratch on Linux (do not reuse the prior agent's arena) — probe
      bot that walks one builder to a mapped firing spot, builds harvester + gunner, dumps magazine
- [ ] 4.2 Defender battery: (a) heal-bot, (b) fed home gunner covering the approach, (c) harvester-sniper;
      run rush vs each and vs all-three; record kill/no-kill and titanium exchange
- [ ] 4.3 Lane-jamming counter test: can a defender block the only firing lane with a cheap building, and
      what does the attacker pay to re-site
- [ ] 4.4 Per-map RUSH/ECON/HYBRID assignment from 2.4's table + 4.2's results; encode as atlas data, not
      runtime logic
- [ ] 4.5 Write the dogma-audit register with final arithmetic for all seven initial dogmas, updating
      verdicts with Linux results from group 2

## 5. Shippable skeleton (day 5–10)

- [ ] 5.1 `bot/main.py` skeleton honouring the runtime-safety spec: outer guard, per-branch guards,
      bounds/vision-checked `ct.*` wrappers, per-unit `random.Random`, action-before-planning ordering
- [ ] 5.2 Map atlas module: fingerprint → (enemy core, symmetry, ore list, opening); unknown-map fallback
- [ ] 5.3 Store protocol v1 (single-writer Core slots, max-register merges, spawn-ordinal role assignment)
- [ ] 5.4 Economy: BFS-routed harvester+chain construction with harvester sealing (exactly one output),
      chain-break detection, `destroy()` scale-management of dead infrastructure
- [ ] 5.5 Offence module implementing the doctrine behind the per-map switch; correct gunner policy
      (team check, magazine dump, rotate-over-rebuild)
- [ ] 5.6 Pre-submit gate: local AST-validator clone, BOM check, `main.py` packaging check, `--strict`
      sweep, Linux TLE pass — one command
- [ ] 5.7 First ladder submission through the full gate; verify entry-point behaviour and CPU headroom via
      `fcode match test` before activating

## 6. Team integration (ongoing)

- [ ] 6.1 Publish `docs/ground-truth.md` and the dogma audit to the team; walk each teammate's branch
      against the register and hand each a ranked fix list
- [ ] 6.2 Stand up the zoo leaderboard (all bots × all bots, exhaustive, nightly) as the team's shared
      arbiter
- [ ] 6.3 Migrate verified probes into CI so a future fcode version bump re-runs the falsification suite
      automatically
