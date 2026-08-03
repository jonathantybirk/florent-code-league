# Warden Walk

`warden` with the escape-Launcher relay chain capped at **one hop per Builder**
(`MAX_RELAY_LAUNCHERS = 1`).

## Where this came from

The cluster said something odd: `ragnarok_fair` beats `valkyrie` 25/42 while
`ragnarok` itself only draws 21/42. The fair twin is the *same bot* with the
offline atlas removed — and because `_opening_ferry` is gated on the atlas, the
fair twin cannot ferry at all. It is forced to walk.

Being forced to walk is what makes it stronger. On aurora:

| | Launchers | Harvesters | Gunners |
|---|---|---|---|
| valkyrie (chains freely) | 6 | 1 | 4 |
| ragnarok_fair (walks) | 3 | 2 | 7 |

Every relay hop is 20 Ti and a permanent +10% on every price the team pays, and
the bill lands on exactly the two things that kill a Core: turrets and
Harvesters. The chain buys tempo and pays for it in firepower and economy at
once.

## The cap is not monotonic

Measured over the 21 official maps in both seats against the two agents the
ratings put in the Nash core, as maps won 2-0 / games won:

| cap | vs ragnarok@79582fc | vs vigil@e267eeb | worst map rate |
|---|---|---|---|
| uncapped (`warden`) | 1 / 21 games | 7 / 24 games | 5% |
| 0 — never ferry | 3 / 16 | 3 / 20 | 14% |
| 2 | 5 / 25 | 5 / 23 | 24% |
| **1 — shipped** | **6 / 25** | **6 / 22** | **29%** |

So neither extreme is right. The first hop is worth 20 Ti — it clears the
Builder out of its own half while the map is still empty — and every hop after
it costs more than it buys. Zero is nearly as bad as unlimited, which is why
"the relay chain is good" and "the relay chain is bad" were both wrong.

1 and 2 are inside each other's noise on 42 games; 1 ships because it is better
on the map metric, and the cluster can settle it.

## The ring is the same bill

A ring Launcher is +10% on every subsequent price exactly like a relay hop, so
the eight-site compass ring is a scale cost as much as a screen. Capping it has
the same non-monotonic shape, measured the same way (maps won 2-0):

| ring cap | vs ragnarok@79582fc | vs vigil@e267eeb | worst map rate |
|---|---|---|---|
| 8 — all of it | 6 | 6 | 29% |
| 3 | 6 | 6 | 29% |
| **2 — shipped** | **7** | **7** | **33%** |
| 1 | 7 | 5 | 24% |

Two is the throw pad plus one more approach covered. Below that the screen
stops covering anything; above it the extra sites are bought with the Gunners
and Harvesters that would otherwise exist.

Together the two caps take the worst-target map rate from 5% to 33%.

## Inherited

Everything in `warden` (vigil's network repair and Builder write-off ported
back), `valkyrie` (ferry gate that survives off-pool, siege barriers), and
`ragnarok`.
