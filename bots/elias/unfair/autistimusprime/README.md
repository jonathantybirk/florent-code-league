# AutistimusPrime

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

Elias's bot. Tagged **unfair** because it ships `atlas.py`, a precomputed table of the 21 published
competition maps, and fingerprints the live map against it. Per the repo README both categories are legal
but not comparable — benchmark this against other `unfair/` bots, or against `fair/` ones knowing the
handicap runs the other way.

Three files, pure stdlib, no map files read at runtime (the atlas is baked into the module).

## Results

Mirrored, both side assignments, `fcode 2.3.3`. Known = the 21 published maps (42 games/pairing).
Unseen = generated maps no bot has seen (`maps/generated/`).

| opponent | known | unseen |
|---|---|---|
| idle | 42–0 | 24–0 |
| lockin | 41–1 | 24–0 |
| frontier | 39–3 | 23–1 |
| starter | 39–3 | 24–0 |
| luc1 | 38–4 | 24–0 |
| mistral / mistral_fast | 34–8 | **8–16 / 9–15** |
| jonbot | 33–9 | 18–6 |
| tempest / tempest_fast | 32–10 | 13–11 |
| vanguard | 32–10 | 12–12 |
| tempest_frontier | 31–11 | 12–12 |
| undertow | 31–11 | 15–9 |
| tempest_ferry | 30–12 | 13–11 |
| **total** | **488–100** | **232–104** |

**Known weakness, stated plainly:** the known-map win rate (83%) does not survive on unseen maps (69%), and
it *loses* to `mistral` and `mistral_fast` there. The ladder draws from the published pool so the known
column is what scores, but the docs warn the pool may be updated between rounds — and it already went
15 → 21 maps once this week. If it moves again, `mistral` is the shape of bot that beats this.

## How it plays

- **Runtime siege.** Infers the enemy Core from map symmetry and ranks firing positions by
  `walk + 6×(range−1) + exposure`. No ore adjacency, no forward harvester, no supply chain — under 2.3.3
  ammo is a global pool filled by `convert_ammo` at the Core, so a Gunner needs only line of fire.
  The atlas only *accelerates* this; the same code runs on unrecognised maps.
- **Three opening builders.** The single global cost scale taxes every later purchase, so six builders cost
  270 Ti and leave scale at 220% (Gunner 22 Ti); three cost 108 Ti at 160% (Gunner 16 Ti).
- **Posture seams** for RUSH / DEFENCE / ECONOMY are present and currently identical, verified at exact
  parity over 1170 game pairs.

## Notes for whoever reads the source

Findings that cost real time to establish are in `llm-slop-analysis/elias/ground-truth.md` — 60+ engine
claims with the probe that established each, including eight documentation errors. Three that bite hardest:

1. **Harvesters block movement**, contradicting `game-rules-reference.md`. A harvester built in your own
   corridor walls off your own builders.
2. **Every turret API is team-blind.** `get_gunner_target` / `can_fire` / `fire` will happily target and
   destroy your own units. The shipped starter fires exclusively on its own team.
3. **Windows cannot measure CPU.** `get_cpu_time_elapsed()` returns 0 and `--tle` is never enforced there,
   so a local profile on Windows is meaningless. Use WSL or `fcode match test`.

Probes are in `bots/probes/`; the arena and both map-set harnesses are in `arena/` and `tools/`.
