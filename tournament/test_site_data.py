from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from tournament.maps import SECRET_ROOT
from tournament.site_data import build, _benchmark, _game, _is_rating_match, _map_catalog, _record, _slug


def row(a: str, b: str, score_a: float, turns: int = 20) -> dict:
    return {
        "bot_a": a,
        "bot_b": b,
        "score_a": str(score_a),
        "winner": "a" if score_a == 1 else "b" if score_a == 0 else "draw",
        "status": "ok",
        "turns": str(turns),
        "win_condition": "core_destroyed",
        "match_id": f"{a}-{b}-{score_a}",
    }


def test_record_is_from_the_selected_bots_perspective():
    rows = [row("alpha", "beta", 1), row("beta", "alpha", 1), row("alpha", "beta", 0.5)]
    assert _record(rows, "alpha") == {
        "games": 3,
        "wins": 1,
        "draws": 1,
        "losses": 1,
        "win_rate": 0.5,
    }


def test_game_names_gold_and_silver_from_engine_order():
    assert _game(row("alpha", "beta", 1), "alpha")["side"] == "gold"
    silver = _game(row("beta", "alpha", 0), "alpha")
    assert silver["side"] == "silver"
    assert silver["result"] == "win"


def test_game_displays_final_engine_coinflip_as_draw():
    match = row("alpha", "beta", 1)
    match["win_condition"] = "coinflip"
    assert _game(match, "alpha")["result"] == "draw"
    assert _game(match, "beta")["result"] == "draw"


def test_slug_is_stable_and_disambiguates_commits():
    first = _slug("vanguard@1234567")
    assert first == _slug("vanguard@1234567")
    assert first != _slug("vanguard@7654321")


def test_historical_rows_without_a_kind_are_rating_matches():
    assert _is_rating_match({})
    assert _is_rating_match({"kind": ""})
    assert _is_rating_match({"kind": "rating"})
    assert not _is_rating_match({"kind": "compliance"})


def test_map_catalog_contains_dimensions_terrain_and_cores():
    [atoll] = _map_catalog(["atoll"])
    assert (atoll["width"], atoll["height"]) == (18, 18)
    assert len(atoll["terrain"]) == 18
    assert len(atoll["terrain"][0]) == 18
    assert len(atoll["cores"]) == 2
    assert atoll["secret"] is False


@pytest.mark.skipif(not any(SECRET_ROOT.glob("*.map26")), reason="no held-out maps present")
def test_map_catalog_publishes_no_terrain_for_a_held_out_map():
    name = f"secret/{sorted(SECRET_ROOT.glob('*.map26'))[0].stem}"
    [held_out] = _map_catalog([name])
    assert held_out["secret"] is True
    # Size is published so the map can be identified; the terrain never is.
    assert held_out["width"] > 0 and held_out["height"] > 0
    assert held_out["terrain"] == []
    assert held_out["cores"] == []


def test_benchmark_recomputes_ratings_for_the_selected_field():
    matches = [
        row("alpha", "beta", 1),
        row("beta", "gamma", 1),
        row("gamma", "alpha", 1),
    ]
    metadata = {
        bot_id: {"name": bot_id, "commit": "1234567", "tags": []}
        for bot_id in ("alpha", "beta", "gamma")
    }
    compliance = {
        "alpha": {"status": "pass"},
        "beta": {"status": "pass"},
        "gamma": {"status": "exceeded"},
    }

    all_matches, all_rankings = _benchmark(
        matches, {"alpha", "beta", "gamma"}, metadata, compliance
    )
    within_time_matches, within_time_rankings = _benchmark(
        matches, {"alpha", "beta"}, metadata, compliance
    )

    assert len(all_matches) == 3
    assert {ranking["bot_id"] for ranking in all_rankings} == {"alpha", "beta", "gamma"}
    assert len(within_time_matches) == 1
    assert [ranking["bot_id"] for ranking in within_time_rankings] == ["alpha", "beta"]
    assert within_time_rankings[0]["games"] == 1
    assert within_time_rankings[0]["melo_r"] != next(
        ranking["melo_r"] for ranking in all_rankings if ranking["bot_id"] == "alpha"
    )


def _match(a: str, b: str, map_name: str, score_a: float) -> dict:
    return {
        **row(a, b, score_a),
        "map": map_name,
        "kind": "rating",
        "match_id": f"{a}-{b}-{map_name}-{score_a}",
    }


def _write_run(run_dir: Path, bots: list[str], matches: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "ratings-distinct.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["bot_id"])
        writer.writeheader()
        for bot_id in bots:
            writer.writerow({"bot_id": bot_id})
    columns = sorted({key for match in matches for key in match})
    with open(run_dir / "matches-distinct.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(matches)


@pytest.mark.skipif(not any(SECRET_ROOT.glob("*.map26")), reason="no held-out maps present")
def test_build_rates_each_map_pool_separately_and_counts_core_maps(tmp_path):
    held_out = f"secret/{sorted(SECRET_ROOT.glob('*.map26'))[0].stem}"
    bots = ["alpha", "beta"]
    # alpha sweeps the official maps; beta sweeps the held-out one. Whoever wins a pool is that
    # pool's sole core agent, so the two pools must disagree about who leads.
    matches = [
        _match("alpha", "beta", "atoll", 1),
        _match("beta", "alpha", "atoll", 0),
        _match("alpha", "beta", "duel", 1),
        _match("beta", "alpha", "duel", 0),
        _match("beta", "alpha", held_out, 1),
        _match("alpha", "beta", held_out, 0),
    ]
    _write_run(tmp_path / "run", bots, matches)
    index = build(tmp_path / "run", tmp_path / "site")

    assert [pool["id"] for pool in index["map_pools"]] == ["", "_secret", "_combined"]
    assert index["field"]["maps"] == 2
    assert index["field_secret"]["maps"] == 1
    assert index["field_combined"]["maps"] == 3

    def core_maps(key: str) -> dict[str, int]:
        return {bot["bot_id"]: bot["nash_core_maps"] for bot in index[key]}

    # Counted within the selected pool: alpha owns both official maps, beta owns the held-out one.
    assert core_maps("rankings") == {"alpha": 2, "beta": 0}
    assert core_maps("rankings_secret") == {"alpha": 0, "beta": 1}
    assert core_maps("rankings_combined") == {"alpha": 2, "beta": 1}
    assert {bot["pool_maps"] for bot in index["rankings_secret"]} == {1}

    # The pooled ratings themselves are pool-scoped, not filtered client-side.
    assert {bot["games"] for bot in index["rankings_secret"]} == {2}
    assert {bot["games"] for bot in index["rankings"]} == {4}

    # And the held-out map's own page still publishes no terrain.
    page = json.loads((tmp_path / "site" / "maps" / held_out.replace("/", "--")).with_suffix(".json").read_text())
    assert page["map"]["terrain"] == []


@pytest.mark.skipif(not any(SECRET_ROOT.glob("*.map26")), reason="no held-out maps present")
def test_build_refuses_to_publish_a_pool_with_unplayed_pairs(tmp_path, capsys):
    held_out = f"secret/{sorted(SECRET_ROOT.glob('*.map26'))[0].stem}"
    # gamma reaches the held-out map, but never plays beta there. An unplayed pair enters the
    # payoff matrix as 0, which reads exactly like a measured draw -- so the pool must not ship.
    matches = [
        _match("alpha", "beta", "atoll", 1),
        _match("beta", "gamma", "atoll", 1),
        _match("gamma", "alpha", "atoll", 1),
        _match("alpha", "beta", held_out, 1),
        _match("gamma", "alpha", held_out, 1),
    ]
    _write_run(tmp_path / "run", ["alpha", "beta", "gamma"], matches)
    index = build(tmp_path / "run", tmp_path / "site")

    # Only the held-out pool has the hole. Pooled over both map sets every pair has played
    # something, so the combined matrix is full and stays publishable.
    assert [pool["id"] for pool in index["map_pools"]] == ["", "_combined"]
    assert "rankings_secret" not in index
    assert "rankings_combined" in index
    output = capsys.readouterr().out
    assert "_secret" in output and "beta" in output and "gamma" in output


def test_build_raises_when_the_standard_pool_itself_is_incomplete(tmp_path):
    matches = [_match("alpha", "beta", "atoll", 1), _match("gamma", "alpha", "atoll", 1)]
    _write_run(tmp_path / "run", ["alpha", "beta", "gamma"], matches)
    with pytest.raises(RuntimeError, match="standard map pool is incomplete"):
        build(tmp_path / "run", tmp_path / "site")
