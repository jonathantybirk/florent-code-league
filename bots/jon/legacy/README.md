# Legacy: bots and probes written for engine 2.2.0

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

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
