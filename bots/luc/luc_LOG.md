# luc loop log

Self-paced improvement loop, started 2026-08-08. Goal: rank 1 on the live ladder.
Bots live in `bots/luc/`, branch `x/luc`.

## Iteration 1 — 2026-08-08 ~05:30

**State at start**: live rank 14 of 109 at 1756 (fcode status; live.json says 15 at 1748).
Flagship `steward_hardened_reinforced` (shr), active build `@c04e46e` (v28). Last 10: 4W 6L.

**Findings from the live feed**:

- `steward@e55aab5` (the older, simpler steward) carries the highest live Elo estimate we own:
  1876 [1814–1956] over 261 matches — vs 1731–1804 for every shr build. Its games ended
  2026-08-05, so the estimate is against an older opponent population. Someone already queued
  `steward@e55aab5:3` in the ladderfarm `test_next` (x/ladderfarm @6b8787e0e) — leaving that
  alone, will read the fresh results when they land.
- We lost 0–5 twice to **Besvikomat** (~1756, same rating as us) within minutes — rated with
  shr@f1f2bda, unrated with shr@366cd1b. Decoded three of the five games (match
  `3eab9d19-f399-4a53-8b7e-14b50edc0937`): Besvikomat plays economic attrition (12–16 Builders,
  7–10 Harvesters, few/no Launchers, first Gunner as late as round 147) and wins long games
  (191–1000 turns). Our side: Harvesters die and are **never rebuilt** (antler: zero Harvesters
  from round 150 of 320), Builders decay 3→1, and the Core grinds down once their mass arrives.
  The jackpot game went to the round-1000 titanium tiebreak — also lost on economy.

**Root cause (in code)**: shr's Core replaces Builders only when bank ≥ `REPLACEMENT_BANK_THRESHOLD`
(260). With all Harvesters dead there is no income, so the bank can never reach 260, and one
parked attacker keeps the Builder heartbeat warm — deadlock: no miners → no income → no trigger
→ no miners. The vidar lineage's income watchdog was lost in the steward line.

**Built**: `bots/luc/freyr` = shr + income watchdog in `core.py`:

- Core tracks bank growth; if no round in the last 30 saw the bank increase (from round 60 on),
  income is declared dead.
- Then: spawn a miner (post-opening spawns are forced miners via `LATE_BUILDERS_MINE`),
  bypassing heartbeat and bank threshold, cooldown 30 rounds, max 6 revives/game, requires known
  ore targets.
- While income is dead, ammo conversion holds back builder+harvester cost (the emergency
  `COMBAT_AMMO_FLOOR` override still wins).

**Local**: compiles, smoke game vs shr on a random 20×20: freyr won by Core kill at 116 (n=1,
noise). Full suite vs shr/vidar/odin on all maps running in background
(`freyr_run1`). Expect ~neutral locally — the watchdog only fires in long games against
economy-killers, which the internal panel mostly isn't. Gate is "no regression"; the real test
is the ladder vs Besvikomat-likes.

**Local numbers** (126 games, 21 official maps, both seats): freyr vs shr **21–21 (0.500)** —
exactly neutral against its parent, as predicted (the watchdog only fires when the economy
dies, which the internal panel rarely causes); vs vidar 27–15 (0.643); vs odin 28–14 (0.667).
Net-loss maps: vault 1–5, fjord 2–4 (parent's numbers there unknown — check before blaming the
watchdog). CPU: worst turn 3.5 ms, 0 turns over 10 ms across sweden/jackpot/vault; Core p99
57 µs. No clock reads. Gate passed → pushing.

**Next**: push freyr to x/luc → queue `freyr@<sha>:2` on x/ladderfarm. Also: check fresh
steward@e55aab5 ladder results — if it really measures ~70 Elo above shr live, understanding
*why* is the next hypothesis. Untouched idea bank: ferry economy Builders to distant ore
(Pantheon does it, flagged twice in notes); the lighthouse-style early-rush loss (core damage
from round 4) is a separate unaddressed failure mode.

## Iteration 2 — 2026-08-08 ~05:50

- Pushed freyr to x/luc as `c2c0d3d8b`; queued `freyr@c2c0d3d:2` (10 live matches) on
  x/ladderfarm (`801f7b5f9`), appended after the steward re-test entry.
- steward@e55aab5 re-test, first fresh round: 3–2, estimate 1876 → **1827 [1756–1907]** —
  regressing toward the shr range (1731–1804) as the stale-field theory predicts. Two rounds
  left; hold judgment.
- vault/fjord: freyr split 1–1 with shr on both, losses are to vidar/odin in games that end
  before round 150 — too short for the watchdog to arm. Inherited variance, not a watchdog
  regression.
- Watchdog false-positive check: 789-round jackpot win vs vidar, zero WATCHDOG fires — the
  bank kept growing, so a healthy economy never triggers it. True-positive test is the live
  field (needs an opponent that actually kills our economy).
- Waiting on: internal run with freyr; freyr's 10 unrated matches (~25 min).

## Iteration 3 — 2026-08-08 ~06:15

- **steward@e55aab5 verdict: stale-field artifact confirmed.** Fresh rounds went ~4–11;
  estimate 1876 → 1827 → **1715 [1650–1782]**. The flagship line stands. Lesson: a live Elo
  estimate built on matches older than ~2 days runs high; re-test before believing any old
  build's number.
- freyr live after round 1: 3–2, estimate 1748 on 5 games — meaningless until ≥25. Second
  round queued.
- **Internal ladder pipeline looks stuck**: index.json run_id `auto-b10e94bd7fe6` unchanged
  since 2026-08-06 16:36. Not mine to fix (harness owner's). Relying on the live ladder.
- **New failure mode dissected** (Besvikomat lighthouse loss, game 5): their opener throws a
  Builder by round-1 Launcher and plants a Gunner at (6,6) — three tiles from our Core — on
  round 3. That 25 HP turret chipped our Core for 186 rounds and ended the game **untouched at
  25/25 HP**. Why: `_defend_core` requires a *visible* target, the guard's own vision never
  covered (6,6) from its post, and the barrier/counter-turret/aligned-gunner answers all fell
  through to healing, 4 HP/round against 10. The docstring even documents the hole ("no
  inferred firing position").
- **Built `bots/luc/vali`** = freyr + shooter beacon: the Core (vision r²=36 — it always sees
  a Core-range shooter) packs the nearest visible enemy turret's position into the upper bits
  of SLOT_CORE_DAMAGED (alarm keeps the low 2 bits; all readers masked). When the guard has no
  visible enemy turret, it walks toward the beacon (standoff 2) until its own vision picks the
  target up, then the existing answers engage.
- Smoke: compiles, HUNT fires on showdown/sprint/duel vs vidar (3 of 4 wins). 168-game panel
  vs shr/freyr/vidar/odin running (`vali_run1`).
- **Panel results**: 20–22 shr, 20–22 freyr, 27–15 vidar, 28–14 odin — neutral at home like
  freyr, which is the expected profile for a live-only failure-mode fix. CPU 0 over 10 ms.
- Pushed vali as `d123262c6`; queued `vali@d123262:2` on x/ladderfarm (`bb0f348e9`), behind
  another agent's `steward_relent@7ed1acc:2`. freyr's second live round still pending (feed
  timestamps are UTC).
- Queue depth note: 4 test entries are now stacked on the farm (~11 min per round), so vali's
  first live round is ~30–45 min out.

## Iteration 4 — 2026-08-08 ~07:00

- Live so far: freyr 6–4 over 10 (est 1731 [1624–1834]); vali round 1 went 2–3 (est 1645, one
  round left); other agent's steward_relent 3–7. All below the 25-game bar — no conclusions.
- **Studied sporks (ladder #1, 2030 — above Pantheon).** Six games decoded (5–0 over Erebus,
  3–2 over Pantheon). Consistent shape: 9–21 Harvesters and 44–95 conveyors a game (nobody
  else breaks 6 Harvesters); Sentinels up by round 5–10 and Gunners nearly absent until a
  round-200+ kill wave (`first_gunner` 210/230/243 with `first_core_hit` one round later);
  eats 1000+ Core damage early and heals through it on economy. It is the 2.3.4 patch
  (Sentinel buff, Gunner nerf) played to its conclusion.
- Our own code already knows Sentinel siege is right (`SENTINEL_SIEGE_FIRST`), and its own
  measurement says the cap of one is a **delivery** ceiling: one attacker can't survive/stay
  solvent long enough to seat a second. sporks fixes delivery with bodies.
- **Built `bots/luc/ullr`** = vali + late attack wave: from round 170, with bank ≥ builder cost
  + 120, the Core buys up to 3 extra attacker Builders (announce-then-spawn through spare bits
  of SLOT_OWN_CORE — a window [start, start+count) so post-wave miners aren't misrouted; other
  spawn paths stand down during the one-round handshake). Each wave attacker seats its own
  siege Sentinel on its own line.
- Smoke: WAVE fires 3/3 on jackpot vs vidar and the Core kill lands at 621 vs freyr's 789 in
  the same matchup. 168-game panel vs shr/vali/vidar/odin running (`ullr_run1`).

## Iteration 5 — 2026-08-08 ~07:30

- **ullr verdict: neutral, not shipped to the farm.** 19–23 shr, 20–22 vali, long games 31–28,
  and a median of *zero* siege Sentinels seated in 64 long games (freyr/vali medians identical
  — the whole lineage almost never converts long games into siege). sporks' wave lands because
  4:1 mining has starved the defense it walks into; the wave without the economy is bodies
  into a working defense. Committed as a parts bin (`ullr`), no farm slot.
- Also learned: 27–45 builder spawns in some 1000-round games pre-exist across the lineage
  (replacement path has no total cap) — not a new bug, but a cost-scale anomaly worth a look
  someday.
- **Built `bots/luc/njord`** = vali + economy ceilings raised toward sporks' scale:
  NETWORK_CAP 4/8 → 6/12, ECON_EXPAND_ROUND 120 → 80, ECON_BUILDER_ROUND 200 → 120,
  ECON_MAX_TOTAL_BUILDERS 6 → 9. Smoke: beats vali on the jackpot tiebreak but only +40
  mined of ~4900 — the caps may not be the binding constraint. Panel running (`njord_run1`);
  the analysis to do on it is *harvesters built / titanium collected* vs vali, not just wins.
- Inherited, confirmed not-njord: the lineage mines 0 and loses deterministically as seat A on
  sweden vs shr (known symmetry-guess failure map).
- Live: freyr 6–4 (est 1732), vali still 5 games (2nd round pending), flagship shr@f1f2bda
  active, team 1751 rank 14.
- **njord panel: best of the day — positive against everything.** 23–19 shr, 24–18 vali,
  29–13 vidar, 29–13 odin, total 0.625 (vali was 0.565 on the same panel). First build today
  to beat its parent locally. Long-game harvester medians unchanged (2) — the gain likely
  comes from ECON_BUILDER_ROUND 120 buying income in mid-length games, not from the raised
  caps; worth decomposing later if njord's live numbers disappoint. CPU clean.
- Pushed njord as `0c51bc1dd`; queued `njord@0c51bc1:2` on the farm.
- Farm queue observation: vali's 2nd round still pending behind other entries; queue is now 5
  deep. Live results are the bottleneck — next builds should keep coming while they trickle.

## Iteration 6 — 2026-08-08 ~08:00

- Live: **rank 12 at 1771** — flagship on a 6-game rated win streak. Test builds at 10 games
  each: freyr 6–4 (1733), njord 4–6 (1668), vali 3–7 (1608). Samples too small to act on;
  note the farm's test panel is deliberately harder than rated draws, so these read low.
- **Dissected the sweden seat-A deterministic 0-mined loss.** Chain of three findings:
  1. My first theory (no ore knowledge) was wrong — builders know 16 ore tiles by round 25.
     Built a midpoint-ore-prior anyway (likely inert; kept, it's harmless and correct).
  2. **The real killer: the Core-damage alarm pins the sole miner as a mender.** Chip damage
     holds alarm=1 permanently; the miner healed 4 HP/round for 240 rounds with its Harvester
     finished but unbelted. Fix in `mimir`: alarm 1 no longer pins a miner with
     `network_load == 0` (zero connected Harvesters); alarm 2 (critical) still does.
     Result: sweden goes 317 → 653 rounds… 
  3. …but still 0 mined: the miner cycles claim → prelay → abandon → re-claim; route
     planning fails repeatedly on sweden's terrain. Deeper pathing project, deferred.
- `mimir` = njord + mend-pin exemption + midpoint prior. Panel vs shr/njord/vidar/odin
  running (`mimir_run1`).
- **mimir panel: 23–19 njord (beats its parent), 23–19 shr, 29–13 vidar/odin, total 0.619.**
  CPU clean. Pushed as `62df0ec39`, queued `mimir@62df0ec:2` (after another agent's
  `gefjon@f66a427:3` — the farm queue is now 7 entries).
- Lineage so far: shr → freyr (income watchdog) → vali (shooter beacon) → njord (economy
  ceilings) → mimir (mend-pin exemption). Each step locally ≥ its parent; njord and mimir
  are the two with real local edges.

## Iteration 8 — 2026-08-08 ~08:35

- Live: **mimir's first round 4–1** — best debut of my builds (5 games, no estimate yet).
  gefjon (other agent) 9–9 over 18. Team rank 12 at 1772.
- **Vault autopsy** (the map every build loses ~2–6): we out-mine vidar there but lose the
  turret war — vidar seats 4 Sentinels (range, fire through walls, never take a hit, 3960
  Core damage) vs our 0 (five Gunners, all dead by round ~70, 1449 damage).
  `SENTINEL_SIEGE_FIRST = True` turned out to be a label, not a behavior: the code only
  tries a Sentinel after the Gunner search fails, which on vault it never does.
- **Built `bots/luc/hodr`** = mimir + Sentinel genuinely first from round 60 (unconditional
  reorder died to vidar's rush at turn 89 — Gunner tempo still owns the opening), target
  1 → 2.
- **Bug caught the hard way**: forgot to import `SENTINEL_SIEGE_FIRST` into builder.py; the
  attacker crashed every round from round 3 and the engine swallowed it (`BUILDER_CRASH` in
  stderr). Two "identical deterministic losses" were the crash, not the strategy. The NOTES
  warning to grep fresh replays for crashes before trusting a run exists for a reason —
  re-learned. Post-fix: hodr kills mimir at turn 59 on duel; vault seats 1 Sentinel
  (damage 1449 → 1593), still lost there. Panel running (`hodr_run1`).

## Iteration 9 — 2026-08-08 ~09:00

- **hodr panel: best of the lineage.** 23–19 shr, 25–17 mimir (beats parent), 32–10 vidar
  (0.762 — the Sentinel bot beaten at its own game), 31–11 odin, total **0.661**. Net-loss
  maps down to vault alone (3–5). Avg 0.61 Sentinels/game seated — delivery is still shy of
  target 2, so there's headroom in the seat search if this direction keeps paying.
- Pushed hodr as `d540e5baf`, queued `hodr@d540e5b:2` (farm queue now 8 entries).
- **mimir live: 7–3 over 10, estimate 1840** — highest live estimate of anything we field
  (flagship ~1780–1800). Needs ≥25 games to qualify for auto-promotion; the farm's UCB
  should feed it more rounds on its own.
- Team rank 12 at 1772.

## Iteration 10 — 2026-08-08 ~09:15

- **mimir promoted to live flagship by the farm** (8–4, est 1844). hodr's test rounds: 6–4
  (est 1743, 10 games).
- Dissected the rated 0–5 to I Stone (1637): played by the *old* flagship shr@f1f2bda just
  before promotion. I Stone builds zero Gunners and one Sentinel at round ~37 — we
  out-damaged them in both decoded games and still lost, because one 2.3.4 Sentinel deals
  9/round and two menders heal 8. Healing through a Sentinel is losing arithmetic; it must
  be killed. shr couldn't see it (out of guard vision) — the beacon+hunt in vali+ closes
  exactly this, so mimir on the ladder should already answer it. Watch item, not a build.
- **Sentinel delivery autopsy** (hodr seats 0.61/game vs target 2): two blockers found —
  the ammo check ran *after* the throttle update, so a low pool burned the 10-round search
  slot; and between attempts the attacker built 25-ammo Gunners that kept the pool under
  the Sentinel's 40 forever. **Built `bots/luc/forseti`** = hodr + ammo-before-throttle +
  hold-Gunner-spend-while-saving (falls back to harass, which spends nothing).
- Panel running (`forseti_run1`).
- **forseti verdict: correct but inert.** Avg Sentinels seated unchanged (0.61/game), vault
  byte-identical, 23–19 vs hodr (noise), 0.649 total. The two unblocks weren't the binding
  constraint — ammo rarely sits under 40 in practice. Real limiter likely attacker lifetime
  vs the round-60 gate or the seen-terrain precondition. Committed for the record, no farm
  slot.
- mimir as flagship: beat team lazy (1864) 3–2, lost 2–3 to Erebus (1870) — competitive at
  top-6 level. Rated scheduler seems quiet since 07:04 UTC; watching.
- Pacing note: farm queue is long and mimir needs rated volume — shifting to longer
  observation windows, building only on live-evidence targets.
