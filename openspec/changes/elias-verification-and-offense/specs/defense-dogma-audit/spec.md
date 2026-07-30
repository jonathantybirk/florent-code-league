## ADDED Requirements

### Requirement: Every inherited defensive belief is registered as a dogma under attack

Each defensive belief the team holds — from docs, the starter bot, or intuition — SHALL be registered with:
the dogma text, its origin, the arithmetic or probe that would refute it, and its current verdict
(`STANDS` | `REFUTED` | `CONDITIONAL`).

#### Scenario: Dogma enters through a teammate's code
- **WHEN** a teammate's branch encodes a defensive behaviour (e.g. gunners ringed at home, barrier walls,
  heal-tanking, a fixed builder count)
- **THEN** the behaviour is registered as a dogma and audited before it is merged into any shared bot, and
  the audit's verdict is communicated to the teammate with the arithmetic, not as an opinion

### Requirement: The initial dogma set is audited with arithmetic

The following SHALL each carry a written audit in the register. Initial verdicts from current evidence:

| Dogma | Verdict | One-line reason |
|---|---|---|
| Barriers protect the Core | `CONDITIONAL` | 10 HP/Ti is real armour, but 3 rounds per lane vs a Gunner, zero vs Sentinels, and it can block own spawn ring and own turret rays |
| Turtle and win the tiebreak | `REFUTED` | tiebreak counts delivered titanium only; turtling delivers zero |
| Heal-tank the attack | `REFUTED` | Gunner 0.20 Ti/dmg beats heal 0.25 Ti/HP and out-paces it 10 vs 4 per round. Confirmed on Linux that the only thing that can damage a unit is a turret (G13) |
| Belt chains are safe from builders | `REFUTED` | Range-0 sabotage exists (G14): an enemy builder stands *on* a walkable conveyor/splitter tile and fires its own tile — 2 dmg / 2 Ti, a 20 HP conveyor dies in 10 rounds. Chain-guarding is mandatory |
| Defensive gunners near the Core | `REFUTED` as implemented anywhere in the field | never fed by the starter; no friend/foe check; friendly buildings jam the ray |
| More builders = safer | `REFUTED` | +20 scale points each, forever; economy optimum sits near 3–4 builders; builders may deal zero damage |
| Must scout for the enemy Core | `REFUTED` | atlas + per-map symmetry answers it at round 0; blanket mirroring is wrong on 6/15 maps |
| 16 comm slots are the bottleneck | `REFUTED` | per-unit `self` persists 1000 rounds; vision is the real constraint |

#### Scenario: Audit updated on new evidence
- **WHEN** any probe result lands that bears on a dogma (e.g. Linux confirms or refutes builder damage)
- **THEN** the verdict is re-derived from the new arithmetic and the register updated in the same commit

### Requirement: Defence is designed from verified exchange rates only

Any defensive component we DO ship SHALL justify itself against the verified attacker cost table (Ti per
damage-per-round delivered to our base), not against intuition.

#### Scenario: Proposed defence is costed
- **WHEN** a defensive component is proposed (turret, barrier pattern, repair rotation, spawn-ring policy)
- **THEN** its titanium cost, scale-point cost, unit-cap cost, and CPU cost are stated alongside the attack
  it counters and the exchange rate, and it is rejected if the attacker pays less to neutralise it than we
  pay to field it

#### Scenario: Anti-rush minimum is defined empirically
- **WHEN** the offence-doctrine probes establish the cheapest rush that works
- **THEN** defence work is scoped to exactly that threat model — the cheapest defence that beats our own
  best rush — rather than to hypothetical threats
