# Discord archive

Turns Florent Code League Discord chat into a live feed of game-relevant
threads on the site, in three layers. Each is rebuildable from the one below,
which is what makes it safe to change the prompt or the feed shape later and
re-run over history already on disk.

    discord/exports/*.json     DiscordChatExporter output, dropped in by hand
      --> ingest               lossless SQLite archive, deduped on snowflake
      --> extract              Claude reads unseen messages into topic threads
      --> publish              feed.json for the site's live feed page

The archive is lossless on purpose: every message keeps its original JSON, so
a question the extractor was never prompted for can still be answered later
without paying for a single token. Filtering is a query-time decision, never an
ingest-time one.

## Running it

    uv run python -m tools.discord_archive poll        # all three, in order

`poll` is what the timer runs. Every stage is a no-op when its input has not
moved: no new files means no ingest, nothing past the watermark means no API
call, and an unchanged feed writes no bytes and triggers no deploy.

Individual stages, when you want them:

    uv run python -m tools.discord_archive ingest -v
    uv run python -m tools.discord_archive extract --dry-run -v   # prompts, no calls
    uv run python -m tools.discord_archive extract
    uv run python -m tools.discord_archive publish
    uv run python -m tools.discord_archive stats

## Searching the raw archive

Independent of what the model made of it:

    uv run python -m tools.discord_archive query --preset game --since 2026-07-01
    uv run python -m tools.discord_archive query --preset rules --pinned
    uv run python -m tools.discord_archive query --author viktor --no-bots
    uv run python -m tools.discord_archive query --contains 'conveyor NEAR turret' --jsonl

Presets live in `filters.py` and are built from the vocabulary in
`docs/official/`, so they match the words the game actually uses. `--contains`
takes a raw FTS5 expression when a preset is too blunt.

## How extraction decides what to send

A per-channel watermark records the newest message already handed to the model,
and each run reads strictly past it — so unseen messages are the only ones that
ever cost anything.

Unseen is not the same as understandable, though. A message arriving mid-argument
means nothing without the argument, so every batch is prefixed with the last
`--context` messages (default 30) before the watermark, marked read-only: the
model may read them for sense but may not file them as new activity. Without
that rule the same messages would be re-attributed on every run.

Threads outlive batches. Open threads from recent runs are passed in, and the
model may continue one by id rather than opening a near-duplicate — which is
what makes a discussion spanning Tuesday and Thursday read as one conversation.

## Cost control

`stats` reports cumulative `tokens_in` / `tokens_out` from the `extract_runs`
table, which logs every call including failures. The system prompt is cached,
so back-to-back batches pay ~0.1x for it rather than full price.

`--effort` (default `high`) is the main lever; `--batch` sets how many new
messages go in one call. `--dry-run` builds the prompts and sends nothing,
which is the cheap way to check what a run would cost before making it.

## Publishing

`publish` writes `feed.json` into the site repo's `public/discord/data/`, which
the page at `src/pages/discord/index.astro` fetches at runtime and re-polls
every 60s. `generated_at` is excluded from the change comparison, so a poll that
finds nothing does not rewrite the file — otherwise every two minutes would look
like new content and deploy the site for nothing.

`--deploy` commits, pushes and ships the site, mirroring what
`tournament/automation.py` already does for the ladder. It stages only the feed
path, so a concurrent edit elsewhere in the site repo is neither committed nor
lost. **It publishes other people's Discord messages to the public web** — that
is the point of the feature, but it is worth knowing which flag does it.

## Files

| File | What it holds |
| --- | --- |
| `db.py` | Schema and upserts. Archive tables above, derived tables below. |
| `ingest.py` | Export parsing, content-hash skip, snowflake dedup. |
| `extract.py` | Watermarks, context overlap, the prompt, the Claude call. |
| `publish.py` | Feed bundle, change detection, site deploy. |
| `query.py` | Ad-hoc search and `stats`. |
| `filters.py` | Relevance presets, applied at query time only. |
