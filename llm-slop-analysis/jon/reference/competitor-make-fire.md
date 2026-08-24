# Make Fire — what they published, and what transfers

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

Two of the names in the Discord (`IsmailFateen`, `3mara`) are Make Fire, and
the team published a full postmortem of **Cambridge Battlecode 2026**:
<https://ismailfateen.me/blog/cambc_postmortem>. Everything here is attributed
to them; none of it is our measurement.

## Caveat that matters more than the tactics

Their game is a **closely related but not identical ruleset**. The postmortem describes
a late-game "static axionite base" with **foundries**, and they build
**sentinels** as a routine offensive tool. Our engine has titanium only, no
foundry, and Sentinels measure badly for us (9-33 when retested on 2.3.3).

So the two engines are clearly relatives -- same cores, conveyors, harvesters,
launchers, gunners, sentinels, symmetry-based Core inference -- but the economy
differs. Read their tactics as *evidence about a related game*, not as rules
for ours. It is also a hint about where our engine could go next: if a second
resource and a foundry ever land, their late-game notes become directly
relevant.

## Their record and approach

One match win short of the Grand Finals; lost to `muteki` in both the winners
and losers brackets of the international qualifiers.

- **Bug2 pathfinding**, unchanged all competition, ported from a 2023
  Battlecode bot.
- **Roles as enumerated states**, ending on three types: `EVERYTHING_DOER`,
  `DEFENSE_FOCUSED`, `ATTACK_FOCUSED`.
- **Spiral waypoint exploration**, sorted by ring distance and angle from Core;
  only the first bot walks the waypoints so the economy does not follow itself.
- **Ore retargeting with a `visited_ores` set** -- they locked onto one deposit
  early and it cost them badly on labyrinth maps.
- **Six defensive Launchers** beside harvesters, throwing enemy bots away from
  the Core. We found the same mechanic independently.
- **Attacks on conveyors and harvesters**, including building Gunners in free
  cells adjacent to an enemy Harvester -- the parasitism we found under 2.2.0.
- `DEFENSE_FOCUSED` bots specifically hunt conveyors that feed enemy turrets.

## The one idea worth stealing

> abandon conveyors after 30 rounds if healed; maintain a `was_healed_before` set

They gave up on a target the enemy keeps repairing. That is the exact counter to
the defence we rely on -- healing is 4 HP a round against a Builder's 2 damage,
so an out-healed target can never fall and every round spent on it is wasted.
Our raiders have `BLOCKED_TILE_PATIENCE` for tiles they cannot *reach*, but
nothing for tiles they can reach and can never kill.

Worth noting in both directions: if they adopt it against us, our heal-based
defence stops soaking their attention for free.

## Their stated weakness is our strength

They describe their magic constants as "mostly arbitrary with very little
testing", and mention no automated testing framework -- a launcher-targeting bug
survived from Sprint 1 to April 13 and was found by public code review rather
than by a harness.

We sweep constants against a 42-game panel and fingerprint opponents for
mid-run contamination. That is the asymmetry to press.
