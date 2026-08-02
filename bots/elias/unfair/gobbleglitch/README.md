# GobbleGlitch

Elias's second bot, built on AutistimusPrime. Tagged **unfair** for the same reason: it ships
`atlas.py`, a precomputed table of the 21 published maps, and fingerprints the live map against it.

Every change below was measured over 42 mirrored games (21 maps × both side assignments) against the
frozen AutistimusPrime as baseline. Things that measured worse were removed and documented in place.

## Results

Known = the 21 published maps, 42 games. Unseen = `maps/generated/`, 24 games.

| opponent | AutistimusPrime | GobbleGlitch | unseen (AP → GG) |
|---|---|---|---|
| frontier | 39–3 | **41–1** | — |
| mistral | 34–8 | 34–8 | 8–16 → **9–15** |
| mistral_fast | 34–8 | 34–8 | 9–15 → **10–14** |
| jonbot | 33–9 | **34–8** | — |
| tempest_fast | 32–10 | 32–10 | 13–11 → 13–11 |
| vanguard | 32–10 | 32–10 | 12–12 → 12–12 |
| undertow | 31–11 | 31–11 | 15–9 → 14–10 |
| `a4sit` (squatter) | 32–10, **1** core kill | **37–5, 17 core kills** | — |
| `a4fort3` (ring fort) | 28–14, 2 kills | 28–14, 3 kills | — |

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

## Known weakness, stated plainly

**The atlas is not an accelerator, and the generalisation gap is the atlas.** AutistimusPrime's
README claimed "the atlas only accelerates this; the same code runs on unrecognised maps." Measured
directly by deleting `atlas.py` and re-running the known-map sweep:

| opponent | with atlas | without |
|---|---|---|
| vanguard | 32–10 | **19–23** |
| tempest_fast | 32–10 | **20–22** |
| undertow | 31–11 | **22–20** |

About 12 games per 42. That is the same size as the 83% known / 69% unseen gap, and it explains it:
on an unseen map there is no atlas and we play like the right-hand column. The runtime siege planner
is not yet as good as the table it falls back from.

This is the single highest-value work item left, and it is worth more than any exploit in the hunt.
The published pool went 15 → 21 maps once already; if it moves again, the right-hand column is what
ships.

## Where the evidence lives

`llm-slop-analysis/elias/exploits/` — eight hunt reports plus `SYNTHESIS.md`, which reconciles them
and lists what was refuted. `HARNESS.md` explains why every probe must report through `ct.resign()`:
`print()` is swallowed entirely, which is how the first hunt lost ~59 probes' worth of findings.
Probes are in `bots/probes/`, lab arenas in `maps/lab/`.
