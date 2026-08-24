# eitri@7f9c590

Seat-specific offline-plan successor to `eitri@a3dd609`.

It keeps the confirmed transit-jam executor, then moves expensive order search
out of the match. Deterministic random search was run offline for each map and
Core anchor. Only orders whose actual 1,000-round do-nothing result improves
are stored in `orders.py`; maps without a proven order retain the six-order
runtime search. A stored map skips runtime alternatives, increasing TLE margin.

Strict full-atlas comparison against `eitri@e06a0c5`:

- seat A: 1,687,200 versus 1,640,390 (+46,810), zero regressions;
- seat B: 1,686,220 versus 1,618,680 (+67,540), zero regressions;
- combined gain: 114,350 Ti across 106 map/seat cases;
- seat-A executor ratio: 96%;
- seat-A planner ratio: 92%, up from 90%.

Notable seat-A actual gains from the stored plans include Icefloe +7,260,
Fimbulwinter +7,250, Nordkap +4,880, and Frostgate +3,870. Seat-B gains include
Bifrost +6,800, Fimbulwinter +5,770, Paths +5,440, and Jackpot +4,760.

The benchmark now accepts `--seat 0|1`, swaps the simulated bot side, reads the
matching titanium counter, and evaluates the exact stored/runtime plan. This
fixes the prior false seat-B audit and impossible executor ratios above 100%.

Focused tests pass 16/16 and now validate every atlas map, both Core anchors,
and every Builder count from one through four. Both-seat 10 ms TLE runs pass on
Archipelago, Bifrost, Eider, Fimbulwinter, Glacierkeep, Icefloe, Paths, Saga,
and Snowflake.

This supersedes every earlier Eitri queue entry. It has no online verdict yet;
test against the configured upper neighborhood and do not promote from local
economy results alone.
