"""Shared constants and communication layout for Vanguard."""

from fcode import Direction, EntityType

D8 = tuple(d for d in Direction if d != Direction.CENTRE)
D4_DELTAS = ((0, -1), (1, 0), (0, 1), (-1, 0))
D8_DELTAS = ((0, -1), (1, -1), (1, 0), (1, 1),
             (0, 1), (-1, 1), (-1, 0), (-1, -1))
FACING = dict(zip(D4_DELTAS, (Direction.NORTH, Direction.EAST,
                              Direction.SOUTH, Direction.WEST)))
FACING8 = {
    (0, -1): Direction.NORTH, (1, -1): Direction.NORTHEAST,
    (1, 0): Direction.EAST, (1, 1): Direction.SOUTHEAST,
    (0, 1): Direction.SOUTH, (-1, 1): Direction.SOUTHWEST,
    (-1, 0): Direction.WEST, (-1, -1): Direction.NORTHWEST,
}
WALKABLE_BUILDINGS = (EntityType.CONVEYOR, EntityType.SPLITTER)

# 2.3.3 pays turrets from a global pool, so a Gunner needs only a firing line
# and titanium at home -- range is the whole constraint.
GUNNER_RANGE_SQ = 13
LAUNCH_RANGE_SQ = 26

# Three of the first four Builders stay home. The siege is supply-rich
# once a battery lands, so the marginal Builder is worth more mining and
# repairing than queueing for a firing position.
ECONOMY_BUILDERS = 2

SLOT_BUILDER_TICKET = 0
CLAIM_SLOTS = range(1, 6)        # home ore claims
SLOT_LAUNCH_ID = 6               # Builder id asking to be thrown
SLOT_ENEMY_CORE = 7
SLOT_SYMMETRY_A = 8              # rejected-symmetry mask, writer = ticket 0
SLOT_SYMMETRY_B = 9              # rejected-symmetry mask, writer = ticket 1
SLOT_ECON_LINES = 14
SLOT_HOME_UNDER_FIRE = 15


# Two. The ferry buys tempo -- a Launcher throw covers ground no walk can --
# but every Launcher is +10% on the team-wide cost scale and costs its rider
# two motionless rounds per hop. Five hops meant four to seven Launchers per
# match and a cost scale that priced us out of the Gunners that actually win.
# Two hops is worth +18 games over 126 against the strongest live opponents
# versus five, and +8 versus none: the ride matters, the price of the long
# ride does not pay.
LAUNCH_HOPS = 2
# Ferry all the way in. Stopping eight tiles out lost the arrival race:
# the strongest opponent had four Gunners against our Core by round 20
# while our attacker was still walking. 15-27 to 22-20 by lowering this.
LAUNCH_MIN_GAP = 3

# The Core spawns Builders onto its own ring, so it must finish the opening
# before we brick that ring up.
FORTIFY_ROUND = 5


# How far from our Core a damaged building is still worth a Builder's round.
# A belt cut beyond the repair crew's reach is severed for good, and a
# purpose-built raider (`probes/reaver`) exploited exactly that: it cut
# lines past the old radius of 4 and out-delivered us four to one.
REPAIR_RADIUS = 7

# Below this share of its hit points the Core outranks everything else.
CORE_PANIC_PERCENT = 55

# Core health below which the whole team switches to defending it.
HOME_ALARM_PERCENT = 85

# Bank above which the Core buys emergency repair crew without hesitation.
EMERGENCY_RESERVE = 120

# Bank above which standing still costs more than the cost scale does.
RICH_RESERVE = 400

# Bank above which a Builder may pay for a long home supply belt.
LONG_LINE_RESERVE = 250

# Rounds spent failing to reach a firing position before trying another.
BLOCKED_TILE_PATIENCE = 6

# Gunners posted over our own approach. Suppression, not defence: the enemy
# assault is Builders with no ranged attack.
HOME_GUNNERS = 2

# Their repair crew mends close to their Core, so a belt cut beyond this is
# severed for good.
RAID_MIN_GAP = 5

# Ammunition is a global pool the Core fills from titanium 1:1, once a turn.
AMMO_TARGET = 40
AMMO_FLOOR = 60

# Harvesters to secure before any Builder spends a round on the ring.
ECON_BEFORE_DEFENCE = 3

# Consecutive attacks with no net progress before a target is written off.
OUTHEALED_PATIENCE = 3

# Defensive Launchers beside our Harvesters (Make Fire ran six).
# Off. Six was Make Fire's number and it did measure better than zero back when
# ECONOMY_BUILDERS was 3 -- but at 2 the pickets became a straight loss, worth
# -12 games over 126 against the strongest live opponents and level on the
# regression panel. Replays say why: we were laying four to seven Launchers by
# round 10, each one +10% on the *team-wide* cost scale, while the bots that
# beat us spent every point of titanium on Gunners. The pickets never stopped
# the rush they were paying for.
PICKET_LAUNCHERS = 0
