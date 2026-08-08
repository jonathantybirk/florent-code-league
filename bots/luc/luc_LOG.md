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
