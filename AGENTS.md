# AGENTS.md

Every LLM-generated `.md` file goes in `llm-slop-analysis/`.

The only exceptions are this file and `README.md`.

Every runnable bot or preserved bot version must contain a `BOT_VERSION.toml`.
Its `source_commit` must be the full 40-character Git commit whose Python
source that directory represents, and `source_path` must name the bot directory
at that commit. Commit source changes first, then update the metadata in a
follow-up commit; a commit cannot truthfully contain its own hash. Historical
snapshots belong under `bots/<author>/versions/`, while bots that target an
incompatible engine belong under `bots/<author>/legacy/`.
