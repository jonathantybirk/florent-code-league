## Context

Engine `fcode 2.3.6`. The 2.3.4 rebalance changed every turret number; all combat and cost-scale
conclusions in `llm-slop-analysis/elias/` predate it and are stale. Derived fresh from
`GameConstants` (see `tools/firstprinciples.py`):

| | Sentinel | Gunner | Builder attack |
|---|---|---|---|
| build | 30 Ti | 20 Ti | — |
| damage / round | **9.00** | 7.00 | 2.00 |
| Ti per damage | **0.556** | 0.571 | 1.000 |
| HP | **40** | 25 | 40 |
| reach (cardinal) | **5** | 3 | 1 |
| blocked by | **nothing** | walls, first building | — |
| cost scale | +20% | +20% (was +10%) | — |

Three consequences drive the whole design:

1. **A Core kill costs ~310 Ti against a 500 Ti opening bank and 3000 Ti lifetime income.** Titanium
   is not the scarce resource; time and survival are.
2. **Defence beats offence on exchange.** A 310 Ti, 56-round Sentinel investment is undone by 40 Ti
   and 20 rounds of one worker chewing it (40 HP ÷ 2 dmg × 2 Ti). But **healing beats chewing** —
   +4 HP for 1 Ti against 2 dmg for 2 Ti — so the atomic combat unit is a turret plus a healer.
3. **The tiebreak ladder is `titanium_collected → live harvesters → titanium_stored → coinflip`, and
   passive income scores zero on the first rung.** A game that reaches round 1000 is decided by
   delivery, which is exactly the objective this bot optimises.

Ladder context: best-of-five series, maps drawn at random per game from the announced pool, and Elo
is fed the *fractional* series score — so margin matters, not just wins.

Evaluation panel is `bots/nash/{steward, vigil, heimdall, odin, prospect_rushonly}`, the five entries
with non-zero Nash probability in the team's latest 3360-game run, treated as black boxes.

## Goals / Non-Goals

**Goals:**

- Win by out-delivering and starving the opponent, with Core destruction as an opportunistic bonus.
- Behaviour organised as a small closed set of worker states with one behaviour each, and a single
  inspectable arbiter choosing between them.
- Every self-harm avoided by a general precondition on the resulting state, never by a special case.
- Diagnostics strong enough that suboptimal behaviour is found by tooling rather than by eye.
- Beat the local Nash panel today.

**Non-Goals:**

- Reading panel-bot source to counter it. They are black boxes.
- A neural state selector in the first iteration. Thresholds first; learning only if the state set
  proves right and the thresholds prove to be the binding constraint.
- Reusing `bot/main.py`. It stays untouched as the control.
- Optimising for the published map pool specifically. Maps are drawn at random and the pool can
  change between rounds.

## Decisions

**D1 — Sentinel is the default turret; the Gunner is the exception.** It out-damages, out-ranges,
out-lives and cannot be blocked or jammed, at 0.556 Ti/damage against 0.571. The Gunner keeps two
niches: 10 Ti cheaper when the budget is genuinely tight, and it can rotate, which matters only when
the threat direction changes. *Alternative considered:* keep Gunner-primary for build speed —
rejected, because a Sentinel kills a Gunner in 2 shots from a tile the Gunner cannot reach.

**D2 — Denial over destruction.** Optimise `titanium_collected` and enemy-harvester count rather
than Core HP. *Alternative:* keep racing the Core — rejected, because that is exactly the single
geometric win condition that the current bot has and that one 20 Ti guard turret denies, and it is
why we lose 2–40 to a bot we otherwise match.

**D3 — Worker state machine with a separate arbiter.** States: `IDLE`, `SECURE_MID`, `SABOTAGE`,
`BUILD_INFRA`, `MAINTAIN`, `DEFEND`, `EVADE`, `JAIL`. The arbiter returns (state, reason); behaviours
never choose their own successor. This is what makes the diagnostics possible at all, and it is the
seam a learned selector would later slot into without touching behaviour code.

**D4 — Coordination through the 16 store slots, budgeted up front.** Slots have a one-round write
lag and are shared team-wide. Roles must be claimed in a way that survives the claimant's death —
the current bot's cumulative `spawned` counter is the cautionary case, where a killed rusher was
never replaced. Claims will be heartbeat-based, so a lapsed claim frees the role.

**D5 — Guards are property checks on the post-action state.** "Would this build leave me with no
legal move?", "would this cut my own delivery path?" — evaluated by simulating the placement, not by
remembering that a particular tile once went wrong. This is the user's explicit instruction and it is
also what generalises to maps we have not seen.

**D6 — Diagnostics are first-class and built early.** `ct.draw_indicator_line` / `draw_indicator_dot`
render into replays, so state and objective are visible in the visualiser. Offline replay analysis
counts idling, oscillation, route excess, wasted actions and unproductive states. Built before the
behaviours, so every behaviour is measurable from the day it exists.

**D7 — Launcher displacement to reach mid first, then destroy the Launcher.** A throw is 0 ammo and
a measured multi-tile displacement; the cost scale is a live census, so destroying the spent Launcher
refunds its +10%. *Alternative:* walk — rejected where the hop's round saving clears a measured
threshold, kept where it does not.

**D8 — Build general now, specialise last.** The organisers rotate half the pool weekly, three
times, ending on the 21st with four days before finalists are picked. Two consequences. First,
anything tuned to today's 15 maps is roughly half worthless in a week, so until the final rotation
every parameter must be justified by a map *property*, not a map. Second, four days is enough to
*run* a specialisation pass and nowhere near enough to *build* one — so the feature-to-parameter
fitting pipeline is built now and left idle, and the final rotation becomes an execution step.

The mechanism is a feature-conditioned policy: cheap features computed at runtime (map dimensions,
Core separation in walk-rounds, ore cluster count and dominance, chokepoint density, open-tile
fraction) map to parameters. This is simultaneously the general solution and the specialisation
route — closing in on optimal trends rather than hardcoding map names, which is also the only form
of specialisation that survives a rotation we cannot see in advance.

*Alternative considered:* ship a per-map table once the final pool is known — rejected. It was
already measured worthless on the previous pool (oracle variants scored 21–21 against their own fair
twins), it dies to any late engine or pool change, and it cannot be validated on held-out maps.

**D9 — Evaluate on margin, not just wins.** Ladder Elo consumes the fractional series score, so the
metric is games won out of games played across the panel plus delivered-titanium differential, and
regressions are read per map because the engine is deterministic and a sweep delta is always a
nameable set of flipped maps.

## Risks / Trade-offs

- **Denial may simply be slower than a rush on small maps** → measure early against the panel; keep
  an opportunistic Core-kill path that triggers only when projected to complete.
- **The state machine becomes a pile of special cases** → the arbiter is separate and every state
  must justify itself with diagnostics showing rounds spent productively in it; a state that never
  pays is deleted.
- **Store-slot budget is only 16 with a one-round lag** → allocate the budget in the design phase and
  treat it as a hard constraint, not something discovered late.
- **Sabotage loses the repair exchange** — a prior measurement had belt-sniping at 6.3:1 *against*
  the attacker versus an opponent that rebuilds → require the exchange to be checked, and abandon
  the target when it inverts.
- **Diagnostics cost CPU inside a 10 ms per-unit budget, and this machine cannot measure CPU**
  (`get_cpu_time_elapsed()` returns 0 on Windows) → keep overlays behind a flag and confirm timing on
  Linux or via remote test before submitting.
- **Over-fitting to five local bots** → the panel is the review surface; acceptance requires the gain
  to hold on maps and opponents not used while iterating.

## Migration Plan

New bot lives in `bots/cand/rdb/`. `bot/` is untouched and is the control in every sweep. Nothing is
published to `bots/elias/` until it beats both the control and the panel. Rollback is deleting the
candidate directory.

## Open Questions

1. Does the healer-beats-grinder duel hold in-engine on 2.3.6, and at what worker ratio does it
   invert? This decides whether forward turrets are holdable at all.
2. Is the Sentinel-versus-Sentinel duel decided by build order via entity-id turn priority? If yes,
   building first is a mechanical win condition and siting must optimise for arrival round.
3. Is a single long conveyor from the largest cluster, flanked by barriers, economically viable —
   delivered Ti/round against build cost plus cost-scale tax, at realistic map distances?
4. What is the real per-unit CPU budget — the docs say 10 ms, the bundled visualiser's own threshold
   is 2 ms. Every complexity decision scales with the answer.
5. Which of the pre-2.3.4 mechanic findings survived the rebalance? Turn order, live-census cost
   scale, no-occlusion vision and spawn-denial-needs-impassable have been re-confirmed on 2.3.5/2.3.6;
   passability needs a clean re-probe.
