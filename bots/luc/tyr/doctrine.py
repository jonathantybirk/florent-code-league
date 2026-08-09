"""Pick an opening from the map, using only what round 0 actually shows.

Nothing here looks a map up. Every branch reads runtime state -- the
dimensions, this Core's own position, and the Core's vision disc -- so the
rules run identically on a pool map, a generated map, and a map nobody has
seen. The two thresholds below (CORNER_MARGIN, BLITZ_MAX_DISTANCE) were
*calibrated* against measurements on the published pool, the same way every
other constant in this bot was; that is parameter tuning, not map knowledge,
and the map names in the comments are the evidence for a threshold rather
than anything the code can read.


Measured over 138,785 tournament matches, the single largest map effect is
whether a rush pays at all: the same pair of bots (tempest family attacking,
vanguard/undertow family building) swings from 3.6% on bridge to 96.9% on
showdown. Grouping the 21 official maps by how bots' ratings move relative to
their own average splits them into two families that reproduce exactly on
independent halves of the match data, and one branch between those two
families recovers about two thirds of everything per-map specialisation could
ever buy. A second branch measured worse than the first, so there are two
doctrines here and there will not be a third.

What a fair bot can see at round 0 is the map dimensions, its own Core
position, and the Core's vision disc (r^2 = 36). Three rules were tried
against that, each a mechanism rather than a correlation, and together they
selected exactly the seven maps that behave as closed and none of the
fourteen that behave as open:

    walls near the spawn      terrain a defender can hold against a rush
    a cornered Core           two map edges of free protection
    a large, ore-rich map     the economy race is worth entering

Only the middle one survived being played. Against an identical twin pinned to
RUSH, over the closed maps in both seats, the wall-density rule lost crossfire
2-0 and the ore rule lost quarry 2-0, while the corner rule won bridge,
jackpot and sweden 2-0 each and split string and vase. So the shipped test is
the corner alone, at 8-2, and the other two are recorded here as measured
failures rather than left in. Crossfire deserves the footnote: it is the one
map in the pool with no measurable map effect at all -- strategy axes explain
2% of the rating spread there against 20-40% elsewhere -- so classifying it
either way was always going to be noise.

Both remaining doctrines run the same three Builders in the same three roles.
Reallocating them was the obvious lever and it is the wrong one: FORTIFY with
two economy Builders and no attacker lost 2-12 to plain RUSH on the same maps.
The cluster analysis says the vanguard family beats the tempest family on
closed ground, but vanguard is a differently built bot, not this one with its
attacker removed -- taking the attacker away yields a worse tempest, not a
vanguard. What did transfer is the cheaper half: where the enemy has to come
down a lane, a turret in that lane is worth building.
"""


RUSH = 0
FORTIFY = 1
BLITZ = 2

NAMES = {RUSH: "rush", FORTIFY: "fortify", BLITZ: "blitz"}

# Chebyshev Core-to-Core distance at or below which the whole team attacks and
# nobody mines. The measurement is on the 1,320-game h2h field run: a bot with
# no economy at all (`tempest_jon`, 0 harvesters in 138 games) scores 21/22 on
# showdown and 21/22 on sprint against a 12-bot field, where the strongest
# economy bot scores 12 and 17 -- and the same bot scores 6/22 on bridge and
# 6/22 on quarry. Economy is not a strategy that is generally good or bad; it
# is tempo spent, and on a map where the enemy Core is six tiles away the game
# is over before the first stack is delivered.
#
# The threshold is measured, not reasoned. Played over the 21 official maps
# against a six-bot panel in both orders, 252 games per setting:
#
#   off   197/252     showdown 6/12
#   6     201/252     showdown 10/12, sprint 9/12          <- shipped
#   8     195/252     ...and duel 3/12, against 9/12 at off
#
# So the gap in the pool's distances (6, 6, 8, then 9) was the wrong place to
# cut. Six tiles is a knife fight and economy is dead weight; eight is already
# far enough that the attacker arrives with nothing behind it and duel alone
# gives back more than showdown wins.
BLITZ_MAX_DISTANCE = 6

# A Core touching two perpendicular edges cannot be enveloped: the map itself
# guards two of the four approaches, which is the cheapest fortification there
# is. Selects bridge, jackpot, string, sweden and vase. The nearest open map is
# sprint, whose Core sits one tile off the corner, so a margin of 1 would start
# costing false positives immediately -- this is deliberately the strict test.
CORNER_MARGIN = 0

# (economy Builders, attacking Builders). Identical in both doctrines: see the
# module docstring for the 2-12 measurement that put them back. The table stays
# because it is the right place for a role change to live if a later one earns
# its way in, not because this one varies.
_ROLES = {
    RUSH: (1, 2),
    FORTIFY: (1, 2),
    # Nobody mines, but somebody guards and somebody mines: one of each.
    #
    # This was three attackers, no miner and -- through _LAUNCHER_BUILDERS
    # below -- no ring Builder either, on the reasoning that a Core six tiles
    # away is decided before economy or defence can matter.
    #
    # The ring Builder is this bot's mender. It is the Builder that stands on
    # the Core and heals it, which one-flag-off ablation prices at 11.0pp of
    # mean and 16.6pp of the worst matchup -- the single largest mechanic in the
    # build. BLITZ was the one doctrine that did not have it, on precisely the
    # maps where the enemy attacker arrives soonest. Measured on showdown and
    # sprint in both seats against five opponents: 0.350 with three attackers,
    # 0.600 adding the guard, 0.650 adding the miner as well, and the worst
    # matchup goes 0.000 -> 0.500.
    #
    # The miner matters for the reason Jon traced on the ladder: a blitz that is
    # answered has nothing behind it, and the opponent that survived simply
    # out-mines a bot holding zero Harvesters at round 120.
    BLITZ: (1, 1),
}
# Builders held back to ring our own Core with Launchers. The ring is a throw
# pad for the ferry and a displacement screen, and BLITZ maps are shorter than
# RELAY_STOP_DISTANCE, so on them the ferry never fires and the pad is a
# Builder and 20 Ti spent on nothing.
_LAUNCHER_BUILDERS = {RUSH: 1, FORTIFY: 1, BLITZ: 1}
# Gunners a Builder will put up away from home. Off under RUSH: answering a
# roaming enemy with a building trades a mobile Builder's turn plus a permanent
# +10% for a turret the enemy walks around. On a closed map it is the opposite
# trade, because there is a lane and the enemy has to come down it. This is the
# whole of the difference between the two doctrines.
_FIELD_GUNNERS = {RUSH: 0, FORTIFY: 2, BLITZ: 0}


def classify(ct) -> int:
    """Choose a doctrine from the Core's opening vision. Never raises."""
    try:
        return _classify(ct)
    except Exception as error:  # noqa: BLE001 - a bad read must not cost the game
        print(
            f"PLAN_FAILED id={ct.get_id()} round={ct.get_current_round()} "
            f"action=classify map reason={type(error).__name__}: {error}"
        )
        return RUSH


def _classify(ct) -> int:
    width, height = ct.get_map_width(), ct.get_map_height()
    core = ct.get_position()
    if core_distance(ct) <= BLITZ_MAX_DISTANCE:
        return BLITZ
    # The Core is 2x2 and get_position reports its north-west cell, so the far
    # edges sit at width - 2 and height - 2.
    on_side = core.x <= CORNER_MARGIN or core.x >= width - 2 - CORNER_MARGIN
    on_end = core.y <= CORNER_MARGIN or core.y >= height - 2 - CORNER_MARGIN
    if on_side and on_end:
        return FORTIFY
    return RUSH


def core_distance(ct) -> int:
    """Chebyshev distance to the enemy Core, over-estimated on purpose.

    A fair bot at round 0 knows only the dimensions and its own Core, which
    leave three candidates -- 180-degree rotation and the two reflections.
    Taking the *farthest* of them is both the best single guess (true on 28
    of 42 published map-sides, against 4 for nearest-first: a fair map places
    the Cores as far apart as its symmetry allows) and the safe error here,
    because reading a map as larger than it is only ever declines BLITZ.
    Measured against the pool it is exact on all three BLITZ maps and errs
    long on vase and string, which is the outcome we want.
    """
    width, height = ct.get_map_width(), ct.get_map_height()
    core = ct.get_position()
    candidates = ((width - 2 - core.x, height - 2 - core.y),
                  (width - 2 - core.x, core.y),
                  (core.x, height - 2 - core.y))
    return max(max(abs(x - core.x), abs(y - core.y))
               for x, y in candidates)


def economy_builders(doctrine: int) -> int:
    return _ROLES.get(doctrine, _ROLES[RUSH])[0]


def launcher_builder_index(doctrine: int) -> int:
    """Where the ring Builder sits, derived from the doctrine's own counts."""
    return economy_builders(doctrine) + attack_builders(doctrine)


def max_opening_builders(doctrine: int) -> int:
    return launcher_builder_index(doctrine) + launcher_builders(doctrine)


def launcher_builders(doctrine: int) -> int:
    return _LAUNCHER_BUILDERS.get(doctrine, _LAUNCHER_BUILDERS[RUSH])


def attack_builders(doctrine: int) -> int:
    return _ROLES.get(doctrine, _ROLES[RUSH])[1]


def max_field_gunners(doctrine: int) -> int:
    return _FIELD_GUNNERS.get(doctrine, _FIELD_GUNNERS[RUSH])
