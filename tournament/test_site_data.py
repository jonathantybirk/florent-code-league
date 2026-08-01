from __future__ import annotations

from tournament.site_data import _game, _map_catalog, _record, _slug


def row(a: str, b: str, score_a: float, turns: int = 20) -> dict:
    return {
        "bot_a": a,
        "bot_b": b,
        "score_a": str(score_a),
        "winner": "a" if score_a == 1 else "b" if score_a == 0 else "draw",
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


def test_map_catalog_contains_dimensions_terrain_and_cores():
    [atoll] = _map_catalog(["atoll"])
    assert (atoll["width"], atoll["height"]) == (18, 18)
    assert len(atoll["terrain"]) == 18
    assert len(atoll["terrain"][0]) == 18
    assert len(atoll["cores"]) == 2
