"""Does nothing. Opponent for the econ_demo smoke test so only one side's
economy timeline matters -- running econ_demo against itself lets whichever
side resigns first end the match before the other side's own value is ever
seen."""

from fcode import Controller


class Player:
    def run(self, ct: Controller) -> None:
        pass
