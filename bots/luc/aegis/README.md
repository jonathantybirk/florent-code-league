# Aegis

`warden` — the highest raw win rate in the field — with the relay cap made
**conditional**, plus enemy-ray-aware Gunner seating.

## The problem this exists to fix

`warden_walk` capped the relay chain unconditionally. On the full ledger that
put it into the Nash support at 0.5, displacing ragnarok and ragnarok_fair —
but it also gave it the *lowest* mElo and *lowest* win rate of the top seven.
It became a specialist, not a stronger bot.

Per opponent, the blanket cap is two different effects added together:

| it gains | it loses |
|---|---|
| ragnarok_fair +14pp | vigil@60d5afa −24pp |
| valkyrie +12pp | vanguard_oracle −19pp |
| ragnarok +10pp | casemate_oracle −12pp |
| | prospect −10pp |

It wins against Launcher-heavy bots, which overspend on cost scale when we no
longer do — and loses against the bots that **wall us out**, where the chain is
not overspending at all but the only way through. It was trading 40/42
matchups for 21/42 ones, which is exactly the trade that buys Nash support and
sells mElo.

## The split

The two callers already tell the cases apart, so no new sensing is needed:

- `_opening_ferry` chains to cross open ground. This is what runs up the bill,
  and it is now capped at `MAX_ROUTINE_RELAY_LAUNCHERS = 1`.
- `_step` reaches for a Launcher only after `PATH_FAILURES_BEFORE_LAUNCHER`
  rounds of failing to path — the signal that something is genuinely blocking
  us. **Uncapped**, because that is the turtle case.

## Expectations, stated in advance

On the local 84-game gate against the two Nash-core agents this scores *worse*
than `warden_walk` (24% of maps 2-0 against 33%). That is the intended
direction: the gate only measures the two matchups the blanket cap was
specialising into, and is blind to the 40/42 games this is trying to keep. The
gate is the wrong instrument for this bot, which is the lesson the ledger
taught — so the cluster's mElo and nash_prob decide it, not the gate.

Timing: 0 turns over 10 ms.
