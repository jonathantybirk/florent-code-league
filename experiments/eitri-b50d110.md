# eitri@b50d110

Executor successor to `eitri@1dd4e6c`. Offline economy evidence only; this
change does not add, remove, or reorder any ladderfarm queue entry.

When a Builder's next route tile is occupied by a friendly Builder, it now
tries a shortest local detour around that one tile immediately. The detour is
accepted only when it costs at most one extra step; otherwise the established
three-round deadlock fallback remains. This avoids both arbitrary unit-ID
priority and the long loops observed with unbounded replanning.

Full 53-map engine sweeps against `bots/common/donothingbot`, seed 1:

- seat A: 1,715,770 Ti (+2,250);
- seat B: 1,713,610 Ti (+2,340);
- combined: 3,429,380 Ti (+4,590 over `1dd4e6c`, +55,590 over `cc2fa28`);
- executor: 96% of the corrected collision-free plan on both seats.

The evaluation was corrected in the same commit. `tools/openbench.py` now
writes a replay for each run, reads the actual Builder creation rounds, and
uses those as the ideal schedule's start times. A temporarily occupied reserved
spawn tile is therefore no longer misreported as executor waste.

Rejected alternatives are recorded by result: later-unit-yields regressed
String, earlier-unit-yields regressed the opposite seat, and unbounded detours
sent String A around long loops. The one-step bound removed the String
regression while retaining the aggregate gain.

`tests/test_eitri.py` passes for all atlas maps, both Core anchors, and builder
counts one through four. Both complete replay-producing sweeps finished without
TLE.
