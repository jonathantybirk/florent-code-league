# Legacy analysis: engine 2.2.0

`vanguard-siege-and-sustain.md` documents the bot that won 99% of a 180-game
field under engine 2.2.0. Its central premise -- *damage = 5 x titanium
physically delivered into Gunners* -- was deleted by 2.3.3, which replaced
per-turret ammunition with a global pool the Core fills by conversion. Read it
for the method, not the conclusions.

What still holds:

- Barrier rings block Gunner rays; Sentinels pierce buildings and cover 17
  tiles to a Gunner's 3.
- `ct.launch()` does not check ownership -- a Launcher throws enemy Builders,
  and needs no ammunition, so this is the one weapon unaffected by the change.
- Healing is 4 HP for 1 Ti and is not touched by the cost scale.
- Matches are deterministic except against opponents that call `random`.
- Method notes: freeze ancestors and play yourself once the field saturates;
  build counters on purpose; a removal justified by measurement is only as good
  as the opponent that measured it.

What is dead: parasitism (Gunners beside enemy Harvesters), forward Harvesters
as feeders, conveyor taps, `_extend_feed`, and the whole logistics-race framing.

See `../reference/engine-2.3.3-changes.md` for the current rules.
