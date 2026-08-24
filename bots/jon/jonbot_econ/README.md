# jonbot_econ

Timing-preserving mining fork of ladderfarm's actual flagship,
`brynhildr@2f83111` (submission v109).

The Core's spawning, role selection, economy trigger, miner count, and defensive
priorities are unchanged. Miners stage on the completed inward belt—or the next
outward tile at the Core mouth—so cornered chains naturally alternate build and
move. They also vacate a planned build tile through the completed network instead
of taking the first arbitrary cardinal step.

Antler retains the parent staging. Replay analysis showed the generic staging
made its third Harvester one round earlier but stranded the repairer beyond an
exposed trunk, collapsing collection from 3,860 to 450 Ti. Both Antler starts
are excluded by terrain key; other maps retain adaptive routing.

Evidence at the server's 10 ms TLE:

- direct mirror against the prior flagship-based fork: 21-21;
- 93-33 against `spar_econ`, `brokkr`, and `steward` over 21 maps and both
  seats, versus 90-36 for the prior fork;
- the ungated staging result was 91-35 at seeds 1 and 2; its five sensitive
  cases repeated identically through seed 5, and the Antler gate retained all
  three gains at seed 6;
- the rejected static ore partition scored 90-36 on that panel and is not in
  this fork;
- the earlier round-zero mining fork scored 6-19 in its first five online
  ladderfarm series and is superseded.
- the mistakenly v116-based timing fork scored 3-22 in its first online round;
  v116 was a challenger, not the farm-selected flagship, and is superseded.

The helpers remain local to the generic mining executor. There are no opening
overrides or changes to when the flagship chooses economy.
