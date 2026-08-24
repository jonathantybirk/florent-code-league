# eitri@a3dd609

Confirmed-transit-jam successor to `eitri@e06a0c5`.

The executor now reserves each Builder's planned paths to and between lanes.
A finished Builder does not move merely because it is on one of those paths:
it yields only after seeing the same friendly Builder beside it for three
consecutive rounds. Ordinary construction clearing retains the previous
neighbor choice. This distinguishes a permanent parked-unit obstruction from
passing traffic without speculative obstacle memory or map-specific rules.

Full 53-map do-nothing comparison against `e06a0c5`:

- total titanium: 1,652,190 versus 1,640,390 (+11,800);
- executor ratio: 96% versus 95%;
- planner ratio unchanged at 90%;
- Duel: 14,580 versus 12,160 (+2,420; 99% versus 83% execution);
- Crossfire: 21,470 versus 16,890 (+4,580; 98% versus 77% execution);
- Lighthouse: 28,910 versus 24,220 (+4,690; 98% versus 83% execution);
- Longship: 37,010 versus 36,900 (+110);
- four maps improve and zero regress.

Against original Eitri, 35 maps improve, zero regress, and total titanium is
up 182,570. Focused tests pass 16/16. Archipelago, Saga, Snowflake, Drumlin,
Glacierkeep, Duel, Crossfire, Lighthouse, and Longship each completed three
seeded 1,000-round runs under the engine's 10 ms TLE.

This supersedes `eitri@e06a0c5`. It has no online games yet: the earlier queued
hash was not present in the platform submission list when this successor was
queued. Test against the configured upper neighborhood; do not promote from
the do-nothing benchmark alone.
