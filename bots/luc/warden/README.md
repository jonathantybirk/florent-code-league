# Warden

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

`valkyrie` with two mechanics ported back from `vigil@e267eeb`: mending a shot
conveyor line, and retiring a Builder that can no longer move.

## Why these two

**Correction to the original rationale.** This bot was built on the claim that
the ragnarok line loses to the vigil line. That claim came from a *partial*
cluster run (2/10 against `vigil@e267eeb`) and is false: on the completed
3,906-match run `valkyrie@d181312` takes 24/42 off `vigil@e267eeb`, 24/42 off
`vigil@18b749d` and 23/42 off `vigil@e22eda8`. Its one losing matchup is
`ragnarok_fair@79582fc` at 17/42.

The port still stands on its own merits, which never depended on the cycle:
ragnarok is simply missing two capabilities, and neither is a matter of taste.

Diffing the two lineages function-by-function, ragnarok is *missing* things
vigil still has. It was assembled as "the best measured mechanic from every
lineage" and two got dropped on the way:

| ported | vigil | ragnarok |
|---|---|---|
| `_repair_network` / `_broken_network_tiles` | yes | **absent** |
| `_write_off` (`self_destruct`) | yes | **absent — zero calls** |

- **Network repair.** A hole shot in the conveyor line means every Harvester
  upstream of the gap mines into a dead end. One 3 Ti tile restores the whole
  line's income. Ragnarok cannot mend a belt at all. This needed new
  bookkeeping: `p.conveyors` is rebuilt from vision each round and so cannot
  tell "destroyed" from "not looking", hence `p.network_plan`, a permanent
  record of what we laid.
- **Write-off.** A Builder walled in behind buildings holds +20% on every price
  the team pays for the rest of the game, and while it answers the heartbeat
  the Core will never replace it. Self-destructing refunds the scale and lets
  the Core respawn somewhere not trapped.

Belts and stuck builders are what *long* games turn on. That is no longer
offered as an explanation of a cycle that does not exist — it is just a gap: a
bot that cannot mend a shot conveyor loses the income of every Harvester
upstream of the hole, for the rest of the game, and a bot that never calls
`self_destruct` pays +20% on everything to keep a Builder that cannot move.

## Measured

Level with the control on the 21 official maps in both seats: 21/42 against
`ragnarok@79582fc` and 24/42 against `vigil@e267eeb`, identical to `valkyrie`.
That is expected rather than encouraging — those games have a median length of
48 rounds and belts are rarely shot in them. The cluster field, with its
harassers and its long games, is the test that matters.
