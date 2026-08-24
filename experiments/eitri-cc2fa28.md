# eitri@cc2fa28

Unfinished-deposit reservation successor to `eitri@7f9c590`.

A finished Builder could previously park on a planned ore tile because idle
clearing reserved unfinished conveyor construction and transit corridors but
not the Harvester target itself. On String, one Builder occupied `(8, 5)` from
round 30 onward while the assigned miner failed to build there from round 64
through round 999.

The deposit set is now part of unfinished construction geometry. The Harvester
builds successfully on round 64. Strict two-seat atlas comparison against
`7f9c590`:

- seat A: String +370 Ti; all other maps unchanged;
- seat B: every map unchanged;
- zero regressions across 106 map/seat cases;
- seat-A total: 1,687,570 Ti;
- combined gain versus `e06a0c5`: 114,720 Ti.

Focused tests pass 16/16. String, Archipelago, and Saga pass the 10 ms TLE from
both seats. This supersedes the earlier Eitri queue entry and still requires an
online verdict; standalone Eitri is an economy benchmark, not a promotion
candidate.
