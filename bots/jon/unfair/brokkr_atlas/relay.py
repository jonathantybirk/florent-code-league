"""A Launcher relay: throwing Builders at the enemy instead of walking them.

Travel is brokkr's largest single expense. The intent audit over the map pool
counted 15016 unit-turns of "closing on the belt" and 9793 of "coming home" --
more than harassing, mining and mending put together. A harasser on a 30x30
map spends twenty rounds walking to a lane, cuts it, and walks twenty rounds
back.

A Launcher throws a Builder to any bot-passable tile within radius^2 26 -- a
little over five tiles -- in one round, for one round of its reload. So a
Launcher every five tiles turns a twenty-round walk into four throws, and the
pathfinder already models exactly this: `Terrain.friendly_launchers` adds an
edge from each tile of a Launcher's pickup ring to everywhere it can throw,
costing one step. brokkr simply never built one, and always searched with
`hops=False`.

The relay is placed on the line between the two Cores because that is the line
every harasser and every attacker walks. It is deliberately sparse: a Launcher
is 20 Ti and +10% cost scale, which is half what a Builder costs in scaling,
but it is still a building that pays only if Builders keep using it.

Two things the engine makes awkward, both handled here rather than in the
caller:

  * a Launcher picks up from its eight adjacent tiles and throws from *itself*,
    so the useful throws are the ones that gain ground rather than merely move
    the Builder.
  * it will happily throw one of our own miners off its lane. So a throw has
    to be worth it -- see `worth_throwing`.
"""

# Engine geometry. Pickup is the adjacent ring; the throw is measured from the
# Launcher, not from the Builder it picked up.
THROW_RANGE_SQ = 26

# Relay stations, as a fraction of the way from our Core to theirs. The first
# is close enough that a Builder leaving home reaches it in a couple of
# rounds; beyond the halfway point a station sits in ground the enemy patrols
# and tends to be destroyed before it repays.
STATIONS = (0.22, 0.42)

# How far off the Core-to-Core line a station may be nudged to find buildable
# ground.
STATION_SLACK = 3

# A throw has to gain at least this many tiles of progress toward the
# destination, or it is just moving a Builder around for a round of reload.
MIN_GAIN = 3

# Titanium kept back so a relay station never comes out of the economy's or
# the mend squad's pocket. A Launcher is a convenience; a Harvester is income
# and a heal is 4 HP.
RESERVE = 90

# How far a Builder will step off its errand to found a station.
DETOUR = 12


def station_targets(brain, enemy_core):
    """Where relay Launchers should stand, nearest first."""
    core = brain.core_tiles()
    if not core or not enemy_core:
        return []
    ours = min(core)
    theirs = min(enemy_core)
    out = []
    for fraction in STATIONS:
        x = round(ours[0] + (theirs[0] - ours[0]) * fraction)
        y = round(ours[1] + (theirs[1] - ours[1]) * fraction)
        out.append((x, y))
    return out


def free_station(brain, wanted):
    """A buildable tile at or near `wanted`, or None.

    The line between two Cores runs through whatever the map puts there, so a
    station that cannot be built exactly is nudged rather than abandoned.
    """
    terrain = brain.terrain
    best = None
    for dx in range(-STATION_SLACK, STATION_SLACK + 1):
        for dy in range(-STATION_SLACK, STATION_SLACK + 1):
            spot = (wanted[0] + dx, wanted[1] + dy)
            if not terrain.inside(spot) or spot in terrain.blocked:
                continue
            if brain.is_free_ore(spot):
                continue                # never build a Launcher on a deposit
            gap = abs(dx) + abs(dy)
            if best is None or gap < best[0]:
                best = (gap, spot)
    return best[1] if best else None


def has_launcher_near(brain, spot, radius=STATION_SLACK + 1) -> bool:
    for tile in brain.our_launchers():
        if abs(tile[0] - spot[0]) + abs(tile[1] - spot[1]) <= radius:
            return True
    return False


def worth_throwing(bot, landing, destination) -> bool:
    """Whether the throw gains real ground for the Builder.

    Compared against the *landing tile*, which is the only comparison that
    means anything. Comparing the Builder to the Launcher cannot work: pickup
    range is the adjacent ring, so the two are always one tile apart and the
    test could never pass. That bug built the relay and then never threw
    anybody from it.
    """
    return _gap(bot, destination) - _gap(landing, destination) >= MIN_GAIN


def best_landing(ct, launcher, bot, destination, candidates):
    """The reachable landing tile closest to `destination`."""
    from fcode import Position
    best = None
    for tile in candidates:
        gap = _gap(tile, destination)
        if best is not None and gap >= best[0]:
            continue
        try:
            if ct.can_launch(Position(*bot), Position(*tile)):
                best = (gap, tile)
        except Exception:
            continue
    return best[1] if best else None


def throw_candidates(launcher, width, height):
    """Tiles a Launcher at `launcher` could throw to, coarse-filtered."""
    span = int(THROW_RANGE_SQ ** 0.5)
    out = []
    for dx in range(-span, span + 1):
        for dy in range(-span, span + 1):
            if dx * dx + dy * dy > THROW_RANGE_SQ:
                continue
            tile = (launcher[0] + dx, launcher[1] + dy)
            if 0 <= tile[0] < width and 0 <= tile[1] < height:
                out.append(tile)
    return out


def _gap(a, b) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])
