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

import defence
import store

# Builders past this cost more in cost scaling (+20% each, on every later
# build) than an extra lane returns on the maps in the pool. Economies in the
# ladder's top ten run 4-7; the larger number only pays where there is ore for
# it, so it scales with the board.
BUILDER_TARGET_SMALL = 4
BUILDER_TARGET_LARGE = 6
LARGE_MAP_AREA = 500

# Titanium held back from spawning so a Builder that reaches its deposit can
# actually pay for the lane it walked to.
ECON_RESERVE = 45

# Once the alarm is up it stays up for this many rounds past the last damage.
# Flapping it would send menders home and back out again, which spends the
# walk twice and heals nothing.
ALARM_HOLD = 40


def run(player, ct) -> None:
    brain = player.brain
    brain.sense(ct)

    if brain.index is None:            # the Core's own bookkeeping
        brain.index = 0
        player.spawned = 0
        player.last_hp = ct.get_max_hp()
        player.last_damage = None
        player.last_threat = None

    _alarm(player, ct)
    _publish(player, ct)
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
    wanted = defence.menders_wanted(dps, len(builders))
    if wanted:
        player.last_threat = round_number

    # Hold the alarm past the last sighting. Flapping it walks menders home
    # and out again, which spends the journey twice and heals nothing.
    recent = (player.last_threat is not None
              and round_number - player.last_threat <= ALARM_HOLD)
    hurt = (player.last_damage is not None
            and round_number - player.last_damage <= ALARM_HOLD)
    if wanted:
        store.raise_alarm(ct, wanted)
    elif recent or hurt:
        store.raise_alarm(ct, max(1, store.alarm_level(ct)))
    elif store.alarm(ct):
        store.clear_alarm(ct)


def _publish(player, ct) -> None:
    kind = player.brain.imap.symmetry()
    if kind is not None and store.symmetry(ct) != kind:
        store.publish_symmetry(ct, kind)


def _ammo(player, ct) -> None:
    """Convert titanium to ammunition only for turrets that exist.

    Ammunition is a one-way door -- converted titanium cannot buy a Harvester
    -- so an economy converts nothing until it owns something that fires.
    """
    if not _have_turrets(player.brain):
        return
    if ct.get_global_ammo() >= 40:
        return
    want = min(20, max(0, ct.get_global_resources() - ECON_RESERVE))
    if want >= 10 and ct.can_convert_ammo(want):
        _try(ct.convert_ammo, want)


def _spawn(player, ct) -> None:
    brain = player.brain
    target = (BUILDER_TARGET_LARGE
              if brain.width * brain.height >= LARGE_MAP_AREA
              else BUILDER_TARGET_SMALL)
    if player.spawned >= target:
        return
    cost = ct.get_builder_bot_cost()
    # The first Builder is bought before the reserve applies: with no Builder
    # there is nothing to reserve titanium for.
    floor = 0 if player.spawned == 0 else ECON_RESERVE
    if ct.get_global_resources() < cost + floor:
        return
    for tile in ct.get_nearby_tiles(dist_sq=2):
        if ct.can_spawn(tile):
            if _try(ct.spawn_builder, tile):
                player.spawned += 1
                store.note_spawn(ct, player.spawned)
            return


def _have_turrets(brain) -> bool:
    for tile in brain.imap.tiles.values():
        name = _STATES[tile.state]
        if name.startswith(("OUR_GUNNER_", "OUR_SENTINEL_")):
            return True
    return False


def _try(action, *args) -> bool:
    try:
        action(*args)
        return True
    except GameError:
        return False


from utils.GCS.Base.protocol import TILE_STATES as _STATES  # noqa: E402
