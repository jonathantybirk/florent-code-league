"""Builder bot entity logic: build a launcher, then wait beside it to be thrown."""

from __future__ import annotations

from fcode import Controller, Direction


class BuilderMixin:
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.built_launcher = False

    def run_builder(self, ct: Controller) -> None:
        if self.built_launcher or ct.get_action_cooldown() != 0:
            return

        pos = ct.get_position()
        for d in Direction:
            build_pos = pos.add(d)
            if ct.can_build_launcher(build_pos):
                ct.build_launcher(build_pos)
                self.built_launcher = True
                return
