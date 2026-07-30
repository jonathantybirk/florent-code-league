# Strategy and communication lessons for Florent Code League

Research pass: 31 July 2026.

This note synthesizes public organizer rules, tournament results, and participant
postmortems. Statements about a team's implementation are attributed to that
team or an organizer. Recommendations for Florent are explicitly labeled as
inferences.

## Lineage and relevance

Florent Code League publicly describes a collaboration with Cambridge
Battlecode. Cambridge Battlecode describes itself as inspired by MIT
Battlecode. Cambridge 2026 is therefore the closest public predecessor located:
it used Python and the same Titan mining setting, builders, harvesters,
conveyors, turrets, and destructible core. MIT Battlecode is the broader
competition tradition, but its game changes substantially each year.

Sources:

- https://league.florent.vc/
- https://battlecode.cam/
- https://docs.battlecode.cam/spec/overview
- https://battlecode.org/past.html

Florent is not identical to Cambridge 2026. Florent has one resource
(titanium), a 2x2 core, no axionite/refining system, a 1,000-round local match,
and a global 16-slot communication store. Cambridge 2026 had axionite and
refining, a 3x3 core, additional infrastructure such as bridges and foundries,
2,000-round games, and spatial markers as its only inter-unit communication.

## Cambridge 2026 finishers and published strategy

The Grand Finals bracket records Pantheon/Oxford first, something else second,
Kessoku Band third, and bwaaa fourth. The double-elimination bracket produced a
tied fifth/sixth tier rather than a unique fifth place; Muteki self-reported a
fifth/sixth finish.

Source: https://game.battlecode.cam/tournament/aa0f6250-8e90-47df-b15b-dae822f57afe

### Pantheon / Oxford — first

The organizer described Pantheon as developing terrain analysis adapted from
StarCraft AI research. Other competitors described it as Voronoi-like. No
Pantheon-authored technical paper or complete public postmortem was located, so
details beyond region/chokepoint-oriented terrain analysis are not verified.

Transferable inference: logistics and defense should reason about connected
regions, chokepoints, and critical infrastructure rather than only Euclidean
distance to the core.

### something else — second

The bracket verifies second place and Make Fire reports losing 5-0 to the team.
No detailed public technical account was located. It would be speculation to
classify the bot as primarily economic, aggressive, or defensive.

### Kessoku Band — third

Team-member accounts describe repeated testing, iteration, and rebuilding
around techniques that worked. No detailed public strategy or source artifact
was located.

### bwaaa — fourth

The bracket verifies fourth place, including a 7-2 win over Muteki. No detailed
public strategy account was located.

### Muteki — tied fifth/sixth

Muteki reported using Dijkstra and BFS, a Union-Find-inspired supply-chain
tracker, priority-ordered strategies, shared per-turn preprocessing, cached
expensive computations, and fast heuristics under an approximately 2 ms turn
budget.

Source:
https://www.linkedin.com/posts/emilvinu_cambridge-battlecode-was-awesome-about-a-activity-7474484240655720448-V8PN

Transferable inference: represent Florent logistics as a connectivity graph.
Track which harvesters and turrets are connected, which routes are blocked, and
which conveyor or splitter is a high-value articulation point.

## Detailed near-finalist evidence

Make Fire narrowly missed the Cambridge finals and published a detailed
postmortem. The team reported:

- Bug2 movement navigation;
- staggered coverage waypoints ordered in outward rings;
- retargeting newly seen, closer ore while preventing target cycles;
- cardinal BFS to decide whether a conveyor route was possible;
- incremental BFS spread over multiple rounds;
- explicit economy/generalist, defense, and attack roles;
- attacks on vulnerable harvesters, conveyors, and turret supply lines;
- timeouts for targets being continuously healed; and
- healing and defensive structures around valuable infrastructure.

The team concluded that a simple bot with few bugs was more valuable than an
ambitious but unreliable one.

Source: https://ismailfateen.me/blog/cambc_postmortem

## MIT Battlecode evidence

The 2025 winner, Just Woke Up, reported explicit unit state machines,
spawn-direction-based exploration, navigation that treated enemy tower range as
blocked terrain, automated A/B testing across maps, automated scrimmages, and
replay review.

Source: https://battlecode.org/assets/files/postmortem-2025-just-woke-up.pdf

The 2025 runner-up, confused, emphasized fundamentals, extensive replay
analysis, adapting effective opponent tactics, and prioritizing high-impact
features. Its deciding finals loss was partly attributed to center-biased
exploration missing valuable corner territory.

Source: https://battlecode.org/assets/files/postmortem-2025-confused.pdf

## High-level Florent strategy inference

### Early economy

1. Start with one builder; add another only when measured parallelism justifies
   its price and +20% scale contribution.
2. Give builders disjoint deterministic exploration regions.
3. Claim ore so builders do not duplicate work.
4. Score deposits by harvester cost, route cost, route risk, and time to first
   delivery.
5. Complete one working ore-to-core line before speculative expansion.
6. Maintain explicit connectivity state for every supply line.

### Harassment

Prioritize economic leverage rather than raw hit points:

1. exposed harvesters;
2. conveyors whose loss disconnects multiple producers;
3. turret-ammunition feeds;
4. splitters and other junctions; and
5. the core only when there is a credible kill opportunity.

Use time or titanium-spending limits so a builder abandons a target that is
being healed faster than it can be damaged.

### Defense

Defend critical junctions, single-route harvesters, the final core approach,
and turret supply lines. Use builders to heal and restore connectivity. A turret
without a functioning ammunition route is not a defense.

### Development process

Run every material change over all maps and multiple seeds, compare against a
fixed baseline, and inspect surprising wins and losses. Public postmortems
consistently present this empirical loop as more valuable than adding complex
features without measurement.

## Communication models

### Florent Code League

Florent gives each team a global blackboard of 16 non-negative integer slots.
Every allied unit can read or write any slot from anywhere. Writes are buffered:
a round reads one consistent snapshot and writes become visible in the next
round. Each unit still has a separate `Player` instance and private local state.

Local source: `docs/llm-slop-docs/api-reference/global-comms.md`

Consequences:

- Central planning is possible, but reports and assignments have at least a
  one-round latency.
- Sixteen slots are too small for a literal shared world model unless values
  are bit-packed.
- Multiple writers need an ownership or arbitration protocol to avoid
  overwriting one another.
- A core cannot optimally assign unseen ore: scouts must first report it.
- Unit-local state remains useful for paths and detailed task execution; the
  store should hold compact team-level facts.

### Cambridge Battlecode 2026

Cambridge used a more restrictive, spatial communication system. Every unit had
an isolated `Player` environment, and physical markers were the only allied
communication. A marker stored one unsigned 32-bit value, was free to place but
limited to one placement per unit per round, occupied a map tile, had 1 HP, and
could be overwritten or destroyed. A unit had to encounter/sense the marker to
read it.

Source: https://docs.battlecode.cam/spec/other-buildings

This strongly discouraged a perfect central controller. Teams needed local
state, distributed heuristics, physical report locations, and robust behavior
when information was delayed or unavailable.

### MIT Battlecode

MIT changes communication mechanics with the annual game:

- In 2024, all units could access a persistent global shared array of 64
  unsigned 16-bit integers from anywhere. Participant accounts used bit-packed
  sections and message queues for attacks, defense, map data, and squadron
  coordination.
- In 2023, teams also had a 64 by 16-bit shared array, but robots could write
  only near friendly headquarters, islands, or amplifiers. Gone Fishin' packed
  HQ locations, symmetry state, congestion, unit counts, wells, enemy reports,
  and island state into it.
- In 2025, communication was local and infrastructure-dependent: units sent
  messages between robots and towers only when connected by allied paint, and
  read messages from a recent-round buffer.

Sources:

- https://releases.battlecode.org/specs/battlecode24/3.0.5/specs.md.html
- https://battlecode.org/assets/files/postmortem-2023-gone-fishin.pdf
- https://releases.battlecode.org/specs/battlecode25/3.1.0/specs.pdf

The recurring design goal is distributed coordination under bounded bandwidth,
range, or computation—not unrestricted control of one global game object.

## Recommended Florent assignment protocol

Florent's 16 global slots are sufficient for centralized *task allocation* for
a small number of builders, even though they are insufficient for centralized
micromanagement.

A practical hybrid design is:

1. Give every builder a stable role/id when the core spawns it.
2. Give each active builder exclusive ownership of one status slot.
3. Pack phase, target coordinate, lease expiry, and a small status/version into
   that integer.
4. Reserve a few slots for core position, enemy core/threat reports, global
   strategy, and ore claims.
5. Let builders make local movement/path decisions.
6. Let the core reassign only at phase boundaries, on expired leases, or when a
   high-priority threat appears.

For one or two builders, this avoids the hardest concurrency problem entirely:
each builder writes only its own status slot, while the core publishes global
orders in core-owned slots. Builders may opportunistically claim newly seen ore
using leased claims; deterministic role priority resolves simultaneous claims
on the following round.

The key distinction is that the core should allocate objectives, not individual
steps. Optimal global matching can be approximated whenever new deposits are
reported, while builders retain enough autonomy to react immediately to local
obstacles and threats.
