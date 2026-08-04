# pantheon_puppet

**Instrument, not a candidate. Never submit this.**

Plays Pantheon's own recorded actions for the first `HANDOVER_ROUND` rounds of a
real v20 game against our `tempest_fast`, then hands control to
`pantheon_replica_day3`. The point is to remove compounding: a Builder one tile
off on round 0 changes every landing and every walk after it, so a plain
side-by-side diff cannot tell "we decide differently here" from "we arrived
here in a different state". After a scripted prefix the board is exactly the
board Pantheon faced, so whatever the replica does next is a decision from an
identical position and any difference is a real difference in policy.

The replica's logic still runs on every scripted round, through a `Shadow`
controller that answers every query and silently drops every action. Ragnarok's
Builders accumulate most of their state in `_sense` on rounds they were alive --
builder index, doctrine, phase, route, remembered terrain, ore claims, build
counters -- so skipping those rounds would hand over to a bot that had never
looked at the board, and the experiment would measure that instead of policy.

## Validated

With the handover set past the end of the game the puppet reproduces the real
Pantheon game **30/30 rounds identically**. That is the instrument's calibration:
the script extraction is faithful, the engine is deterministic, our local
`tempest_fast` matches the server's submission, and entity ids line up.

## Usage

```
tools/pantheon_analysis/make_script.py <map>        # extract one game -> script_data.py
tools/pantheon_analysis/handover_test.py <map> <r>  # side-by-side from round r
tools/pantheon_analysis/handover_score.py <r> <n>   # per-action score, all maps
```

## Baseline, handover at round 8

**21% of Pantheon's individual actions reproduced** (123/598) over the eight
rounds after handover, one game per map:

| action type | reproduced |
|---|---|
| turret builds | 30% |
| walks | 22% |
| economy builds | 7% |
| launcher retirement | 0/3 |

Best maps fjord 52%, pinch 41%, twins 39%, duel 37%; worst sweden and string 0%.

On `duel` the raiders match almost move for move for four rounds after handover
-- same walks, same `gunn@(9,6)` on r8, same `gunn@(6,2)` on r9 -- while the
economy passengers diverge immediately. That is the opposite of what the win
rate suggested, and it says the attack policy is close and the economy policy is
not.
