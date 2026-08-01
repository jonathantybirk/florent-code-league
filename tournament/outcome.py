"""Interpret engine outcomes consistently throughout the evaluation pipeline.

The engine always names a winner, but ``win_condition=coinflip`` means every gameplay
tiebreaker was equal and the final choice was random.  Evaluation treats that outcome as a draw
while retaining the engine's chosen winner separately for auditability.
"""

from __future__ import annotations

ENGINE_SCORE = {"a": 1.0, "b": 0.0, "draw": 0.5}
DRAW_CONDITIONS = frozenset({"coinflip"})


def normalize(winner: object, win_condition: object = "") -> tuple[str, float]:
    """Return the semantic winner and bot-A score for an engine result."""
    engine_winner = str(winner).lower()
    condition = str(win_condition).lower()
    if condition in DRAW_CONDITIONS:
        return "draw", 0.5
    if engine_winner not in ENGINE_SCORE:
        raise ValueError(f"unexpected winner value from engine: {winner!r}")
    return engine_winner, ENGINE_SCORE[engine_winner]


def score_a(row: dict) -> float:
    """Return bot A's semantic score, correcting historical coinflip rows on read."""
    if str(row.get("win_condition", "")).lower() in DRAW_CONDITIONS:
        return 0.5
    return float(row["score_a"])
