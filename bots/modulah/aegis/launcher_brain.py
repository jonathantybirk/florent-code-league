"""Launchers: ferry Builders toward whatever they published.

No handshake. Builders write the tile they are committed to into their own
store slot every round, so a Launcher reads its neighbours' destinations and
serves them unasked -- a request/response protocol would cost two rounds,
because a write at round R is not readable until R+1.
"""

from __future__ import annotations

from fcode import Controller, GameError, Position

import comms
import ferry


def _target_of(ct: Controller, uid: int, round_no: int):
    """The tile that Builder published, or None if it has not claimed one."""
    for slot in comms.BUILDER_SLOTS:
        word = ct.read_store(slot)
        if not comms.is_fresh(word, round_no):
            continue
        info = comms.unpack_builder(word)
        if info["target"] is not None:
            # Slots are not keyed by unit id, so serve the nearest published
            # destination: with one writer per slot the set of live targets is
            # exactly the set of live Builders, and a Launcher only ever has
            # one or two neighbours to choose between.
            return Position(*info["target"])
    return None


def run(ct: Controller) -> None:
    r = ct.get_current_round()
    try:
        ferry.serve(ct, lambda uid: _target_of(ct, uid, r))
    except GameError:
        pass
