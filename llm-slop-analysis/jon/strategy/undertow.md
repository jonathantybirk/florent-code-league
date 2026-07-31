# Undertow

`bots/jon/fair/undertow` is a fair, map-agnostic economy, defence, and siege
bot. It began as a response to Vanguard but is intended to be a contender in
its own right.

## Strategic identity

Undertow absorbs a committed Builder attack cheaply, continues expanding, and
then reverses pressure with a supplied siege. Its defining mechanic is the
**picket Launcher**.

The engine allows `ct.launch()` to move an enemy Builder. Once an invading
Builder enters a picket's adjacent radius, the Launcher throws it toward the
enemy Core. This costs no ammunition and can reset the same attacker over and
over. The Launcher is also a solid building and therefore interrupts Gunner
rays.

That replaces the earlier four-layer Barrier experiment. Deep static
fortification beat one opponent but obstructed the home economy and lost on
randomized terrain. Undertow retains only the cheap inner Core ring and builds
at most two pickets after a nearby enemy Builder has actually been observed.

## Opening and transition

The first four Builders have distinct jobs:

1. three Builders claim deposits and build the home economy;
2. one Builder remains near the Core as the repair and picket engineer;
3. none of the four becomes an early attacker;
4. once the bank exceeds 300 Ti, additional Builders become the counter-siege.

Only three Builders plan supply lines. Letting all four plan concurrently
produced overlapping routes and averaged roughly 35 Conveyors for fewer
Harvesters than Vanguard. The fourth Builder now performs no extraction
planning, so it is available when the attack arrives without corrupting the
economic build order.

The home economy permits lines up to twelve tiles but disables the previous
three-times-long rich-bank fallback. This avoids converting a large late bank
into sprawling, vulnerable Conveyor lines.

## Defence

The defence is layered by function rather than by wall depth:

- a one-tile building ring blocks point-blank Gunner rays;
- damaged nearby buildings and the Core are repaired;
- a detected enemy Builder triggers up to two picket Launchers on the outer
  approach;
- a picket always throws an enemy before servicing a friendly ferry request;
- opening Builders remain at home after extraction saturates;
- producers feeding a genuinely Core-threatening enemy turret may be
  destroyed to deny parasitic ammunition.

Picket positions are shared through two packed-position communication slots.
This distinguishes permanent defensive Launchers from one-shot siege ferries,
which still self-destruct when their queue is empty to remove their cost-scale
penalty.

## Offence

Undertow retains Vanguard's strongest general siege components:

- terrain-only symmetry inference from personally observed tiles;
- launcher-assisted travel;
- forward Harvesters near the enemy Core;
- parasitic Gunners beside enemy producers;
- short Conveyor creep when direct supply is unavailable;
- opposite-flank assignment across attackers;
- repair and economy recall under sustained home damage.

The counterattack begins at a 300-Ti reserve. A 400-Ti threshold won 19-11
against Vanguard; 300 Ti improved the same full test to 23-7 by converting the
post-defence bank into pressure sooner.

## Fairness

Undertow performs no runtime file, map, network, or process access. Match state
comes only from the controller API, map dimensions, team stores, and the
published symmetry guarantee. Predicted terrain is derived from observations;
buildings and units must be sensed normally.

## Results

Against the live Vanguard version that also repels enemies with its ferry
Launchers:

- official maps, both sides: **23-7**;
- representative generated maps, both sides: **39-21**;
- stress generated maps, both sides: **28-28**.

Across all fifteen official maps in both player orders against `strat1`, all
three Lucas challengers, unfair Lockin, and Starter, Undertow scored
**178-2 (98.9%)** with no errors. The two losses were one game against
`claude_challenger_1` and one against Lockin. The Vanguard counter therefore
did not come at the expense of the existing opponent field.

## External strategic influence

The design follows a recurring Battlecode lesson: pressure is strongest when
it forces an expensive response while expansion continues behind it. The
[2025 winner](https://battlecode.org/assets/files/postmortem-2025-just-woke-up.pdf)
described its hardest opponent as combining aggression with expansion, and the
[2021 winner](https://web.mit.edu/agrebe/www/battlecode/21/index.html) improved
defensive-map results by changing its build order to keep producing income.
Undertow applies that principle to this engine's local-ammunition logistics
rather than copying any Battlecode-specific unit logic.
