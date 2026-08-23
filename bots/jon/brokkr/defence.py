"""Reading the threat to our Core, and what to do about it.

The whole defensive case rests on one piece of arithmetic. Healing costs 1
titanium for 4 HP; a Sentinel spends 10 ammunition -- 10 titanium -- to deal
18, or 1.8 HP per titanium. Mending is therefore 2.2x more titanium-efficient
than shooting, so an attacker who commits a fixed opening budget cannot break
a Core whose owner comes home. An all-in Sentinel rush can afford roughly 292
titanium of ammunition, about 522 damage, against a 500 HP Core: it wins by a
hair against a Core nobody defends and loses outright against one that heals.

Which makes *when* the alarm fires the entire game. Firing it on damage taken
means the ring is already built and firing; a Builder ten tiles out spends ten
rounds walking home while 36 damage a round lands, and arrives to a Core with
150 HP left. Firing it when an enemy Builder first appears near our Core buys
those same ten rounds back, and the ring gets built into a base that is
already healing. This module exists to make that trigger early and explicit
rather than a side effect of the HP ledger.

Digging a turret out is the other half. A Builder hits an adjacent building
for 2 damage at 2 titanium, so a 40 HP Sentinel costs 40 titanium and twenty
rounds to remove -- worse per titanium than healing, but it removes 9 damage a
round permanently instead of repairing 4. Below the crossover the ring wins by
attrition no matter how much we heal, so the two are not alternatives: healing
holds the Core up while digging shortens the siege.
"""

from utils.GCS.Base.protocol import TILE_STATES as _STATES

# How near our Core an enemy has to come before it counts as an attack. The
# Core's own vision is radius 6 (r^2 = 36), so anything it can see at all is
# already close enough to matter; the margin covers Builders sighted by a
# Builder of ours standing further out.
THREAT_RADIUS = 8

# Damage a round, by what is standing there. A Sentinel fires 18 every two
# rounds, a Gunner 7 every round. An enemy Builder near our Core is not doing
# damage yet, but it is what turns into a turret, which is the thing we need
# the warning about.
TURRET_DPS = {"ENEMY_SENTINEL": 9.0, "ENEMY_GUNNER": 7.0}
BUILDER_THREAT = 4.0

# One mender per this much incoming damage, plus one, as the opening guess
# before any damage has actually landed.
DPS_PER_MENDER = 9.0
SIGHTING_MENDERS = 5

# A siege can ask for more than the economy would ever buy. Each Builder heals
# 4 HP a round, so holding a four-Sentinel ring at 36 needs nine of them --
# and every one costs 20% on every later build, which is why the number is
# reached by feedback rather than by prediction (see `adjust`).
SIEGE_MENDERS = 10


def survey(brain):
    """What is threatening our Core right now.

    Returns ``(dps, builders, turrets)`` -- incoming damage a round from
    turrets in range, the enemy Builder positions near our Core, and the
    turret positions, nearest first.
    """
    core = brain.core_tiles()
    if not core:
        return 0.0, [], []
    dps = 0.0
    builders, turrets = [], []
    for key, tile in brain.imap.tiles.items():
        name = _STATES[tile.state]
        if not name.startswith("ENEMY_"):
            continue
        if _near(key, core) > THREAT_RADIUS:
            continue
        if name.startswith("ENEMY_BUILDER_BOT") or name.startswith("ENEMY_BOT_ON_CONVEYOR"):
            builders.append(key)
        else:
            family = name.rsplit("_", 1)[0] if name[-2:-1] == "_" else name
            for prefix, rate in TURRET_DPS.items():
                if name.startswith(prefix):
                    dps += rate
                    turrets.append(key)
                    break
    turrets.sort(key=lambda t: _near(t, core))
    builders.sort(key=lambda b: _near(b, core))
    return dps, builders, turrets


def heal_spots(brain):
    """Tiles a mender can actually heal the Core from.

    Heal, like build and attack, reaches orthogonally only -- the four
    diagonal tiles touching a Core corner are useless to a mender. Walking
    home with `exact=False` treats all eight as arrival, so a Builder that
    reached a corner tile stood there for the rest of the match healing
    nothing while the Core died: traced on helheim, two of four menders were
    parked that way from round 60 to the loss on round 73.
    """
    core = brain.core_tiles()
    spots = set()
    for tile in core:
        for delta in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            spot = (tile[0] + delta[0], tile[1] + delta[1])
            if spot in core or not brain.terrain.inside(spot):
                continue
            if spot in brain.terrain.blocked and spot != brain.me:
                continue
            spots.add(spot)
    return spots


def diggable(brain, turrets):
    """Enemy turrets orthogonally adjacent to us, worst first.

    Attack, like heal and build, reaches orthogonally only.
    """
    me = brain.me
    out = [t for t in turrets
           if abs(t[0] - me[0]) + abs(t[1] - me[1]) == 1]
    out.sort(key=lambda t: -_dps_of(brain, t))
    return out


def _dps_of(brain, tile) -> float:
    name = _STATES[brain.imap.state_at(*tile) or 0]
    for prefix, rate in TURRET_DPS.items():
        if name.startswith(prefix):
            return rate
    return 0.0


def menders_wanted(dps: float, enemy_builders: int) -> int:
    """How many Builders should come home.

    Sized to the damage actually on the board rather than re-decided every
    round on turret counts: hildr's log records that flip-flopping this bought
    exactly one mender, which is enough to lose the race and not enough to
    survive it.
    """
    if dps <= 0 and enemy_builders == 0:
        return 0
    effective = dps + BUILDER_THREAT * min(enemy_builders, 2)
    return max(1, min(SIGHTING_MENDERS, int(effective / DPS_PER_MENDER) + 1))


def adjust(wanted: int, floor: int, hp_delta: int) -> int:
    """Track the Core's net HP instead of predicting the damage.

    `hp_delta` is the Core's HP change since last round, already net of our
    own healing, which makes it the only honest measure of whether the mend
    squad is big enough. Sizing the squad from observed turret DPS alone
    cannot serve both a lone scout and a four-Sentinel ring: a count tuned for
    the ring wrecks the economy every time somebody walks past, and a count
    tuned for the scout loses the ring. Measured on the pool, the fixed guess
    gave 24/30 against hildr and 6/30 against steward.

    Rising by one a round is fast enough because the Core spawns menders on
    its own ring, where they heal the round they appear.
    """
    if hp_delta < 0:
        return min(SIEGE_MENDERS, max(wanted, floor) + 1)
    if hp_delta > 0 and wanted > floor:
        return wanted - 1           # winning the exchange: give one back
    return max(wanted, floor)


def _near(tile, core) -> int:
    return min(abs(tile[0] - c[0]) + abs(tile[1] - c[1]) for c in core)
