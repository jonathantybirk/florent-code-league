# Undertow on engine 2.3.3

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

The original Undertow was designed in the July 31 Codex thread
`019fb40b-1c7b-7601-b2ca-2d10c9e2974e`. Its picket-Launcher defence remained
useful, but its forward siege still implemented the engine 2.2 ammunition
model. On 2.3.3 it lost **5-37** to Vanguard across the current 21-map pool.

## Repair

The conversion keeps Undertow's strategic distinction and fixes four stale
mechanics:

- the Core holds 40 global ammunition rather than prepaying 120;
- Builders approach Conveyor targets from cardinal adjacency instead of
  walking onto the target tile;
- repair crews use the new cardinal-adjacency healing rule;
- attackers choose any personally observed tile with a firing line to the
  enemy Core, rather than building a forward Harvester and local feed network.

Three opening Builders establish the economy and remain available for repairs
and reactive picket Launchers. The fourth Builder attacks immediately. Unlike
Vanguard's five-hop rush, Undertow buys no offensive ferries: its attacker
walks while titanium and cost scale stay available for guns, replacement
Builders, and the home defence that directly repels Vanguard's rush.

Vanguard later added six permanent Launcher pickets of its own. That reversed
the matchup because Undertow's Builder selected the closest firing seat, walked
adjacent to the screen, and was thrown away. Undertow now prefers the outer
edge of Gunner range. It can establish ranged fire from observed terrain
without entering a Launcher's adjacent control radius, then shoot through the
static screen toward the Core.

## Results

All pairings run both player orders, with no errors:

| corpus | Undertow | Vanguard |
|---|---:|---:|
| current 21-map pool, seed 1 | **24** | 18 |
| current 21-map pool, seeds 1-3 | **72** | 54 |
| representative generated maps | **47** | 13 |
| stress generated maps | **30** | 26 |

On the six-map screen this version went 72-0 against `strat1`, all three Lucas
Claude challengers, `jonbot`, and `starter`. The current Vanguard result also
includes its five-hop ferry change, its rule for abandoning building targets
that defenders out-heal, and six permanent defensive Launcher pickets.

## Fairness

The bot performs no runtime map, file, network, or process access. Terrain and
enemy state come from Controller observations. Its only prediction is the
published map-symmetry inference already used by both Undertow and Vanguard;
predicted firing positions are rejected until personally observed.
