"""Tests for duplicate-bot detection."""

from __future__ import annotations

import pytest

from tournament.duplicates import behaviour_groups, code_groups, render, score_table
from tournament.registry import BotSpec


_COUNTER = iter(range(1_000_000))


def _row(a: str, b: str, score: float, status: str = "ok") -> dict:
    return {
        "bot_a": a,
        "bot_b": b,
        "score_a": score,
        "status": status,
        "winner": "a" if score > 0.5 else "b" if score < 0.5 else "draw",
        "match_id": f"{a}|{b}|{score}|{next(_COUNTER)}",
    }


def _field(results: dict[tuple[str, str], float], opponents: list[str]) -> list[dict]:
    """Build rows where `results[(bot, opponent)]` is the bot's score against that opponent.

    A fractional score is realised as that fraction of four wins, so a rate like 0.75 comes from
    genuine per-match outcomes rather than a fabricated aggregate.
    """
    rows = []
    for (bot, other), score in results.items():
        wins = round(score * 4)
        for game in range(4):
            rows.append(_row(bot, other, 1.0 if game < wins else 0.0))
    return rows


# Four opponents with pairwise-distinct records among themselves, so the backdrop cannot itself
# register as a duplicate group and confuse the assertions below.
BACKDROP = {
    ("w", "x"): 1.0, ("w", "y"): 1.0, ("w", "z"): 1.0,
    ("x", "y"): 1.0, ("x", "z"): 1.0,
    ("y", "z"): 1.0,
}
FOILS = ["w", "x", "y", "z"]


def _members(groups) -> set[frozenset[str]]:
    return {frozenset(g.members) for g in groups}


def test_finds_two_bots_with_identical_results():
    rows = _field(
        BACKDROP
        | {
            ("twin_a", "w"): 1.0, ("twin_a", "x"): 1.0, ("twin_a", "y"): 0.0, ("twin_a", "z"): 1.0,
            ("twin_b", "w"): 1.0, ("twin_b", "x"): 1.0, ("twin_b", "y"): 0.0, ("twin_b", "z"): 1.0,
        },
        FOILS,
    )
    groups = behaviour_groups(rows)
    assert _members(groups) == {frozenset(("twin_a", "twin_b"))}
    assert groups[0].kind == "behaviour"


def test_does_not_flag_bots_that_differ_on_one_opponent():
    """A single differing opponent is enough to be a different player."""
    rows = _field(
        BACKDROP
        | {
            ("a", "w"): 1.0, ("a", "x"): 1.0, ("a", "y"): 0.0, ("a", "z"): 1.0,
            ("b", "w"): 1.0, ("b", "x"): 1.0, ("b", "y"): 1.0, ("b", "z"): 1.0,  # differs on y
        },
        FOILS,
    )
    assert frozenset(("a", "b")) not in _members(behaviour_groups(rows))


def test_tolerance_finds_near_duplicates():
    """'Seem to be identical' -- a small consistent gap should be catchable but not by default."""
    rows = _field(
        BACKDROP
        | {
            ("a", "w"): 1.0, ("a", "x"): 1.0, ("a", "y"): 0.75, ("a", "z"): 1.0,
            ("b", "w"): 1.0, ("b", "x"): 1.0, ("b", "y"): 1.0, ("b", "z"): 1.0,
            ("a", "b"): 0.5,
        },
        FOILS,
    )
    assert frozenset(("a", "b")) not in _members(behaviour_groups(rows, tolerance=0.0))
    assert frozenset(("a", "b")) in _members(behaviour_groups(rows, tolerance=0.25))


def test_bots_differing_only_in_beating_each_other_are_not_duplicates():
    """Regression: excluding the pair's own result is necessary but not sufficient.

    `w` and `x` below have identical records against every shared opponent and differ only in
    that w beats x. They are not redundant -- the paper's duplicate ties with its original
    (Definition 3) -- so the even-head-to-head condition must reject this.
    """
    rows = _field(BACKDROP, FOILS)
    assert frozenset(("w", "x")) not in _members(behaviour_groups(rows))


def test_three_way_duplicate_is_one_group_not_three_pairs():
    triplet = {
        (name, foil): score
        for name in ("a", "b", "c")
        for foil, score in (("w", 1.0), ("x", 1.0), ("y", 0.0), ("z", 1.0))
    }
    groups = behaviour_groups(_field(BACKDROP | triplet, FOILS))
    assert frozenset(("a", "b", "c")) in _members(groups)
    # ...and not also emitted as the three constituent pairs.
    assert frozenset(("a", "b")) not in _members(groups)


def test_ignores_pairs_with_too_few_shared_opponents():
    """Two bots that have barely played cannot be called identical."""
    rows = [_row("a", "x", 1.0), _row("b", "x", 1.0)]
    assert behaviour_groups(rows) == []


def test_errored_matches_are_excluded():
    rows = _field(
        {("a", "x"): 1.0, ("a", "y"): 1.0, ("a", "z"): 1.0,
         ("b", "x"): 1.0, ("b", "y"): 1.0, ("b", "z"): 1.0}, ["x", "y", "z"]
    )
    rows.append(_row("a", "x", 0.0, status="error"))
    groups = behaviour_groups(rows)
    assert len(groups) == 1  # the errored row must not break the match


def test_score_table_folds_both_orders():
    rows = [_row("a", "b", 1.0), _row("b", "a", 1.0)]
    _, table = score_table(rows)
    assert table[("a", "b")] == (1.0, 2)
    assert table[("b", "a")] == (1.0, 2)


def test_code_groups_detects_identical_python(tmp_path, monkeypatch):
    """Two registry entries pointing at the same tree at the same commit must group."""
    from tournament.gitutil import resolve_commit

    commit = resolve_commit("9713344")
    specs = [
        BotSpec(name="one", commit=commit, path="bots/jon/fair/vanguard"),
        BotSpec(name="two", commit=commit, path="bots/jon/fair/vanguard"),
        BotSpec(name="three", commit=commit, path="bots/jon/legacy/turtle"),
    ]
    groups = code_groups(specs)
    assert len(groups) == 1
    assert set(groups[0].members) == {f"one@{commit[:7]}", f"two@{commit[:7]}"}


def test_code_hash_ignores_non_python_files():
    """An added BOT_VERSION.toml once made all 34 bots look changed; only .py may count."""
    from tournament.duplicates import code_hash
    from tournament.gitutil import resolve_commit

    old = code_hash(resolve_commit("9713344"), "bots/jon/legacy/vg_v1")
    new = code_hash(resolve_commit("origin/x/jon"), "bots/jon/legacy/vg_v1")
    assert old and old == new


def test_render_is_empty_when_nothing_found():
    assert "no duplicate" in render([])


@pytest.mark.parametrize(
    "members",
    [
        ("v233_h@9713344", "vanguard@9713344"),
        ("adaptive_v1@9713344", "siege_v2@9713344"),
        ("frontier@9713344", "frontier_v2@9713344"),
    ],
)
def test_known_duplicate_pairs_in_the_real_tournament(members):
    """Regression: these three pairs were found by hand in the 34-bot run and must stay found.

    Each plays 21/42 head to head -- the signature of two identical deterministic bots, where each
    wins every map as player A -- and matches on all 32 other opponents.
    """
    from pathlib import Path

    from tournament.merge import read

    run = Path(__file__).resolve().parent / "runs" / "jon-full"
    if not (run / "matches.csv").exists():
        pytest.skip("jon-full has not been run in this checkout")
    groups = behaviour_groups(read(run))
    found = {frozenset(g.members) for g in groups}
    assert frozenset(members) in found
