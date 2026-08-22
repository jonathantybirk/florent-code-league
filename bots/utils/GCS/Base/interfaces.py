"""Placeholder interfaces to modules that do not exist yet.

The GCS module must not reach outside its scope, so everything it needs from
the internal-map, logistics, and behaviour modules is declared here as a
minimal protocol plus a trivial standalone implementation.  PLACEHOLDER
markers show exactly what other modules are expected to replace.
"""

from __future__ import annotations

from typing import Iterable, Protocol

from .messages import Fact
from .protocol import STATE_CODE

# Priority class weights (tunable hyperparameters, one place).  Higher = sent
# first.  Symmetry outranks everything (it implies the enemy Core plus a
# mirror twin for every later fact); the issue overlays outrank terrain
# because they are actionable and perishable.
CLASS_WEIGHTS: dict[str, float] = {
    "ENEMY_CORE": 10.0,
    "ENEMY_GUNNER": 8.0, "ENEMY_SENTINEL": 8.0, "ENEMY_LAUNCHER": 8.0,
    "ENEMY_BUILDER_BOT": 7.0, "ENEMY_BOT_ON_CONVEYOR": 7.0,
    "ORE_FREE": 6.0,
    "CONVEYOR_ISSUE": 5.0, "HARVESTER_ISSUE": 5.0,
    "WALL": 4.0, "ENEMY_BARRIER": 4.0,
    "ENEMY_CONVEYOR": 3.5, "ENEMY_SPLITTER": 3.5, "ENEMY_HARVESTER": 3.5,
    "OUR_": 2.0,            # friendly infrastructure (prefix fallback)
    "EMPTY": 1.5,           # information negatives still matter
    "TOOK_FIRE_HERE": 1.0,
    "": 1.0,                # default
}


def state_weight(state: int) -> float:
    name = _NAMES[state] if state < len(_NAMES) else "UNKNOWN"
    for prefix, w in CLASS_WEIGHTS.items():
        if prefix and name.startswith(prefix):
            return w
    return CLASS_WEIGHTS[""]


_NAMES = tuple(STATE_CODE)      # index -> name


class MapSource(Protocol):
    """What the GCS needs from the internal-map module (not written yet)."""

    def pending_facts(self, budget: int) -> list[Fact]:
        """Up to `budget` unpublished facts, best first."""

    def apply_fact(self, fact: Fact, from_gcs: bool = True) -> None:
        """Record a fact.  from_gcs=True marks it already-published: anything
        absorbed from the store has by definition reached the whole team."""

    def note_shared(self, facts: Iterable[Fact]) -> None:
        """Mark exactly these facts published — called only for facts a
        confirmed write actually carried."""

    def symmetry(self) -> int | None:
        """The map's symmetry kind (protocol.SYMMETRY_KINDS index) if known."""


class DictMapSource:
    """Dict-backed MapSource so the GCS runs and tests standalone.

    PLACEHOLDER — the internal_map module replaces this with the real map,
    including freshness bookkeeping and observation input.
    """

    def __init__(self):
        self.tiles: dict[tuple[int, int], int] = {}
        self.published: set[tuple[int, int]] = set()
        self._symmetry: int | None = None

    def pending_facts(self, budget: int) -> list[Fact]:
        pending = [Fact(x, y, s) for (x, y), s in self.tiles.items()
                   if (x, y) not in self.published]
        pending.sort(key=lambda f: -state_weight(f.state))
        return pending[:budget]

    def apply_fact(self, fact: Fact, from_gcs: bool = True) -> None:
        self.tiles[(fact.x, fact.y)] = fact.state
        if from_gcs:
            self.published.add((fact.x, fact.y))
        else:
            self.published.discard((fact.x, fact.y))

    def note_shared(self, facts: Iterable[Fact]) -> None:
        for f in facts:
            self.published.add((f.x, f.y))

    def symmetry(self) -> int | None:
        return self._symmetry


# ---------------------------------------------------------------------------
# Logistics detectors — PLACEHOLDER, owned by the logistics module.
# Until implemented they report "no issue", so the CONVEYOR_ISSUE /
# HARVESTER_ISSUE tile states are wired end-to-end but never fire.
# ---------------------------------------------------------------------------

def has_conveyor_issue(pos: tuple[int, int]) -> bool:
    """PLACEHOLDER: is our conveyor at pos stalled/starved/mis-routed?"""
    return False


def has_harvester_issue(pos: tuple[int, int]) -> bool:
    """PLACEHOLDER: is our harvester at pos in trouble?"""
    return False


# ---------------------------------------------------------------------------
# Directive hook — PLACEHOLDER, owned by the behaviour/pathfinding modules.
# The GCS delivers directives; acting on them is not its job.
# ---------------------------------------------------------------------------

def on_directive(x: int, y: int, task: int) -> None:
    """PLACEHOLDER: called for each directive addressed to (or open to) this
    unit.  The behaviour module decides whether and how to obey."""
