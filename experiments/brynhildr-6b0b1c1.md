# brynhildr@6b0b1c1

Hostile delivery-plug repair on top of `e9eccd8`.

The v122 replay series against Besvikomat (`e49b4afe-8607-466f-8fc3-f86242b966ff`)
exposed the same logistics exploit on all five maps. Besvikomat shot out the
first inbound conveyor and placed a Barrier on that remembered belt tile in
the following round. The ordinary repair routine recognized only an empty
missing conveyor, so the occupied hostile stump was never cleared or rebuilt.
Our five games collected only 10, 200, 1,630, 150, and 0 titanium while live
Harvesters continued feeding disconnected branches.

The Atlas losses in `2f3f63dc-3ef5-4b72-b2b0-65fcbf6e9bc4` repeated the same
destroy-and-Barrier sequence on the Core mouth. A home miner now treats a
hostile building on any remembered conveyor as a network break, prioritizes a
plugged Core mouth, digs it out, and then rebuilds the conveyor with its
remembered inward direction. It holds the repair job while waiting for enough
titanium instead of extending a disconnected branch.

A focused controller test verifies the two-stage sequence: hostile plug is
fired on first, then the empty mouth is rebuilt with its original facing.

Focused local gate over the seven replay-relevant maps, both seats, seeds 1-2,
and six older category leaders (168 games):

- records exactly matched `e9eccd8`, with zero errors and no outcome changes;
- the repair path changed eight game trajectories;
- six existing wins finished 8-32 rounds sooner;
- two existing losses survived 33 rounds longer.

Full local gate over 15 maps, both seats, seeds 1-5, and the same six category
leaders (900 games total):

- hildr78 135/150;
- steward 130/150;
- gefn 125/150;
- spar_wall 94/150;
- spar_sentinel 125/150;
- brokkr 122/150;
- 731/900 overall, exactly matching `e9eccd8`, zero errors and zero outcome
  regressions.

Sixty-nine games changed internal trajectories. All 20 affected spar_wall wins
finished sooner; the largest relevant gain was Jotunheim from round 762 to
503. No category lost a game.
