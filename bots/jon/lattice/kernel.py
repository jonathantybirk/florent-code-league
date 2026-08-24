"""The behaviour kernel: build a context, score every behaviour, run the best.

This is the whole control flow of a Builder Bot, and it is deliberately tiny.
There is no state machine and no transition table -- each round every behaviour
re-scores itself from current knowledge and the highest scorer runs. Long-term
conduct is an emergent property of consistent local scoring rather than of
remembered goals, which means a Builder never persists a plan that the board has
already invalidated.

Adding a capability to this bot means writing one `bhv_*` module and adding it to
`BEHAVIOURS`. Retuning priorities means editing `config.CEILINGS`. Neither
requires touching this file.

Behaviours are evaluated in descending order of their ceiling and the loop stops
as soon as the best score found cannot be beaten by any remaining ceiling, so a
turn that finds an urgent action never pays to evaluate the cheap ones.
"""
from __future__ import annotations

from fcode import Controller, GameError

import bhv_explore
import bhv_guard
import bhv_harvest
import bhv_mend
import bhv_route
import bhv_secure
import bhv_siege
import config

# Order is irrelevant -- the kernel sorts by ceiling -- but keeping it in
# priority order makes the list readable.
BEHAVIOURS = (
    bhv_guard,
    bhv_mend,
    bhv_siege,
    bhv_route,
    bhv_harvest,
    bhv_secure,
    bhv_explore,
)

_ORDERED = tuple(sorted(BEHAVIOURS,
                        key=lambda m: config.CEILINGS.get(m.NAME, 0.0),
                        reverse=True))


class Context:
    """Everything a behaviour is allowed to depend on, assembled once per turn.

    Behaviours must not stash state on the context between turns; anything that
    has to persist belongs on `memory`, which is the owning brain's own dict and
    is the only mutable carry-over in the design.
    """
    __slots__ = ("ct", "wm", "memory", "role", "scratch")

    def __init__(self, ct: Controller, wm, memory: dict, role: str):
        self.ct = ct
        self.wm = wm
        self.memory = memory
        self.role = role
        self.scratch = {}      # per-turn hand-off from score() to run()

    # Convenience wrappers: every behaviour needs these and none of them should
    # be allowed to raise out into the kernel.
    def can_act(self) -> bool:
        try:
            return self.ct.get_action_cooldown() == 0
        except GameError:
            return False

    def can_move(self) -> bool:
        try:
            return self.ct.get_move_cooldown() == 0
        except GameError:
            return False

    def titanium(self) -> int:
        try:
            return self.ct.get_global_resources()
        except GameError:
            return 0

    def budget_left(self) -> int:
        try:
            return config.CPU_BUDGET_US - self.ct.get_cpu_time_elapsed()
        except GameError:
            return 0

    def cpu_ok(self) -> bool:
        try:
            return self.ct.get_cpu_time_elapsed() < config.CPU_SAFE_US
        except GameError:
            return False


def run_turn(ctx: Context) -> str:
    """Score, pick, execute. Returns the name of whatever ran, for tracing."""
    best_score = 0.0
    best = None
    for module in _ORDERED:
        ceiling = config.CEILINGS.get(module.NAME, 0.0)
        if best is not None and best_score >= ceiling:
            break              # nothing left can beat what we already have
        if not ctx.cpu_ok() and ceiling < config.CEILINGS["siege"]:
            break              # out of budget: only the urgent tiers remain
        try:
            score = module.score(ctx)
        except GameError:
            score = 0.0
        if score > best_score:
            best_score = score
            best = module

    if best is None:
        return "idle"
    try:
        best.run(ctx)
    except GameError:
        pass
    return best.NAME
