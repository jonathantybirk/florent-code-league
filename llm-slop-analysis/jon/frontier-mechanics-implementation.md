# Frontier mechanics implementation

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

Date: 2026-08-02

This pass audited surprising engine behavior, isolated every proposed policy in its own bot, and
promoted only changes that survived an official-map panel. Every reported pairing uses all 21
official maps, both player orders, seed 1, and the server 10 ms limit.

## Implemented

- `undertow` and `undertow_oracle`: Builder clearing and harassment now attack an orthogonally
  adjacent tile under engine 2.3.3 instead of walking onto a target and attacking their own tile.
- `tempest_frontier`: Tempest Fast plus permissive Gunner fire and one reactive enemy-repelling
  Launcher. The Launcher is bought only after an enemy Builder comes within squared distance 36
  of the home Core; this avoids most premature defensive spending.
- `tempest_oracle_ferry` and `undertow_oracle`: record directly observed terrain and revoke atlas
  predictions at the first visible contradiction. This cannot make unseen-map identification
  information-theoretically perfect, but it prevents permanent phantom walls and ores.
- Preserved probes independently cover adjacent attacks, permissive fire, outer-range seating,
  wide and close pickets, Sentinel rushing, and guarded Oracle behavior.

## Isolated results

The common frontier panel was Undertow, Vanguard, and Mistral Fast, 126 games per challenger.

| policy | score | result |
|---|---:|---|
| Tempest Fast baseline | 68–58 | baseline |
| one reactive picket, wide trigger | **74–52** | useful but over-triggers against weaker bots |
| permissive Gunner fire | 69–57 | small gain |
| outer-range seat tiebreak | 67–59 | rejected; helps Undertow, hurts Vanguard |
| Sentinel rush | 4–122 | decisively rejected |
| Undertow adjacent-attack repair | 50–76 | identical to old Undertow on this panel; correctness fix |

The tighter combined `tempest_frontier` scored 204–90 against Tempest Fast, Undertow, Vanguard,
Mistral Fast, Jonbot, Starter, and Claude Challenger 1. It beat Tempest Fast 22–20. Excluding that
head-to-head, it improved the six shared external matchups from Tempest Fast's 180–72 to 182–70.
The gain is real but small.

Oracle contradiction rollback was neutral on the official pool: guarded and original Tempest
Oracle split 21–21 with identical aggregate behavior. It completed 60 games on the generated
representative variants without errors and split 31–29.

## Current mixed frontier

After the concurrent map-aware Vanguard Oracle commit, the current four-bot field produced:

| bot | record | rate |
|---|---:|---:|
| Tempest Oracle Ferry | **86–40** | **68.3%** |
| Tempest Frontier | 79–47 | 62.7% |
| Undertow Oracle | 51–75 | 40.5% |
| Vanguard Oracle | 36–90 | 28.6% |

Tempest Oracle Ferry beat every entrant individually. The fair Tempest Frontier also beat both
oracle descendants: Undertow Oracle 29–13 and Vanguard Oracle 35–7. There were zero unresolved
games or time-limit failures in the 252-game run.

## Interpretation

The useful imported mechanic is not “build Launchers.” It is “buy exactly one Launcher only when
an enemy walking attack is already close enough to be displaced.” The wide trigger gained against
the frontier but donated games to weaker opponents through unnecessary cost scaling; tightening
the trigger recovered part of that loss.

Permissive firing is cheap robustness, while outer-seat bias is matchup-specific and Sentinel
piercing does not overcome Sentinel economics. Undertow's stale attack logic deserved correction
despite producing no frontier-panel gain because the invalid action path remains exploitable by
infrastructure-heavy opponents.

No bot was submitted or activated.
