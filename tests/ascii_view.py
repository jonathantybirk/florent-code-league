"""A crude "replay" for tests/fake_controller.py scenarios: render a
World as an ASCII grid, and capture a sequence of those across rounds
into one text blob you can open in an editor or print to a terminal.

Not a replacement for the real fcode visualizer -- draw_indicator_*
calls are no-ops on FakeController (see fake_controller.py's module
docstring), and this understands neither HP, ammo, nor CPU. It exists
for a much narrower purpose: eyeballing a scenario's layout, or watching
it evolve round to round, while writing or debugging a test -- the same
role `fcode run --watch` plays for a real match, at a fraction of the
fidelity and none of the setup.
"""

from __future__ import annotations

from fcode import Direction, EntityType, Position, Team

from fake_controller import World

_CONVEYOR_GLYPH = {
    Direction.NORTH: "^",
    Direction.SOUTH: "v",
    Direction.EAST: ">",
    Direction.WEST: "<",
}

# Team-neutral base glyph per building type; upper-cased for Team B by
# _glyph_for. Conveyors are handled separately (direction, not type,
# picks the glyph) and are drawn the same for both teams, since which
# team a belt belongs to rarely matters for reading a scenario at a
# glance -- give it a team-specific glyph here if a test ever needs to
# tell them apart.
_BUILDING_GLYPH = {
    EntityType.CORE: "c",
    EntityType.HARVESTER: "h",
    EntityType.SPLITTER: "p",
    EntityType.BARRIER: "k",
    EntityType.GUNNER: "g",
    EntityType.SENTINEL: "s",
    EntityType.LAUNCHER: "l",
}

LEGEND = (
    "u/U builder bot   c/C core       h/H harvester   p/P splitter\n"
    "k/K barrier       g/G gunner     s/S sentinel     l/L launcher\n"
    "^v<> conveyor (facing)   o ore   # wall   . empty\n"
    "lowercase = Team A, UPPERCASE = Team B"
)


def _glyph_for(world: World, pos: Position) -> str:
    # A Builder Bot standing on a walkable building (Conveyor/Splitter)
    # is drawn on top, since that's what's actually there.
    bot = world.builder_at(pos)
    if bot is not None:
        return "U" if bot.team == Team.B else "u"

    b = world.building_at(pos)
    if b is not None:
        if b.etype == EntityType.CONVEYOR:
            ch = _CONVEYOR_GLYPH.get(b.direction, "+")
        else:
            ch = _BUILDING_GLYPH.get(b.etype, "?")
        return ch.upper() if b.team == Team.B else ch

    if pos in world.walls:
        return "#"
    if pos in world.ore:
        return "o"
    return "."


def render_ascii(
    world: World,
    *,
    top_left: Position | None = None,
    bottom_right: Position | None = None,
) -> str:
    """One character per tile -- see LEGEND. top_left/bottom_right (both
    inclusive) restrict rendering to a sub-rectangle, for a large World
    where only one corner matters.
    """
    x0 = top_left.x if top_left is not None else 0
    y0 = top_left.y if top_left is not None else 0
    x1 = bottom_right.x if bottom_right is not None else world.width - 1
    y1 = bottom_right.y if bottom_right is not None else world.height - 1
    rows = [
        "".join(_glyph_for(world, Position(x, y)) for x in range(x0, x1 + 1))
        for y in range(y0, y1 + 1)
    ]
    return "\n".join(rows)


class AsciiReplay:
    """Capture render_ascii() snapshots across rounds into one text blob.

    Usage sketch:

        replay = AsciiReplay()
        for i in range(50):
            ct = world.controller_for(unit_id)
            economy.run(ct, state)
            world.advance_round()
            replay.capture(world, label=f"after run {i}")
        replay.write("scratch/route.txt")  # or print(replay.text())
    """

    def __init__(self) -> None:
        self.frames: list[str] = []

    def capture(self, world: World, label: str | None = None, **viewport: Position) -> None:
        header = f"--- round {world.round}" + (f" ({label})" if label else "") + " ---"
        self.frames.append(header + "\n" + render_ascii(world, **viewport))

    def text(self) -> str:
        body = "\n\n".join(self.frames) if self.frames else "(no frames captured)"
        return f"{body}\n\n{LEGEND}"

    def write(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.text())
