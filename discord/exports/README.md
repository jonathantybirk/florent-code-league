# Discord export drop directory

Put DiscordChatExporter JSON exports here. Anything matching `*.json`, at any
depth, is picked up by the next `ingest`; nothing else in this directory is
read, and no file here is ever modified or moved.

    dotnet tool install -g DiscordChatExporter.Cli    # once

    discordchatexporter export \
        --token "$DISCORD_TOKEN" \
        --channel <channel-id> \
        --format Json \
        --output discord/exports/

`$DISCORD_TOKEN` can be a **bot** token (the bot must be in the server with Read
Message History) or your own **user** token. The user-token route needs no
admin cooperation, but automating a user account is against Discord's terms of
service and is the usual cause of account termination — the same exposure a
self-bot carries. The bot-token route does not have that problem.

Re-exporting the same channel with a wider date range is the intended way to
keep the archive current. Overlap is free: files are identified by content
hash, so an unchanged file is skipped outright, and messages are deduplicated
on their Discord snowflake, so the messages you already have collapse onto the
rows already stored. Only genuinely new messages and genuine edits land.

Discord's own "Request my Data" package is detected and rejected rather than
half-parsed — it contains only your own messages, so ingesting it would produce
an archive that looks populated but holds none of the discussion.

The exports are gitignored. They are other people's messages, verbatim and
attributed, and they should not travel with the repository.
