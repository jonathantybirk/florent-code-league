# jonbot_econ@4bedc58

Side-gated refinement of `jonbot_econ@19793f0` (submission v120), whose first
online ladderfarm round scored 13-2: 5-0 versus OpenSverige, 5-0 versus I Stone,
and 3-2 versus gsxWins.

The generic conveyor-chain staging remains unchanged. Only a single
terrain/start predicate falls back to the `brynhildr@2f83111` parent movement
on starts where staging reproducibly hurts the real-opponent panel: both Antler
starts, Quarry B, Skald B, String A, and Yulerune B. Core timing, economy
authorization, miner count, combat, and defensive priorities are unchanged.

All-map 10 ms evidence against Spar Econ, all 53 maps and both seats:

- `19793f0`: 72-34 versus the parent's 71-35 at the discovery seed, with four
  gains and three losses;
- `4bedc58`: 75-31 versus 71-35 at the holdout seed before gating String A;
- String A was 3-5 relative to the parent over seven seeds, so its final gate
  restores parent behavior without removing a gain;
- Crossfire A, Duel A, Helheim B, Quarry B, Skald B, Yulerune A, and Yulerune B
  each repeated their original result in all three replication seeds;
- Icefloe A retained a net +3 over four additional seeds and remains staged.

The earlier 21-map, three-opponent panel was 93-33 versus 90-36 for the parent.
The implementation remains one generic movement helper plus one start-key gate;
there are no scripted map openings.
