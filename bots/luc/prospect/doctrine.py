"""Pick an opening from the map, using only what round 0 actually shows.

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

NAMES = {RUSH: "rush", FORTIFY: "fortify"}

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
    RUSH: (1, 1),
    FORTIFY: (1, 1),
}
# Gunners a Builder will put up away from home. Off under RUSH: answering a
# roaming enemy with a building trades a mobile Builder's turn plus a permanent
# +10% for a turret the enemy walks around. On a closed map it is the opposite
# trade, because there is a lane and the enemy has to come down it. This is the
# whole of the difference between the two doctrines.
_FIELD_GUNNERS = {RUSH: 0, FORTIFY: 2}


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
    # The Core is 2x2 and get_position reports its north-west cell, so the far
    # edges sit at width - 2 and height - 2.
    on_side = core.x <= CORNER_MARGIN or core.x >= width - 2 - CORNER_MARGIN
    on_end = core.y <= CORNER_MARGIN or core.y >= height - 2 - CORNER_MARGIN
    if on_side and on_end:
        return FORTIFY
    return RUSH


def economy_builders(doctrine: int) -> int:
    return _ROLES.get(doctrine, _ROLES[RUSH])[0]


def attack_builders(doctrine: int) -> int:
    return _ROLES.get(doctrine, _ROLES[RUSH])[1]


def max_field_gunners(doctrine: int) -> int:
    return _FIELD_GUNNERS.get(doctrine, _FIELD_GUNNERS[RUSH])
