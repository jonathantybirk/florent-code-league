# brynhildr@e9eccd8

Defensive spawn-role correction on top of the bounded wall-escape lifecycle in
`3c77244`.

The Core now marks a Builder explicitly when it spawned that Builder for a
home job. Spawned units first act on the following round, when the buffered
marker is visible. The new Builder therefore remains a mender/miner even if the
attack Builder has just died and no attack heartbeat exists. Sentinel commands
mask the marker and retain the original shoot/hold/volley semantics.

This was diagnosed from v118's Stavkirke loss to Besvikomat:

- an enemy Sentinel began firing on round 356;
- two home Builders healed 8 HP/round against its 9 average DPS;
- the Core paid for a third home Builder on round 692 at 122 HP;
- without a live attack heartbeat, that Builder selected the attack role on
  round 693 and walked from the Core ring to the enemy Core;
- the Core died on round 746 after receiving 3,060 HP of healing.

A focused controller test verifies that the home-spawn marker overrides a
missing attack heartbeat. The Core writes `SLOT_GO` once per round, and
Sentinels mask the low two command bits.

Full local gate over 15 maps, both seats, seeds 1-5, and six older category
leaders (900 games total):

- hildr78 135/150;
- steward 130/150;
- gefn 125/150;
- spar_wall 94/150;
- spar_sentinel 125/150;
- brokkr 122/150;
- 731/900 overall, exactly matching `3c77244`, zero errors and no changed
  outcomes.

Only six brokkr games changed internal timing or economy metrics; none changed
Builder counts, final Core HP, or result.
