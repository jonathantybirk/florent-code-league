# What the cost scale actually costs (engine 2.3.3)

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

Every building raises the *team-wide* price of everything: Builder +20%,
Gunner/Launcher +10%, Harvester +5%, Conveyor/Barrier +1%. Refunded when the
building dies. This turned out to be the single most valuable thing to reason
about this session -- four of the five wins below are just "stop buying things
that are not Gunners".

Scores are games out of 126: Vanguard against `mistral`, `tempest` and the
`v233_i` checkpoint, 42 games each. Baseline at the start was **51**.

| change | from | to | score |
|---|---|---|---|
| `ECONOMY_BUILDERS` | 3 | 2 | 51 -> 63 |
| `PICKET_LAUNCHERS` (defensive pickets) | 6 | 0 | 63 |
| `LAUNCH_HOPS` (ferry length) | 5 | 2 | 63 -> 69 |
| `HOME_LINE_MAX` (conveyor trunk) | 7 | 2 | 69 -> **78** |

`PICKET_LAUNCHERS` reads as flat above because it was measured against a
different opponent mix; on the pooled panel it was level (330 vs 330) and worth
+12 against the live bots, so it went in on those grounds plus the CPU saving.

## Curves, so nobody re-sweeps them

- `ECONOMY_BUILDERS` 0/1/2/3 -> 31/40/78/(51). Vanguard genuinely needs an
  economy; this is the *opposite* of Mistral, which wins on 0 and pure rush.
  A parameter that is right in one bot is not right in another.
- `HOME_LINE_MAX` 0/1/2/3/4/5/7/10 -> 46/58/**78**/75/74/73/70/69. Clean peak.
  Mine what is next to the Core; a long trunk is expensive, slow to repay and
  the enemy only has to stand on it.
- `LAUNCH_HOPS` 0/1/2/3/5 -> 54/67/**78**/65/63. Sharp peak. The ferry buys
  real tempo, the *long* ferry does not pay for its Launchers.
- `MAX_BUILDERS` 3/4/5 -> 56/**70**/50 (measured mid-session). Sharp peak at 4.
- `AMMO_TARGET` 20/40/80 -> 67/**78**/74. Already optimal.
- `MAX_HOME_HARVESTERS` 3/6/10 -> 77/78/78, `HOME_GUNNERS` 0/2/4 -> 77/78/78.
  Neither binds; left alone.
- `ECON_BEFORE_DEFENCE` 0/1/3 -> 52/53/**78**. Lowering the gate to get the
  barrier ring built earlier is a clear loss. Vanguard builds **zero** barriers
  in a typical match and that is correct.

## Sentinels are a trap

Gunner: 10 damage, cooldown 1, 2 ammo -> 10 dmg/round, **5 damage per titanium**
of ammunition, 10 Ti to build. Sentinel: 18 damage, cooldown 3, 10 ammo -> 6
dmg/round, **1.8 damage per titanium**, 30 Ti to build. Since 2.3.3 makes
ammunition cost titanium 1:1, the Sentinel is ~2.8x worse per titanium spent
*and* 3x the build cost. Its only edges are range 17 vs 3, piercing buildings,
and vision 32. No bot in this repo builds one; that is the right call unless a
map makes Gunner range unusable.

## Negative results worth not repeating

- **Seat pinning.** Seats are ordered by `reach`, measured from where the
  Builder stands, so it re-ranks every step and the Builder can oscillate --
  strait replays show the same four seats called "too far" from round 23 to 30
  while we sat on 98 Ti and a Gunner cost 22. Three fixes all lost: pin until
  resolved 74, pin with tolerance 1/3/6 -> 70/69/73, drop `reach` from the key
  59. Baseline 78. Walking past a better seat costs more than the wobble.
- **`reach` as the primary key** (ahead of line-of-fire quality): 73. A clear
  firing line is worth more than arriving sooner.
- **Reactive barrier ring** (wall the Core when the alarm fires, ignoring the
  econ gate): 69 vs 70. Dropped.
- **Healing the forward battery** (`_mend`): exactly neutral because it never
  runs. Instrumenting `_siege` shows attacker rounds go 8/34/65 to *walking*
  against 1/7/11 to building, with `_assist` reached 0/0/2 times a match. The
  siege is bottlenecked on travel, not on what it does after arriving.
- **Tempest's 5-Gunner battery cap**: byte-identical at 3, 5 and 99. Never
  binds in Vanguard.

## Where Vanguard still loses

It wins every long game and loses every short one: against Tempest it won at
r44/44/69 and lost at r31/36/37/40. The opening is the weakness, and the
opening is dominated by walking to the enemy Core.
