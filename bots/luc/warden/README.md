# Warden

`valkyrie` with two mechanics ported back from `vigil@e267eeb`, chosen because
that bot is the one the ragnarok line loses to.

## Why these two

The rated field says the ragnarok line does not beat the vigil line:
`valkyrie@d181312` scores 90.3% over 3,038 cluster matches against 94
opponents, and nearly all its losses are vigil commits (2/10 to `vigil@e267eeb`,
4/10 to `vigil@e22eda8`, 17/42 to `ragnarok_fair`). The ratings already name
this: the Nash core is `{vigil@e267eeb 0.50, ragnarok 0.25, ragnarok_fair
0.25}`, a rock-paper-scissors.

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

Belts and stuck builders are what *long* games turn on, and long games are
where vigil beats ragnarok — so this is the most plausible mechanism for the
cycle that is available as a straight port rather than a redesign.

## Measured

Level with the control on the 21 official maps in both seats: 21/42 against
`ragnarok@79582fc` and 24/42 against `vigil@e267eeb`, identical to `valkyrie`.
That is expected rather than encouraging — those games have a median length of
48 rounds and belts are rarely shot in them. The cluster field, with its
harassers and its long games, is the test that matters.
