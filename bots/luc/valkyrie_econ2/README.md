# Valkyrie econ2

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

`valkyrie` with a fourth opening Builder: a second miner (RUSH roles 2 economy, 1 attacker, plus the
Launcher-ring Builder).

## Why

Ragnarok fixes the opening headcount at three and says why: every Builder Bot
adds +20% to every build cost the team will ever pay. But the comment argues
the cost, it does not report a measurement against a panel -- what *was*
measured is which of the three does which job, not how many there are. Pantheon
(#1 on the ladder) opens with four.

The two directions are split into two bots because they are different bets.
`econ2` buys delivered titanium, which is also the round-1000 tiebreak;
`atk2` buys a second Gunner battery at the enemy Core. Cost scaling taxes
both identically, so whichever wins says which side of the trade the +20% is
worth paying on.

Not measured locally beyond a smoke test -- the tournament is the instrument
for this, and 42-game local duels demonstrably cannot resolve differences this
size (they called a 25-game regression "noise").
