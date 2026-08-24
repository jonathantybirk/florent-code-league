"""Measure observed damage delivered to cores in replay files.

This counts attack events whose target is a core tile and converts them to gross
damage using the game rules.  Healing is reported separately; "DPS" here is
damage per game round, not net HP loss after repairs.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from analyze_mining_lanes import core_tiles, initial_state
from analyze_top_mining import message, parse_entity, pos, scalar, submessages


DAMAGE = {"bot": 2, "gunner": 7, "sentinel": 18}


def analyze(path: Path) -> dict:
    raw = path.read_bytes()
    _, _, _, entities = initial_state(raw)
    cores = {e.team: e for e in entities.values() if e.kind == "core"}
    regions = {team: core_tiles(core) for team, core in cores.items()}
    first_harvester = {0: None, 1: None}
    core_hits: dict[int, list[dict]] = defaultdict(list)
    heals: dict[int, list[int]] = defaultdict(list)

    turns = submessages(raw, 3)
    for turn_number, turn in enumerate(turns):
        for update in submessages(turn, 1):
            health = message(update, 5)
            if health is not None:
                entity = entities.get(scalar(health, 1))
                raw_delta = scalar(health, 2)
                delta = raw_delta - (1 << 64) if raw_delta >= (1 << 63) else raw_delta
                if entity is not None and entity.kind == "core" and delta < 0:
                    attacker = 1 - entity.team
                    core_hits[attacker].append(
                        {"turn": turn_number, "damage": -delta}
                    )
                continue
            place = message(update, 1)
            if place is not None and message(place, 1) is not None:
                entity = parse_entity(message(place, 1))
                entities[entity.id] = entity
                if entity.kind == "harvester" and first_harvester[entity.team] is None:
                    first_harvester[entity.team] = turn_number
                continue
            move = message(update, 2)
            if move is not None:
                entity = entities.get(scalar(move, 1))
                if entity is not None:
                    entity.position = pos(message(move, 2))
                continue
            remove = message(update, 3)
            if remove is not None:
                entities.pop(scalar(remove, 1), None)
                continue
            heal = message(update, 15)
            if heal is not None:
                actor = entities.get(scalar(heal, 1))
                target = pos(message(heal, 2))
                if actor is not None and target in regions[actor.team]:
                    heals[actor.team].append(turn_number)

    teams = []
    for team in (0, 1):
        hits = core_hits[team]
        by_turn = Counter()
        by_amount = Counter()
        for hit in hits:
            by_turn[hit["turn"]] += hit["damage"]
            by_amount[str(hit["damage"])] += 1
        first = min(by_turn, default=None)
        last = max(by_turn, default=None)
        span = None if first is None else last - first + 1
        gross = sum(by_turn.values())
        teams.append(
            {
                "first_harvester": first_harvester[team],
                "first_core_damage": first,
                "last_core_damage": last,
                "attack_span": span,
                "gross_core_damage": gross,
                "gross_dps_active_span": None if not span else gross / span,
                "peak_round_damage": max(by_turn.values(), default=0),
                "hits_by_damage_amount": dict(by_amount),
                "damaging_rounds": len(by_turn),
                "core_heals_received": len(heals[1 - team]),
                "hits": hits,
            }
        )
    return {"file": path.name, "turns": len(turns), "teams": teams}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    paths: list[Path] = []
    for path in args.paths:
        paths.extend(sorted(path.glob("*.replay26")) if path.is_dir() else [path])
    rendered = json.dumps([analyze(path) for path in paths], indent=2)
    if args.output:
        args.output.write_text(rendered + "\n")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
