# hildr

The Sentinel rush (v70 `sentinel_rush_cluster` -> v72 `rush_econ_pivot`) with a Core that does the
race arithmetic instead of converting everything to ammunition on round 0.

## What the ladder replays of v70 showed

| opponent type | what they do | v70 result |
|---|---|---|
| pure rushers (Landers, Jacobs Code, Pantheon) | nobody mends; first ring up wins | coin flip on placement round |
| mending rushers (not adgato, Viktor5776) | 4-5 Builders at home the round our Builder is seen, ~2000 HP healed | 0-5, 0-5 |
| economies (TRRR, Troupe, Besvikomat) | 10-60 Builders, harvesters, 3000-5000 HP mended | timeouts lost on titanium collected |

## The numbers

* Budget: 500 - 30 (Builder) - 178 (ring) = **292 Ti of ammunition = 29 shots = 522 damage**, one
  Core. Anything else bought before the kill (a mender is 36-78 Ti plus 20% on every later build)
  leaves their Core standing at 14 HP. So while we are winning the race, nothing else is bought.
* Mending is 4 HP/Ti, shooting 1.8 HP/Ti. Four menders (16 HP/round) make a four-Sentinel ring need
  50 shots = 500 Ti, which no all-in rusher has. So when *their* ring will stand first, buy menders
  sized to their turrets (one per 9 dps, plus one) and win the long game on income.
* The call is made once, when their Builder first enters Core vision, from the two rings' ETAs
  (ours from the attack Builder's published walk; theirs from their Builder's distance, then from
  their observed placement rate). Re-deciding every round on turret counts flip-flopped: it bought
  one mender -- enough to lose the race, not enough to survive it.
* Both Cores dying in one round is settled on titanium **stored**; rushers store nothing, so 5 Ti
  are never converted. 1000 rounds is settled on titanium **collected** (harvester deliveries only),
  so a home Builder lays one Harvester and a belt *pointing at the Core* (v72's pointed away).
* Their mending is measured from the HP ledger (their Core's gain plus what our shots took), not
  assumed from the mender count -- four menders are 16 HP/round only while they have the titanium.
  Below 120 HP every point we have becomes ammunition; with menders making the kill unaffordable
  the ring holds, banks, and fires 40-ammo volleys at a mender on its ray.

## Placement

Four Sentinels now land 1-2 rounds apart on every pool map from both seats (v72 had gaps of 10-15):
no turret is built on a tile the route to the anchor runs through, and none that leaves the Builder
with no exit while builds remain (three turrets and a wall made a cell on midgard).

## The stall (added 2026-08-23)

A rush that parks their Core at ~110 HP behind menders used to bank passive income toward a
~500 Ti burst it would reach fifty rounds after round 1000.  The stall is now treated as what it
is -- an income race: once HOLD has accumulated 15 rounds and home is quiet, two home Builders
mine (three Harvesters, belts at the Core), titanium stays titanium as the burst bank, the
ammunition float stays one volley deep, and the ring grows past four from surplus.  Volleys
(20 ammo) hit Harvesters first, then menders on the ring, then any Builder on a ray; a stale
150+ bank is spent into the Core rather than hoarded.  brokkr (Jon's economy bot): 4/30 -> 24/30.

Discipline, from steward_hardened: replacements are damped after eight Builders, and two mender
deaths under a standing threat stop mender purchases outright -- a Builder bought into the fire
that killed the last one is a donation.

## Local results, 15 pool maps x both seats

| opponent | hildr | v70 for comparison |
|---|---|---|
| v70 | 25/30 | -- |
| v72 | 27/30 | 7/30 |
| v75 (rush_launcher_aware) | 27/30 | -- |
| steward_hardened_reinforced@f61245f | 21/30 | 19/30 |
| v72 + 4 reactive menders (not-adgato stand-in) | 28/30 | 28/30 |
| hildr | 15/30 | |

Many mirror wins are dead heats won on the stored-titanium tiebreak.

