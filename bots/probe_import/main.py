"""Probe: rushplan.py inside the sandbox -- junk handling and live Team-enum lookup.

Before running, copy the two modules under test in beside this file (they are deliberately NOT
kept here, so there is never a stale duplicate of bot/rushplan.py in the tree):

    cp bot/atlas.py bot/rushplan.py bots/probe_import/
    .venv/Scripts/python.exe tools/probe_run.py bots/probe_import sprint
"""

from fcode import Controller, EntityType

try:
    import rushplan
    ERR = None
except Exception as exc:
    rushplan = None
    ERR = "%s: %s" % (type(exc).__name__, exc)


class Player:
    def __init__(self):
        self.done = False

    def run(self, ct: Controller) -> None:
        if self.done:
            return
        try:
            if ct.get_entity_type() != EntityType.CORE:
                return
        except Exception:
            return
        self.done = True
        if rushplan is None:
            ct.resign("IMPORT FAILED %s" % ERR)
            return
        team = ct.get_team()
        o = []
        o.append("team=%r" % (team,))
        o.append("live=%s" % (rushplan.attack_plan("sprint", team),))
        o.append("junk=%r/%r/%r" % (rushplan.attack_plan("nope", None),
                                    rushplan.deny_tiles("nope", None),
                                    rushplan.recommendation("nope", None)))
        o.append("maps=%d plans=%d" % (len(rushplan.MAP_NAMES), len(rushplan.PLANS)))
        ct.resign("|".join(o))
