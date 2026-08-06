## 1. Gating investigations — answers that change the design

Run before any behaviour is written. Each produces a number and a verdict in
`openspec/changes/resource-denial-bot/findings.md`.

- [ ] 1.1 **Healer vs grinder.** Probe a Sentinel with N friendly healers against M enemy grinders on
  a lab arena. Report the (N, M) ratio at which the turret survives indefinitely, and the Ti/round
  cost to each side. Decides whether forward turrets are holdable at all.
- [ ] 1.2 **Sentinel first-strike duel.** Two Sentinels in range of each other, built one round apart.
  Report which wins and whether entity-id order decides it. Decides whether arrival round is a win
  condition.
- [ ] 1.3 **Single-belt viability.** For each pool map, compute delivered Ti/round for one conveyor
  run from the largest cluster to a Core tile, against build cost plus cost-scale tax, plus flanking
  barriers. Report break-even round per map and the fraction of maps where it pays.
- [ ] 1.4 **Passability re-probe on 2.3.6.** Clean table for every terrain and building type, both
  teams. The previous probe's encoding is unreadable; this is load-bearing for all pathing.
- [ ] 1.5 **CPU budget.** Determine the real per-unit limit (docs say 10 ms, the visualiser's own
  threshold is 2 ms) via `BotOutput{execTimeUs,tled}` in a replay or a remote test. Every complexity
  decision scales with the answer.
- [ ] 1.6 **Store-slot budget.** Allocate all 16 slots on paper: role claims, cluster ownership,
  enemy Core, alarm, heartbeat. Confirm the one-round lag and team-wide sharing still hold on 2.3.6.
- [ ] 1.7 **Sabotage exchange rate.** Measure the cost to us of cutting a belt element against the
  cost to a repairing opponent. Establish the abandon condition.

## 2. Harness and diagnostics — built before behaviour

- [ ] 2.1 `tools/arena.py`: run a candidate against the Nash panel across pool and generated maps,
  both seats, reporting wins, delivered-titanium differential and per-map results.
- [ ] 2.2 `tools/diag/replay.py`: decode a replay into per-round, per-unit state.
- [ ] 2.3 Detector: idle rounds per worker per game.
- [ ] 2.4 Detector: oscillation (position and state) with worker id and round window.
- [ ] 2.5 Detector: route excess against shortest known path.
- [ ] 2.6 Detector: wasted actions (attempted action produced no state change), by action type.
- [ ] 2.7 Detector: unproductive state occupancy — rounds in a state that produced no progress.
- [ ] 2.8 `tools/watch.py`: generate replays against each panel bot and print the visualiser command.
- [ ] 2.9 Verify indicator overlays render, and measure their per-round cost.

## 3. Bot skeleton

- [ ] 3.1 `bots/cand/rdb/` package skeleton; passes `tools/check_bot.py`; plays a legal game doing
  nothing but spawning.
- [ ] 3.2 Store-slot allocation implemented per 1.6, with heartbeat-based role claims that free a
  role when its holder dies.
- [ ] 3.3 State enum, arbiter interface returning (state, reason), and per-state behaviour stubs.
- [ ] 3.4 Indicator overlay of state and objective, behind a flag.

## 4. Safe-action guards

- [ ] 4.1 Post-action occupancy simulation used by every build decision.
- [ ] 4.2 Enclosure guard: refuse a build that leaves the builder or an adjacent friendly with no
  legal move.
- [ ] 4.3 Delivery guard: refuse a build that severs our path from harvester to a Core tile.
- [ ] 4.4 Spawn-ring guard: price rather than ban, using passable buildings where a ring tile is
  needed.
- [ ] 4.5 Firing-line guard: refuse a build inside our own turrets' covered tiles.
- [ ] 4.6 Stall guard: abandon an objective after bounded consecutive non-progress and re-enter state
  selection.
- [ ] 4.7 Target-ownership check before any `fire`.

## 5. Map and resource model

- [ ] 5.1 Ore clustering from observed terrain.
- [ ] 5.2 Cluster valuation including delivery path and first-stack round.
- [ ] 5.3 OURS / THEIRS / CONTESTED classification by relative walk distance.
- [ ] 5.4 Choke-tile identification for each cluster.
- [ ] 5.5 Belt-viability decision using the 1.3 arithmetic.

## 6. Threat model and evasion

- [ ] 6.1 Enemy turret coverage from type, position and facing, with Sentinel piercing.
- [ ] 6.2 Coverage expiry when a remembered turret's tile is observed empty.
- [ ] 6.3 Route cost that prefers uncovered ground rather than forbidding covered ground.
- [ ] 6.4 `EVADE` behaviour, including the all-neighbours-covered case.
- [ ] 6.5 Threat-triggered state re-evaluation on sighting.

## 7. Behaviours

- [ ] 7.1 `SECURE_MID`: reach the highest-value contested cluster, with Launcher displacement gated
  on a measured round saving, and destroy the spent Launcher.
- [ ] 7.2 `BUILD_INFRA`: harvester plus belt to a Core tile, guarded by 4.3.
- [ ] 7.3 `MAINTAIN`: repair and heal our own infrastructure and turrets.
- [ ] 7.4 `DEFEND`: turret siting to cover our clusters and approaches, Sentinel-primary.
- [ ] 7.5 `SABOTAGE`: reach the enemy half, cut the element that zeroes the most upstream value,
  occupy the vacated tile, abandon per the 1.7 condition.
- [ ] 7.6 `JAIL`: contain an enemy worker where it is cheaper than killing it.
- [ ] 7.7 Ore denial: plug enemy-side ore seats, guarded by 4.3.
- [ ] 7.8 Ammo policy at the Core, sized from the actual turret mix.

## 8. Arbiter

- [ ] 8.1 Feature set the arbiter reads, each individually loggable.
- [ ] 8.2 Thresholded selection rule with hysteresis and minimum dwell.
- [ ] 8.3 Oscillation detection wired to diagnostics.
- [ ] 8.4 Per-state productivity report to justify each state's existence; delete states that never
  pay.

## 9. Evaluation and review loop

- [ ] 9.1 Baseline: candidate vs `bot/` control and vs each panel bot; record per-map results.
- [ ] 9.2 After each accepted change: re-run the panel, report win counts and titanium differential,
  and regenerate replays for visual review.
- [ ] 9.3 Report diagnostics counts alongside every result so behaviour regressions surface even when
  the score does not move.
- [ ] 9.4 Keep `findings.md` current — every finding with its number, sample size and probe.
