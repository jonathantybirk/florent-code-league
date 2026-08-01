# Legacy: bots and probes written for engine 2.2.0

Everything here was built against the pre-2.3.3 rules and is kept for the
record, not for play. Under 2.2.0 ammunition was **per-turret and physically
delivered**, Builders moved in all eight directions, and a Builder's attack hit
**its own tile**. All three are now false, so these bots mis-path, cannot cut a
belt, and build turrets that never fire.

- `vg_v1` .. `vg_v7` -- successive archived Vanguard builds, used as ancestors
  in the gauntlet. Each beats the one before it.
- `turtle`, `nemesis`, `reaver`, `baiter`, `riptide`, `ebb` -- counters written
  to beat a specific build. `reaver` and `baiter` both found real defects;
  `nemesis` is a recorded negative result.
- `probe_launch`, `probe_sentinel`, `probe_steal` -- single-purpose mechanic
  probes. Their findings are in `llm-slop-analysis/jon/legacy/`.
- `archive/` -- the earliest economy, siege, and frontier strategies, also
  written for the 2.2.0 rules. Post-2.3.3 snapshots live in `../versions/`.

The findings that still hold under 2.3.3 are the geometric ones: Barrier rings
block Gunner rays, Sentinels pierce buildings, and a Launcher can throw an
*enemy* Builder for no ammunition.
