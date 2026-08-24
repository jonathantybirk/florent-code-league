"""Archive, extract and publish game-relevant Discord discussion.

Three layers, each rebuildable from the one below it:

    discord/exports/*.json   DiscordChatExporter output, dropped in by hand
      -> ingest              lossless SQLite archive, deduped on snowflake
      -> extract             Claude reads unseen messages into topic threads
      -> publish             feed.json for the site's live feed page

See README.md in this directory for the operating instructions.
"""
