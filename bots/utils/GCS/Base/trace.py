"""Per-round trace lines for tools/gcs_viz.py (Store Scope).

Any bot that runs the GCS can call `Tracer.emit()` once per unit per round,
after publish().  The line is printed; the engine keeps prints verbatim in
the .replay26, which is what the visualiser reads.

    tracer = Tracer()                       # one per unit
    ...
    result = gcs.absorb(ct); gcs.map.observe(ct); ... gcs.publish(ct)
    tracer.emit(ct, gcs, result, written_before)
"""

from __future__ import annotations

import json

from . import protocol as P


class Tracer:
    def __init__(self):
        self._dumped: dict = {}          # last traced (state, source, round) per tile layer

    def map_delta(self, gcs) -> list:
        """Tiles whose record changed since the last trace, per layer, so the
        viewer can rebuild the unit's whole internal map from deltas."""
        out = []
        tiles = getattr(gcs.map, "tiles", {})
        for (x, y), t in tiles.items():
            layers = (("t", getattr(t, "terrain", None)), ("b", getattr(t, "building", None)),
                      ("u", getattr(t, "unit", None)))
            for layer, rec in layers:
                if rec is None:
                    continue
                key = (x, y, layer)
                val = (rec.state, rec.source[0], rec.round)
                if self._dumped.get(key) != val:
                    self._dumped[key] = val
                    out.append([x, y, rec.state, rec.source[0], rec.round, layer])
        return out

    def emit(self, ct, gcs, result, written_before) -> None:
        reg = gcs.registry
        if reg is None:
            return
        pos = ct.get_position()
        m = gcs.map
        line = {
            "r": ct.get_current_round(), "id": ct.get_id(), "kind": gcs.kind,
            "slot": gcs.slot, "pos": [pos.x, pos.y],
            "wrote": gcs.last_written if gcs.last_written != written_before else None,
            "store": [ct.read_store(i) for i in range(P.STORE_SIZE)],
            "owners": {s: [o.kind, list(o.pos) if o.pos else None, o.has_written]
                       for s, o in reg.owners.items()},
            "slots": {s: d for s, d in result.per_slot.items()},
            "learned": [[f.x, f.y, f.state] for f in result.facts],
            "known": len(getattr(m, "tiles", {})),
            "map_delta": self.map_delta(gcs),
            "symmetry": m.symmetry() if hasattr(m, "symmetry") else None,
            "enemy_core": m.enemy_core() if hasattr(m, "enemy_core") else None,
            "our_core": getattr(m, "our_core", None),
            "resync": reg.resync_write_round, "onboard_until": reg.onboard_until,
            "core_hp": reg.core_hp,
        }
        print("GCSTRACE " + json.dumps(line, separators=(",", ":")))
