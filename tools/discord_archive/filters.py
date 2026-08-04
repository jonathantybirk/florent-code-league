"""Relevance presets, applied at query time rather than at ingest.

Keeping these out of the ingest path is the whole point of archiving raw: a
preset that turns out to miss a topic can be widened and re-run over history
already on disk, instead of over a channel that has since scrolled past the
exporter's reach.

The vocabulary below is drawn from `docs/official/`, not invented -- the unit,
building and API names are the ones the game itself uses, so a message
discussing them is almost always about play rather than small talk.
"""

from __future__ import annotations

# Entities, resources and mechanics. Matched case-insensitively as whole words.
GAME_NOUNS = [
    "titanium", "ti", "ammo", "core", "harvester", "conveyor", "splitter",
    "barrier", "builder bot", "builderbot", "gunner", "launcher", "sentinel",
    "turret", "vision radius", "action radius", "spawn radius", "cooldown",
    "self_destruct", "global comms", "global_comms", "comms", "line of sight",
    "los", "tile", "map26", "fcode",
]

# Anything that changes what a correct bot does, or how it is scored.
RULE_TERMS = [
    "patch", "hotfix", "changelog", "rule change", "rules change", "balance",
    "nerf", "buff", "breaking change", "new version", "release", "deprecat",
    "cpu limit", "time limit", "timeout", "disqualif", "dq", "banned",
    "submission", "submit", "deadline", "final", "bracket", "seed",
]

# Competitive signal: results, standings, and who beat whom.
LADDER_TERMS = [
    "leaderboard", "ladder", "rating", "elo", "rank", "standings", "match",
    "replay", "win rate", "winrate", "head-to-head", "tournament", "scrim",
]

# Strategy talk worth reading even when it names nothing concrete.
STRATEGY_TERMS = [
    "opening", "rush", "eco", "economy", "build order", "meta", "strategy",
    "counter", "defen", "aggress", "expansion", "wall", "scout", "micro",
]

PRESETS: dict[str, list[str]] = {
    "game": GAME_NOUNS + RULE_TERMS + LADDER_TERMS + STRATEGY_TERMS,
    "nouns": GAME_NOUNS,
    "rules": RULE_TERMS,
    "ladder": LADDER_TERMS,
    "strategy": STRATEGY_TERMS,
}

# Terms written as prefixes, meant to catch a family: "defen" for defend and
# defense, "deprecat" for deprecated and deprecation.
_STEMS = {"defen", "aggress", "deprecat", "disqualif"}


def fts_query(preset: str) -> str:
    """Render a preset as an FTS5 MATCH expression.

    Anything that is not a bare alphanumeric word is quoted as a phrase. That
    covers spaces, but also hyphens and underscores: FTS5 tokenises on those
    too, so an unquoted `head-to-head` parses as the expression `head` AND `to`
    AND `head` -- and `to` is then read as a column name, which is a syntax
    error rather than a miss. Quoting turns the whole thing back into a phrase
    match on the tokens.

    Stems become prefix matches. FTS5 matches whole tokens, so short terms like
    "ti" and "dq" cannot match inside a longer word.
    """
    parts = []
    for term in PRESETS[preset]:
        cleaned = term.replace('"', "").strip()
        if not cleaned:
            continue
        if cleaned in _STEMS:
            parts.append(f"{cleaned}*")
        elif cleaned.isalnum():
            parts.append(cleaned)
        else:
            parts.append(f'"{cleaned}"')
    return " OR ".join(dict.fromkeys(parts))


def available() -> list[str]:
    return sorted(PRESETS)
