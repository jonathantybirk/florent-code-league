# jonbot_income_v103@2344f91

Superseded before online testing by `jonbot_income_v113@166dbac`, which applies
the same timing-preserving movement to the newer expected-Elo flagship.

Timing-preserving mining-movement fork of the actual live flagship,
`brynhildr@84d92d3` (submission v103).

This intentionally does **not** transplant Eitri's opening or alter any Core
decision. Economy authorization, Builder count and spawn rounds, combat,
defence, repair, and resource reservations are byte-identical to the parent.
Only an already-authorized miner's movement changes: it vacates completed build
tiles inward through the chain and stages nearer the next chain tile instead of
taking an arbitrary sidestep. Seven previously measured map/start regressions
retain exact parent movement through one data gate.

Local 15-pool-map, both-seat, 10 ms paired panel:

- Spar Econ: 17-13 versus parent 15-15;
- Brokkr: 10-20 versus parent 9-21;
- Steward: 14-16 for both;
- total: 41-49 versus 38-52 (+3 wins);
- direct parent mirror: 15-15.

This is the integration experiment requested after standalone Eitri v123 went
0-25 online against Bean counters, not adgato, Pantheon, Leviathan, and sporks.
It should be judged by expected Elo against live opponents. Do not replace v103
from the local panel alone.
