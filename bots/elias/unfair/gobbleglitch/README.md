# GobbleGlitch

Elias's second bot, built on AutistimusPrime. Tagged **unfair** for the same reason: it ships
`atlas.py`, a precomputed table of the 21 published maps, and fingerprints the live map against it.

Every change below was measured over 42 mirrored games (21 maps × both side assignments) against the
frozen AutistimusPrime as baseline. Things that measured worse were removed and documented in place.

## Results

Known = the 21 published maps × both sides, 42 games. Unseen = `maps/generated/`, 24 games.

| opponent | known: AP → GG | unseen: AP → GG |
|---|---|---|
| mistral | 34–8 → **39–3** | 8–16 → **12–12** |
| mistral_fast | 34–8 → 36–6 | 9–15 → 9–15 |
| jonbot | 33–9 → **34–8** | 18–6 → **21–3** |
| tempest_fast | 32–10 → **37–5** | 13–11 → 13–11 |
| vanguard | 32–10 → **37–5** | 12–12 → **19–5** |
| undertow | 31–11 → **35–7** | 15–9 → **21–3** |
| frontier / luc1 / lockin | 39–3 / 38–4 / 41–1 → **42–0** each | — |
| `a4sit` (squatter) | 32–10, **1** core kill → **37–5, 17 kills** | — |

Known **80.8% → ~88%**, unseen **52.1% → 66.0%**. `mistral`, the only rival that was beating us on
unseen maps, goes 8–16 → 12–12 there and 34–8 → 39–3 on known. The one regression is
`mistral_fast` on unseen, unchanged at 9–15.

## What changed

**1. Body-aware occupancy in the rush planner.** The load-bearing fix. `_run_rush` decided a firing
tile was taken with `_building_at` and never consulted `_bot_at` — and a Builder Bot is not a
building. A parked enemy body passed the occupancy check, the executor walked adjacent,
`can_build_gunner` refused, and the branch spent the round without ever touching `rush_stuck`.
Against `a4sit` — sixty lines that park six builders on ring tiles and never act again — the bot
built gunners in **1 of 42 games**, failing 1,136 times per game.

The previously withdrawn `BUILD_PATIENCE` timer failed because it could not tell a squatted tile
from an unfunded one and abandoned both. `BODY_PATIENCE` keys on the body directly, so an unfunded
tile never trips it.

**2. Sentinel third pass.** When both Gunner passes — strict and permissive — come back empty, plan
a Sentinel instead. A Sentinel's shot is stopped by **nothing**: verified in-engine on
`maps/lab/sentwall.map26`, where one behind a two-tile wall band killed a 500 HP Core at turn 84,
matching 500 ÷ 18 = 28 shots at cooldown 3 exactly. It is the only unjammable weapon in the game —
a Gunner is neutralised by a 3 Ti barrier in its lane, and a Sentinel has no lane to block.

Last, never first: 30 Ti and +20 pp against 10 and +10, and 2.78× worse per titanium of damage. It
must not pre-empt a permissive Gunner. Ordering this wrong cost 1 game each against vanguard and
undertow before it was corrected.

**3. Launcher retirement, with a bodyguard exemption.** The global cost scale is a **live census**,
not a cumulative ratchet — `scale% = 100 + Σ increments of every LIVING owned entity`, and removal
refunds in full and immediately (1224 measured checks across 153 scale values, zero mismatches). A
spent ferry Launcher is +10 pp on every later purchase; the audit measured 3.2–3.8 built per game
for 1.6–1.9 actual throws. Corridor Launchers retire after `RETIRE_IDLE`; ones near our own Core
never do.

**4. Opportunistic guard Launcher.** Built only when an enemy Builder Bot is actually near home and
we are already standing next to the site — never walked to. Sited at Chebyshev 2–4 from the Core,
because a ring-sited Launcher measured **zero throws in 43 rounds**: a Gunner bears on a Core from
3–5 tiles out, so rival crews never enter a ring-sited Launcher's r²≤2 pickup ring. Measured
neutral; kept because a throw is 0 Ti, 0 ammo and a measured +4 tiles of displacement.

## Measured and rejected

- **Fortify before heal.** The audit is damning — 1,127 alarm rounds produced 944 heals and 8
  barriers in 210 games, because during an alarm the Core is damaged by definition so the heal
  branch always returns first. The lab agreed: 201 rounds of Gunner fire against one builder
  rebuilding one barrier cost 1.01 Ti/round with the Core taking **zero** damage. It still measured
  worse — undertow 31–11 → **29–13** — because the lab put the barrier exactly in the lane, and here
  the threat-side sort is a guess at which of 12 ring tiles the ray actually uses. The transferable
  version is to read the enemy turret's facing (`get_direction` works on enemy turrets) and brick
  `pos + facing.delta()`; that is not what this branch does, and it is left alone until it is.
- **A walking guard Launcher.** Returning True while in transit hijacks the round from healing and
  the economy every round, for a Launcher that may never see anything enter its 8-tile ring.

**5. Farthest-first enemy-Core inference — the atlas dependency, fixed.**

AutistimusPrime's README claimed the atlas "only accelerates this; the same code runs on
unrecognised maps." Deleting `atlas.py` and re-running the known-map sweep showed otherwise —
about 12 games per 42, the same size as the 83%/69% known-vs-unseen gap. Ablating the seeds one at
a time located it exactly:

| seeded from the atlas | vs vanguard |
|---|---|
| nothing | 19–23 |
| the full static wall set | **19–23** — worth precisely nothing |
| the enemy Core anchor alone | **32–10, 31 kills** — full strength |

So the atlas was never a map memory that mattered. It was a correct answer to one guess: which of
the three symmetry candidates holds the enemy Core. Without it, that guess was made **closest
first**, on the reasoning that a wrong guess is discovered after the shortest detour — optimising
the price of being wrong rather than the odds of being right.

Measured over the published pool from both sides, closest-first names the true enemy Core on
**4 of 42 map-sides — 9.5%**. It cannot do better: the 180° rotation is by construction the
*farthest* of the three candidates, so closest-first can never pick it, and rotation is the truth
on 28 of those 42.

**Farthest first** scores 28/42 (66.7%) on the published pool and 14/48 (29.2%) on generated maps,
against closest-first's 8/48 — better on *both* map sets rather than tuned to one. The rationale is
map design, not this pool: a two-player map is built to be fair, so the Cores sit as far apart as
the symmetry allows.

Effect, with the atlas deleted entirely:

| opponent | closest-first | farthest-first |
|---|---|---|
| vanguard | 19–23 | **26–16** |
| tempest_fast | 20–22 | **30–12** |
| undertow | 22–20 | **24–18** |

and on unseen maps, where there is no atlas and the guess always runs, 57/120 → **62/120**.
Known-map results are unchanged, because with the atlas the guess never runs at all.

**6. Three attackers, and therefore no economy builder at all.**

`ATTACKERS` 2 → 3 against `BUILDERS = 3`. It reads wrong and measures right, because titanium was
never the binding constraint — an inert bot ends a match with 3000 unspent, and passive income alone
is 2.5 Ti/round against a Gunner's 2 Ti/round of ammunition. The audit had already established that
the entire win condition is one geometric event, a Gunner on the enemy ring, so **approaches are the
scarce resource, not titanium.** The cost is the ~2470 Ti a chain collects over a full match, and
`titanium_collected` only decides games that reach turn 1000 — which these do not.

Found by measurement, not by copying, but it converges on exactly what `mistral` does
(`ECONOMY_BUILDERS = 0`, `SCOUT_BUILDERS = 4`) — which is the answer to why it was beating us on
unseen maps.

## Tried, and rejected on the evidence

**Splitting the symmetry hypotheses across the two attackers.** `mistral` sends four opening scouts
to `unique[index % 3]` of the three symmetry candidates, so one is right by construction on every
map. Offline this looks decisive: covering the top two candidates rather than one raises the hit
rate from 29.2% to 83.3% on generated maps.

In game it changed **nothing** — 62/120 unseen with it and without, to the game. Instrumenting the
rusher at round 10 on three generated maps showed why: `alive` already held exactly **one**
candidate and the Core was already sighted, because `reject_by_tile` and `reject_by_footprint`
narrow the mask from observed terrain within the first few rounds. There is no ambiguity left to
split by the time a second opinion could pay for itself.

That also explains what farthest-first is really worth: not settling the question, but aiming the
first ten rounds of walking correctly while the question settles itself.

## Known weakness, stated plainly

The atlas still buys about 15 games per 126 on known maps, so this is still tagged **unfair**. But
the fair version is now genuinely competitive rather than crippled — 80–46 across vanguard,
tempest_fast and undertow with no map data at all — and is worth publishing as a separate fair
entry.

Unseen play is now positive overall (62/120) but `mistral` still wins the matchup 14–10. It is 767
lines with no map data, so its performance is identical in kind on both map sets; whatever it does
better is a real strategic difference, not an information advantage.

## Where the evidence lives

`llm-slop-analysis/elias/exploits/` — eight hunt reports plus `SYNTHESIS.md`, which reconciles them
and lists what was refuted. `HARNESS.md` explains why every probe must report through `ct.resign()`:
`print()` is swallowed entirely, which is how the first hunt lost ~59 probes' worth of findings.
Probes are in `bots/probes/`, lab arenas in `maps/lab/`.
