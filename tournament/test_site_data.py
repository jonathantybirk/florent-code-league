from __future__ import annotations

from tournament.site_data import _benchmark, _game, _is_rating_match, _map_catalog, _record, _slug


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
