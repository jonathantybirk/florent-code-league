"""Lattice -- a modular, memoryless bot for fcode 2.3.4+.

Architecture
------------
One `Player` per unit. `run()` does three things and nothing else: refresh
perception, pick a brain by entity type, hand off. All the actual policy lives in
modules that can be swapped independently:

    config.py        every tunable, with the reasoning for its value
    geom.py          pure geometry; the 4-neighbour / 8-way distinction
    comms.py         the 16-slot store as a named schema
    world.py         perception and memory
    nav.py           reverse BFS pathing on the Builder's cardinal graph
    econ.py          delivery model: what is connected and how full the pipe is
    kernel.py        scores behaviours, runs the best
    bhv_*.py         one behaviour per file
    core_brain.py    spawn policy and ammunition
    turret_brain.py  firing policy

Why memoryless
--------------
Builders keep no state machine. Every round each one re-scores every behaviour
from current knowledge and runs the highest scorer, so a Builder cannot persist a
plan the board has already invalidated -- and long-term conduct emerges from
consistent local scoring rather than from remembered goals. The only carried
state is a small per-unit cache (a planned conveyor route, an opening explore
axis), and every entry in it is revalidated before use.

What the design is built around
-------------------------------
Healing restores 4 HP for a flat 1 Ti and is immune to cost scale; a Sentinel
spends 10 ammo to deal 18 damage. Defence therefore buys 4 HP per titanium
against offence's 1.8. A tended Core does not die, so most games reach the
round-1000 tiebreak, which is decided by titanium *collected* -- stacks that
physically landed on a Core tile. So the bot plays for delivery, defends what
delivers, and shoots the enemy's supply rather than their guns.
"""
from __future__ import annotations

from fcode import Controller, EntityType, GameError

import comms
import core_brain
import kernel
import roles
import turret_brain
import world


class Player:
    def __init__(self):
        self.wm = world.WorldModel()
        self.memory = {}
        self.core = core_brain.CoreBrain()
        self.turret = turret_brain.TurretBrain()
        self.roles = roles.RoleTracker()
        self.kind = None

    def run(self, ct: Controller) -> None:
        # Nothing may escape: an uncaught exception permanently destroys the unit
        # for the rest of the match, which is far worse than losing one turn.
        try:
            self._play(ct)
        except GameError:
            pass
        except (ValueError, IndexError, KeyError, TypeError, AttributeError,
                ZeroDivisionError, OverflowError):
            pass

    def _play(self, ct: Controller) -> None:
        if self.kind is None:
            self.kind = ct.get_entity_type()

        self.wm.observe(ct)

        if self.kind == EntityType.CORE:
            self.core.run(ct, self.wm)
            return

        if self.kind == EntityType.BUILDER_BOT:
            comms.bump(ct, comms.BUILDER_TICK)
            ctx = kernel.Context(ct, self.wm, self.memory,
                                 role=self.roles.resolve(ct, self.wm))
            kernel.run_turn(ctx)
            return

        # Gunner, Sentinel, Launcher.
        self.turret.run(ct, self.wm)
