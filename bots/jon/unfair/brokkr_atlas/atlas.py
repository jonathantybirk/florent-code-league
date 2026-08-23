"""Recognise which pool map we are on, and use what that tells us.

This module is inert unless a generated `mapdata.py` sits beside it. brokkr
ships without one and is unaffected; `bots/jon/unfair/brokkr_atlas` ships with
one. The split is this repo's fair/unfair convention, and it is also the only
honest way to measure what the knowledge is worth: the two bots are otherwise
the same source.

What it buys is the opening. brokkr's largest measured weakness is that its
first Harvester lands on round 14 where the ladder's top ten manage 3 to 6,
and the intent trace says why: Builders spawned on rounds 2-4 wander with
`ore=0` until round 12 because nobody can see any. A recognised map hands them
every deposit and the symmetry axis on round 0.

Identification is by elimination rather than by hash, because a hash needs the
whole grid and we only ever have a corner of it. Map dimensions alone settle
six of the fifteen; the rest fall out after a few rounds of terrain agreeing
with exactly one candidate. A candidate is dropped the moment any observed
terrain tile disagrees, so a map outside the pool identifies as nothing and
the bot plays on unchanged -- which is what happens in a final, by design.
"""

try:
    from mapdata import MAPS, SYMMETRIES
except ImportError:                     # the fair build ships no atlas
    MAPS, SYMMETRIES = {}, ()

from utils.GCS.Base.protocol import STATE_CODE

# Only these tell us about terrain. Everything else on a tile is a building or
# a unit, which says nothing about the ground underneath and would eliminate
# the correct map -- an ore tile with a Harvester on it reads as HARVESTER.
_TERRAIN_CHAR = {
    STATE_CODE["EMPTY"]: "0",
    STATE_CODE["WALL"]: "1",
    STATE_CODE["ORE_FREE"]: "2",
}

# Enough agreeing tiles that a coincidence between two same-sized maps is not
# credible. A Core sees 113 tiles, so this is reached on round 0.
MIN_EVIDENCE = 40


def available() -> bool:
    return bool(MAPS)


def identify(brain):
    """The pool map matching everything we have seen, or None.

    None means either "not enough evidence yet" or "not a pool map"; the
    caller cannot tell them apart and does not need to, since both mean
    "carry on without help".
    """
    if not MAPS:
        return None
    candidates = [(name, entry) for name, entry in MAPS.items()
                  if entry[0] == brain.width and entry[1] == brain.height]
    if not candidates:
        return None

    evidence = 0
    for (x, y), tile in brain.imap.tiles.items():
        char = _TERRAIN_CHAR.get(tile.state)
        if char is None:
            continue
        evidence += 1
        candidates = [c for c in candidates if c[1][3][y][x] == char]
        if not candidates:
            return None
    if len(candidates) != 1 or evidence < MIN_EVIDENCE:
        return None
    # The evidence bar applies even when the dimensions are unique in the
    # pool. Six pool maps have a size nothing else shares, and skipping the
    # terrain check for those would identify *any* map of that size as the
    # pool one and then teach the bot a deposit list belonging to somewhere
    # else. A Core sees 113 tiles on round 0, so the bar costs nothing.
    return candidates[0][0]


def teach(brain, name) -> int:
    """Give the unit everything the atlas knows. Returns deposits added.

    Terrain is fed in as ordinary map facts, so every downstream query --
    route planning, the blocked set, deposit selection -- treats atlas
    knowledge exactly as it treats something a Builder walked past and saw.
    """
    entry = MAPS.get(name)
    if entry is None:
        return 0
    _width, _height, kind, rows, ore = entry
    if kind in SYMMETRIES:
        brain.imap.set_symmetry(SYMMETRIES.index(kind))
    added = brain.learn_ore(ore)
    # Walls matter too: they are what makes an optimistic route across
    # unrevealed ground wrong, and a lane planned through a wall is rebuilt
    # from scratch the moment a Builder reaches it.
    brain.learn_walls(
        (x, y)
        for y, row in enumerate(rows)
        for x, char in enumerate(row)
        if char == "1"
    )
    return added
