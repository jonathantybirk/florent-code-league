# eitri@4cb5cb5

Planner-search successor to `eitri@7bb92f2`. Executor lifecycle and contention
handling are unchanged.

The old greedy Steiner planner tried only nearest-first and farthest-first
deposit insertion. Those orders frequently boxed later lanes out of Core
access. The new shared `network.insertion_orders()` adds three cheap,
deterministic alternatives: even/odd interleaving and both coordinate sweeps.
`plan.py` and `tools/openbench.py` call the same generator, preventing evaluator
drift. A non-baseline order must predict at least 100 Ti more before it can
replace the original choice.

Ten explored orders would exceed the 10 ms unit budget on five large maps.
The selected five-order portfolio captures +113,120 theoretical Ti; worst
measured planning time was 7.9 ms. Archipelago, Saga, Snowflake, and Drumlin
also completed full 1,000-round engine matches at `--tle 10`.

Full 53-map do-nothing result versus original Eitri:

- total titanium: 1,625,170 versus 1,469,620 (+155,550);
- executor ratio: 95% versus 91%;
- planner ratio: 90% versus 85%;
- 35 maps improve and zero regress;
- focused/all-atlas 1-4-builder tests pass 15/15.

Largest planner-successor gains over `7bb92f2`: Auroraveil +10,010, Jackpot
+9,260, Drumlin +8,650, Eider +8,590, Paths +7,900, Snowflake +7,570,
Pinch +7,050, Aurora +6,650, Heart +6,440, and Meander +6,140.

This is still not called optimal: average planner yield remains 90% of the
capacity-aware upper bound, and online testing against the current upper
neighborhood remains required.
