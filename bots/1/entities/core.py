"""Core entity logic."""

from __future__ import annotations

from fcode import Controller


class CoreMixin:
    def run_core(self, ct: Controller) -> None:
        pass
