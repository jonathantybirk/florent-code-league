# docs — original sources only

This directory holds **verbatim captured source material and nothing else**. No
summaries, no reformatting, no LLM commentary. Anything a model wrote belongs in
[`llm-slop-analysis/`](../llm-slop-analysis/), never here — otherwise the next
model cannot tell a guess from a source, and one pass's guess becomes the next
pass's "documentation".

## What is here

- [`scraped-originals/game.code.florent.vc/docs/`](scraped-originals/game.code.florent.vc/docs/)
  — raw text of every official documentation page.
- [`scraped-originals/game.code.florent.vc/tutorials/`](scraped-originals/game.code.florent.vc/tutorials/)
  — raw text of all five tutorial modules (24 lessons).

A previous pass also kept a reformatted-and-annotated Markdown mirror of these
pages. It has been removed: it was a second, drifting copy of material we
already have verbatim, and its annotations were LLM-authored claims sitting in a
directory that reads as authoritative. The reverse-engineered file-format notes
and the rendered map atlas moved to
[`llm-slop-analysis/jon/reference/`](../llm-slop-analysis/jon/reference/) for the
same reason.

## Source ranking

When two of these disagree, trust them in this order:

1. **The running engine** (`fcode 2.2.0`) — probe it.
2. **`.venv/lib/python3.13/site-packages/fcode/data/docs/spec.md`** — the spec
   shipped inside the engine wheel, and `_types.py` beside it.
3. **`scraped-originals/`** — the official site.

The official tutorials are known to be wrong about builder timing: they state
that a build consumes the round's move, that builders cannot build on their own
tile or diagonally, and they move only on cardinals. All three are false in
2.2.0. See
[`llm-slop-analysis/jon/meta/mechanics-audit.md`](../llm-slop-analysis/jon/meta/mechanics-audit.md).

Verify timing-sensitive behaviour with a probe bot before trusting prose.
