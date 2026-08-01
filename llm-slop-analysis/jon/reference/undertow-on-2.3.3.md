# Undertow on engine 2.3.3

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

The opening retains a fourth Builder as a home engineer. Economy Builders
construct reactive picket Launchers when an enemy Builder is actually observed
near home, so Undertow keeps its cheap positional counter to a Builder siege
without prepaying for static defence. Rich-reserve Builders provide the delayed
counterattack.

## Results

All pairings run both player orders, with no errors:

| corpus | Undertow | Vanguard |
|---|---:|---:|
| current 21-map pool, seed 1 | **27** | 15 |
| current 21-map pool, seeds 1-3 | **81** | 45 |
| representative generated maps | **44** | 16 |
| stress generated maps | **30** | 26 |

On the six-map screen the three-attacker-opening experiment also went 60-0
against `strat1`, all three Lucas Claude challengers, and `jonbot`; the retained
home engineer was selected by the Vanguard and generated-map comparisons. A
direct Duel match completed under the server's 10 ms turn limit and destroyed
Vanguard's Core on round 58.

## Fairness

The bot performs no runtime map, file, network, or process access. Terrain and
enemy state come from Controller observations. Its only prediction is the
published map-symmetry inference already used by both Undertow and Vanguard;
predicted firing positions are rejected until personally observed.
