"""Builder bot entity logic."""

from __future__ import annotations

from fcode import Controller


class BuilderMixin:
    def run_builder(self, ct: Controller) -> None:
        pass
