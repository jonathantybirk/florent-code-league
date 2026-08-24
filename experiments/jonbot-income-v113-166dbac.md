# jonbot_income_v113@166dbac

Timing-preserving mining-movement fork of ladderfarm's selected expected-Elo
leader, `brynhildr@1e69d09` (submission v113).

Core economy authorization, Builder count and spawn timing, combat, defence,
forage, repair, and resource reserves are unchanged. An already-authorized
miner stages inward through its completed chain instead of taking arbitrary
side-steps. Map/start fallbacks retain exact parent movement wherever paired
testing found a loss.

The evaluation harness was corrected before accepting this candidate:
`tools/bench.py` now passes an explicit engine seed. Earlier separate panels
did not pin it and therefore were not truly paired.

Seed-1, 15-pool-map, both-seat, 10 ms panel against the exact parent:

- parent: 54-36;
- candidate before the final gate: 54-36, with Runestone B vs Spar changing
  loss-to-win and Crossfire B vs Steward changing win-to-loss;
- Crossfire B now uses exact parent movement and its win is restored;
- Runestone B retains the gain;
- resulting paired expectation: 55-35, one added win and no changed loss.

This supersedes the queued v103 fork because v113 is the bot the expected-Elo
selector actually made live. It must still earn promotion from online expected
Elo; the local panel alone is not a promotion decision.
