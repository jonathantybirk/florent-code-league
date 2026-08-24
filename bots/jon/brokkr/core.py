"""Core behaviour: spawn the workforce, publish what only the Core knows,
and decide when the team is under attack.

The Core is the one unit guaranteed to have been alive for the whole match and
to sit still, so two jobs belong to it and nowhere else: assigning Builder
spawn indices (it is the only unit that knows how many exist), and calling the
alarm. It calls the alarm on sighting rather than on damage: measured over the
map pool against a Sentinel rush, moving the trigger from "our HP dropped" to
"an enemy is near our Core" took the match from 5/30 to 15/30. See defence.py
for why the rounds of warning are worth that much.
"""

from fcode import EntityType, GameError

import debug
import defence
import roster
import siege
import store

# Titanium held back from spawning so a Builder that reaches its deposit can
# actually pay for the lane it walked to.
ECON_RESERVE = 45

# Under siege the Core spawns menders past the economic Builder target. What
# limits healing is Builder actions, not titanium: each Builder heals 4 HP a
# round for 1 Ti, so a Core on 28 HP sitting on 350 Ti -- traced on stavkirke
# -- was short of hands, not money. A mender born on the spawn ring is already
# adjacent to the Core and heals the round it appears. The reserve is what
# those hands then spend; spawning down to nothing buys menders who cannot
# afford to heal.
MEND_RESERVE = 70
# The engine's team cap is 50 units including the Core; staying well under it
# leaves room and keeps cost scaling survivable.
SIEGE_UNIT_CAP = 16

# Stop replacing menders once this many of our units have died. See
# `_needs_menders` for why losses rather than a spawn count.
MAX_MENDER_LOSSES = 6
NEAR_CORE = 3

# Once the alarm is up it stays up for this many rounds past the last damage.
# Flapping it would send menders home and back out again, which spends the
# walk twice and heals nothing.
ALARM_HOLD = 40

# Rounds of titanium history the income estimate averages over. Long enough
# that a Harvester's 10 Ti every 4 rounds is several samples, short enough to
# notice an economy being destroyed.
INCOME_WINDOW = 40


def run(player, ct) -> None:
    brain = player.brain
    brain.sense(ct)

    if brain.index is None:            # the Core's own bookkeeping
        brain.index = 0
        player.spawned = 0
        player.last_hp = ct.get_max_hp()
        player.last_damage = None
        player.last_threat = None
        player.prev_hp = ct.get_max_hp()
        player.prev_delta = 0
        player.prev_balance = ct.get_global_resources()
        player.income_gains = []

    _alarm(player, ct)
    _gossip(player, ct)
    _open_siege(player, ct)
    _ammo(player, ct)
    _spawn(player, ct)


# ----------------------------------------------------------------------
def _alarm(player, ct) -> None:
    """Publish how many Builders should come home, and hold it steady.

    The trigger is an enemy near the Core, not damage to it. By the time HP
    moves, a Sentinel ring is already built and firing at 36 a round, and a
    Builder ten tiles out arrives after 360 of that has landed. Sighting the
    enemy Builder that will place the ring buys those rounds back.
    """
    hp = ct.get_hp()
    if hp < player.last_hp:
        player.last_damage = ct.get_current_round()
    player.last_hp = hp

    round_number = ct.get_current_round()
    dps, builders, _turrets = defence.survey(player.brain)
    floor = defence.menders_wanted(dps, len(builders))
    delta = hp - player.prev_hp
    player.prev_hp = hp
    player.prev_delta = delta
    wanted = defence.adjust(store.alarm_level(ct), floor, delta) if (floor or delta < 0) else 0
    if wanted:
        player.last_threat = round_number

    # Hold the alarm past the last sighting. Flapping it walks menders home
    # and out again, which spends the journey twice and heals nothing.
    recent = (player.last_threat is not None
              and round_number - player.last_threat <= ALARM_HOLD)
    hurt = (player.last_damage is not None
            and round_number - player.last_damage <= ALARM_HOLD)
    debug.log(f"r{round_number} CORE hp={hp} d={delta} dps={dps} want={wanted} "
              f"eb={len(builders)} turrets={len(_turrets)} ti={ct.get_global_resources()}")
    if wanted:
        store.raise_alarm(ct, wanted)
    elif recent or hurt:
        store.raise_alarm(ct, max(1, store.alarm_level(ct)))
    elif store.alarm(ct):
        store.clear_alarm(ct)


def _gossip(player, ct) -> None:
    """The Core is the first and best scout: it sees radius 6 from round 0
    while a newborn Builder sees 4, so it owns the first entries on the ore
    bulletin. It uses the last slot, which no Builder index reaches until the
    roster passes seven."""
    brain = player.brain
    brain.sync_symmetry(ct, store)
    board = store.ore_board(ct)
    brain.learn_ore(board)
    spare = brain.unreported_ore(board)
    if spare is not None:
        store.publish_ore(ct, store.ORE_SLOTS - 1, spare)


def _ammo(player, ct) -> None:
    """Feed the Sentinel line, and nothing else.

    Ammunition is a one-way door -- converted titanium cannot buy a Harvester
    back -- so an economy converts nothing until it owns something that fires.
    The Core cannot see the siege line, which stands five tiles from the enemy
    base, so it reads the count off the store rather than off its own map.
    """
    if not siege.enemy_core_tiles(player.brain):
        return
    if store.siege_sentinels(ct) <= 0 and not _have_turrets(player.brain):
        return
    want = siege.ammo_wanted(ct.get_global_ammo(),
                             ct.get_global_resources(), ECON_RESERVE)
    if want >= 10 and ct.can_convert_ammo(want):
        _try(ct.convert_ammo, want)


def _open_siege(player, ct) -> None:
    """Declare the attack open once the economy can fund it.

    Writing 1 here is what turns the last economic Builders into attackers;
    they then count their own Sentinels up from it. The trigger is our
    Harvester count rather than the round, because what an attack needs is
    income to convert, not elapsed time.
    """
    if store.siege_sentinels(ct) > 0:
        return
    brain = player.brain
    income = _income(player, ct)
    store.note_economy(ct, store.siege_sentinels(ct), income)
    if siege.ready(brain, ct.get_global_resources(), income,
                   ct.get_current_round(), ct.get_sentinel_cost()):
        debug.log(f"r{ct.get_current_round()} CORE SIEGE-OPEN "
                  f"income={income:.1f} ti={ct.get_global_resources()} "
                  f"enemy={brain.imap.enemy_core()}")
        store.note_sentinel(ct, 1)


def _income(player, ct) -> float:
    """Titanium a round arriving, estimated from the team balance.

    Only rises are counted: spending shows up as a fall, and what is wanted
    here is what comes in. It is an estimate -- a build and a delivery in the
    same round net out -- and it is the honest one available, because the
    alternative is counting Harvesters the Core cannot see.
    """
    balance = ct.get_global_resources()
    gain = balance - player.prev_balance
    player.prev_balance = balance
    if gain > 0:
        player.income_gains.append(gain)
    else:
        player.income_gains.append(0)
    if len(player.income_gains) > INCOME_WINDOW:
        del player.income_gains[0]
    if len(player.income_gains) < INCOME_WINDOW:
        return 0.0
    return sum(player.income_gains) / len(player.income_gains)


def _spawn(player, ct) -> None:
    brain = player.brain
    target = roster.econ_target(brain.width, brain.height)
    cost = ct.get_builder_bot_cost()
    if player.spawned >= target:
        if not _needs_menders(player, ct, cost):
            return
        return _place(player, ct)
    # The first Builder is bought before the reserve applies: with no Builder
    # there is nothing to reserve titanium for.
    floor = 0 if player.spawned == 0 else ECON_RESERVE
    if ct.get_global_resources() < cost + floor:
        return
    _place(player, ct)


def _needs_menders(player, ct, cost) -> bool:
    """True when the siege wants another pair of hands and we can pay for it."""
    wanted = store.alarm_level(ct)
    # Living units, not lifetime spawns. Counting spawns meant a Builder that
    # died to harassment was never replaced: traced on midgard, the Core sat
    # on 1038 titanium losing 1 HP a round because it had reached its lifetime
    # cap and could not buy the two menders that would have turned the siege.
    if not wanted or ct.get_unit_count() >= SIEGE_UNIT_CAP:
        return False
    # Replace menders that die, but not forever. Against a long siege the
    # replacements hold the Core up -- capping on lifetime spawns instead left
    # 1038 titanium unspent on midgard while it bled a HP a round. Against a
    # Sentinel rush the same replacements walk into the ring and die, and
    # feeding it measured 25/30 where stopping measured 27/30. Losses are the
    # signal that separates the two, and the Core can count them: everything
    # it spawned that is no longer alive.
    if player.spawned + 1 - ct.get_unit_count() > MAX_MENDER_LOSSES:
        return False
    if ct.get_global_resources() < cost + MEND_RESERVE:
        return False
    return _menders_home(player.brain) < wanted


def _menders_home(brain) -> int:
    """Builders standing where they can actually heal.

    Counting everything near the Core counts the diagonal tiles too, and a
    Builder on one of those heals nothing -- so the count read as "enough
    menders" and suppressed the spawn that would have saved the Core.
    """
    spots = defence.heal_spots(brain)
    if not spots:
        return 0
    count = 0
    for key in spots:
        unit = brain.imap.unit_at(*key)
        if unit is not None and _STATES[unit].startswith("OUR_BUILDER_BOT"):
            count += 1
    return count


def _place(player, ct) -> None:
    for tile in ct.get_nearby_tiles(dist_sq=2):
        if ct.can_spawn(tile):
            if _try(ct.spawn_builder, tile):
                # Publish the 0-based index of the Builder just spawned, not
                # the new total. Its first run() is the round after the spawn,
                # so what it reads is this write -- post-incrementing here made
                # every index one too high and left index 0 matching nobody.
                store.note_spawn(ct, player.spawned)
                player.spawned += 1
            return


def _have_turrets(brain) -> bool:
    for key in brain.imap.tiles:
        building = brain.imap.building_at(*key)
        if building is not None and _STATES[building].startswith(
                ("OUR_GUNNER_", "OUR_SENTINEL_")):
            return True
    return False


def _try(action, *args) -> bool:
    try:
        action(*args)
        return True
    except GameError:
        return False


from utils.GCS.Base.protocol import TILE_STATES as _STATES  # noqa: E402
