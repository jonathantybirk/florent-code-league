# eitri@1dd4e6c

Scheduler successor to the deposit portfolio documented at `eitri@44745c2`.
This is an offline economy result only and is not submitted to either farm
queue.

The crew scheduler previously estimated travel between successive lanes with
Manhattan distance. That is exact on open ground but assigns work to the wrong
Builder around walls. The new scheduler uses BFS distance through known terrain
while avoiding deposits that will become Harvesters. Runtime execution, spawn
placement, builder count, and deposit plans are unchanged.

Two complete 53-map engine sweeps against `bots/common/donothingbot`, seed 1:

- seat A: 1,713,520 Ti (+1,180);
- seat B: 1,711,270 Ti (+1,660);
- combined: 3,424,790 Ti (+2,840 over `44745c2`, +51,000 over `cc2fa28`).

The change is deliberately global rather than a map-exclusion portfolio. It
has small per-map tradeoffs, but the largest corrected assignments improve
Jotunheim A by 1,340, Eider B by 1,360, and Saga B by 1,390. A half-detour
blend was also tested across the full atlas and rejected: it gained only 10 Ti
over the parent, versus 2,840 for exact distance.

`tests/test_eitri.py` passes, including every map, both anchors, and builder
counts one through four. Both engine sweeps completed without TLE.
