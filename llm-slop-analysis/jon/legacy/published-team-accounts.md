# Published Cambridge team accounts

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

Every technical statement below is attributed to the team that published it.

## Pantheon — Grand Finals winner

Organizer James Leung said Pantheon developed a terrain-analysis approach adapted from StarCraft AI research and was preparing a paper. No public Pantheon technical paper or full postmortem was located during this pass.

> **Superseded 2026-08-05.** The postmortem exists and has been read:
> [Pantheon_postmortem.pdf](https://game.battlecode.cam/postmortems/Pantheon_postmortem.pdf),
> digested in [../reference/pantheon-khaos-postmortem.md](../reference/pantheon-khaos-postmortem.md).
> The organizer's "terrain analysis adapted from StarCraft AI research" statement is confirmed and
> specific: Pantheon's bot *Khaos* runs a BWTA-style (Broodwar Terrain Analyzer) medial-axis
> chokepoint detector built on a sweep-line Voronoi over rasterised free-space boundary samples,
> vendored from the Foronoi Python library. Make Fire's claim that their own terrain work "did not
> use Voronoi analysis like Pantheon" is likewise confirmed.
> The postmortem refers to a public GitHub repository for the bot and tooling but gives no URL,
> and no such repo was located; treat the code as unavailable.

Source: [organizer summary](https://www.linkedin.com/posts/james-leung-dev_5864605-games-played-587-teams-1518-activity-7462172589520662528-SfO5)

## Kessoku Band — third in the Grand Finals

Team member Mikhail Borbe described six weeks of testing, iteration, and rebuilding around what worked. He lists first place in the international qualifiers and third place in the Grand Finals. No detailed technical artifact from the team was located during this pass.

Source: [Mikhail Borbe profile](https://www.linkedin.com/in/mikhail-borbe)

## Muteki — self-reported fifth/sixth in the Grand Finals

Team member Emil Vinu reported that Muteki placed fifth/sixth. He described the two-millisecond computation limit and said the bot used Dijkstra's algorithm, breadth-first search, and a custom Union-Find-inspired system for tracking supply chains. He also described a priority-ordered strategy list, structured preprocessing, cached expensive computations, and heuristics. His post says the bot was open-sourced, but an accessible repository link was not located during this pass.

Source: [Emil Vinu's account](https://www.linkedin.com/posts/emilvinu_cambridge-battlecode-was-awesome-about-a-activity-7474484240655720448-V8PN)

## Make Fire — one match win short of the finals

Make Fire's postmortem says the team was one match win from reaching the finals. The team reported:

- using Bug2 navigation throughout the competition;
- starting Sprint 1 with Explorer and Attacker roles, estimated enemy-core positions based on symmetry, and a “suicide meta”;
- briefly reaching ladder rank two after switching to direct aggressive attacks following a rules change;
- implementing bot behavior as enumerated states;
- using cardinal breadth-first search to choose between conveyors and bridges;
- assigning staggered or spiral-like exploration coverage points;
- defining `EVERYTHING_DOER`, `DEFENSE_FOCUSED`, and `ATTACK_FOCUSED` roles;
- retargeting closer ore while using a visited set to prevent cycles; and
- attacking vulnerable conveyors, harvesters, and supply lines feeding turrets.

The authors described their own bot as simple and reported that bugs affected it. They also wrote that their terrain work did not use Voronoi analysis “like Pantheon”; that statement is Make Fire's description of Pantheon, not a Pantheon-authored technical account.

Source: [Make Fire postmortem](https://ismailfateen.me/blog/cambc_postmortem)

## cheesynachos — top 12 in the international qualifier

The cheesynachos postmortem identifies the team as top 12 in the international qualifier; this is not a Grand Finals placement. The team reported:

- a parallel match runner, CSV output, an auto-scrim tool modified from Blue Dragon, team-by-map matrices, and profiling with `cProfile` and SnakeViz;
- navigation influenced by Bug navigation, followed by heuristic search and A*;
- an optimized A* using integer tile indices, cached position objects, local variables, and arrays, with measured execution reduced from more than two milliseconds to about 1,200 microseconds;
- direct conveyor saturation at four harvesters under the Cambridge rules;
- a straightforward route strategy that avoided merging into backed-up conveyor lines;
- an enclosure around harvesters that the team measured as a 50–70 Elo improvement;
- no large measured effect from its initial center-biased exploration, followed later by an expanding exploration radius defined as `0.02 * round + 20`;
- a healer pinned near the core, scored points of interest for attacks, and conservative deconstruction and replacement behavior.

Source: [cheesynachos postmortem (PDF)](https://game.battlecode.cam/postmortems/cheesynachos_postmortem.pdf)

## okbro — round of 16 in the international qualifier

Team member Vaishakh Vipin reported a peak ladder rank of seven with a 2597 rating and a round-of-16 international-qualifier result. He also reported records for a round-55 core destruction and a round-1998 core destruction, and described the bot as handling attack, defense, and resource management. His post said a postmortem was planned; no such artifact was located during this pass.

Source: [Vaishakh Vipin's account](https://www.linkedin.com/posts/vaishakh-vipin_just-spent-the-last-few-weeks-deep-in-cambridge-activity-7459144416440537088-uvnk)
