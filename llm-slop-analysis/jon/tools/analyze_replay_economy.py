"""Audit final economy topology directly from an fcode .replay26 event log.

No unpublished protobuf schema is required; this decodes the small subset of
the wire format needed for Cores, Harvesters, and Conveyors.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DIRECTION = {1: (0, -1), 3: (1, 0), 5: (0, 1), 7: (-1, 0)}


def read_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    value = shift = 0
    while True:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7


def fields(data: bytes):
    offset, result = 0, []
    while offset < len(data):
        key, offset = read_varint(data, offset)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, offset = read_varint(data, offset)
        elif wire == 1:
            value, offset = data[offset:offset + 8], offset + 8
        elif wire == 2:
            length, offset = read_varint(data, offset)
            value, offset = data[offset:offset + length], offset + length
        elif wire == 5:
            value, offset = data[offset:offset + 4], offset + 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")
        result.append((number, wire, value))
    return result


def message_dict(data: bytes) -> dict[int, list]:
    result: dict[int, list] = {}
    for number, _, value in fields(data):
        result.setdefault(number, []).append(value)
    return result


def position(data: bytes) -> tuple[int, int]:
    msg = message_dict(data)
    return msg.get(1, [0])[0], msg.get(2, [0])[0]


def unwrap(data: bytes):
    while True:
        decoded = fields(data)
        if len(decoded) == 1 and decoded[0][:2] == (1, 2):
            data = decoded[0][2]
        else:
            return decoded


def decode(path: Path):
    top = fields(path.read_bytes())
    snapshot = message_dict(next(value for number, _, value in top if number == 1))
    cores = {}
    for raw in snapshot.get(4, []):
        core = message_dict(raw)
        owner = core.get(1, [0])[0]
        cores[owner] = position(core[3][0])

    harvesters, conveyors = {}, {}
    for number, _, raw_round in top:
        if number != 3:
            continue
        for _, _, raw_event in fields(raw_round):
            event = unwrap(raw_event)
            values = {field: value for field, _, value in event}
            # Spawn/build events have scalar id + position + hp/maxhp.
            if not {1, 3, 4, 5}.issubset(values):
                continue
            team = values.get(2, 0)  # omitted for Team A, 1 for Team B
            if team != 0:
                continue
            entity_id, pos = values[1], position(values[3])
            if 15 in values:
                harvesters[entity_id] = pos
            elif 11 in values:
                marker = message_dict(values[11])
                conveyors[entity_id] = (pos, DIRECTION[marker[1][0]])
    return cores[1], harvesters, conveyors


def audit(path: Path):
    core, harvesters, conveyors_by_id = decode(path)
    footprint = {(core[0] + dx, core[1] + dy) for dx in (0, 1) for dy in (0, 1)}
    conveyors = {pos: direction for pos, direction in conveyors_by_id.values()}
    cardinal = tuple(DIRECTION.values())
    results, used = [], set()

    for entity_id, harvester in harvesters.items():
        if any((harvester[0] + dx, harvester[1] + dy) in footprint
               for dx, dy in cardinal):
            results.append({"id": entity_id, "position": harvester,
                            "connected": True, "length": 0, "reason": "direct"})
            continue
        starts = []
        for dx, dy in cardinal:
            tile = harvester[0] + dx, harvester[1] + dy
            if tile in conveyors:
                out = tile[0] + conveyors[tile][0], tile[1] + conveyors[tile][1]
                if out != harvester:
                    starts.append(tile)
        best_failure = "no accepting adjacent conveyor"
        success = None
        for start in starts:
            current, seen, route = start, set(), []
            while current in conveyors and current not in seen:
                seen.add(current)
                route.append(current)
                dx, dy = conveyors[current]
                nxt = current[0] + dx, current[1] + dy
                if nxt in footprint:
                    success = route
                    break
                if nxt not in conveyors:
                    best_failure = f"line ends at empty/non-conveyor tile {nxt}"
                    break
                receiver_out = (nxt[0] + conveyors[nxt][0], nxt[1] + conveyors[nxt][1])
                if receiver_out == current:
                    best_failure = f"head-on receiver at {nxt}"
                    break
                current = nxt
            if success is not None:
                break
            if current in seen:
                best_failure = f"conveyor loop at {current}"
        if success is not None:
            used.update(success)
            results.append({"id": entity_id, "position": harvester,
                            "connected": True, "length": len(success), "reason": "line"})
        else:
            results.append({"id": entity_id, "position": harvester,
                            "connected": False, "length": None, "reason": best_failure})

    disconnected = [item for item in results if not item["connected"]]
    return {
        "replay": str(path),
        "harvesters": len(results),
        "connected": len(results) - len(disconnected),
        "disconnected": disconnected,
        "conveyors": len(conveyors),
        "orphan_conveyors": len(set(conveyors) - used),
        "routes": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("replays", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    reports = [audit(path) for path in args.replays]
    if args.json:
        print(json.dumps(reports, indent=2))
        return
    for report in reports:
        print(f"{report['replay']}: {report['connected']}/{report['harvesters']} "
              f"harvesters connected; {report['orphan_conveyors']}/{report['conveyors']} "
              "orphan conveyors")
        for failure in report["disconnected"]:
            print(f"  harvester {failure['id']} at {tuple(failure['position'])}: "
                  f"{failure['reason']}")


if __name__ == "__main__":
    main()
