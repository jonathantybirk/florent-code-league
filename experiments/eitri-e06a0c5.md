# eitri@e06a0c5

Superseded before online testing by `eitri@a3dd609`, which adds confirmed
transit-jam clearing and improves four maps without regression.

Strict six-order planner successor to `eitri@4cb5cb5`. It adds the reverse
even/odd deposit interleave, which unlocks dense maps that none of the first
five deterministic orders route well.

Worst measured planning times are 8.9 ms on Archipelago and 8.8 ms on Saga.
Five repeated full Archipelago matches completed under the engine's 10 ms TLE;
Snowflake, Drumlin, and Glacierkeep also pass. A non-baseline plan now requires
a predicted gain above 300 Ti. The earlier 100-Ti threshold admitted a
modelled +260 Frostgate plan that actually lost 50 Ti; the stronger margin
removes that switch and every all-map regression.

Full 53-map do-nothing result versus original Eitri:

- total titanium: 1,640,390 versus 1,469,620 (+170,770);
- executor ratio: 95% versus 91%;
- planner ratio: 90% versus 85%;
- 33 maps improve and zero regress;
- Archipelago: 38,800 versus 24,490;
- Bifrost: 32,380 versus 22,420;
- focused/all-atlas 1-4-builder tests pass 15/15.

This supersedes all earlier Eitri queue entries. Online testing remains against
the current upper neighborhood led by Bean counters.
