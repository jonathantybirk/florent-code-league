"""Turn unseen archived messages into game-relevant threads, using Claude.

Three properties drive the design.

*Only unseen messages cost money.* A per-channel watermark records the newest
message already handed to the model. Each run reads strictly past it, so a poll
that finds nothing new makes no API call at all.

*Unseen is not the same as understandable.* A message arriving mid-argument
means nothing without the argument, so every batch is prefixed with the last
`--context` messages before the watermark, marked as read-only. The model may
read them for sense but may not file them as new activity -- without that rule
the same messages would be re-attributed on every run.

*Threads outlive batches.* A discussion that starts on Tuesday and resumes on
Thursday is one thread, so the open threads from recent runs are passed in and
the model may continue one by id instead of opening a near-duplicate. This is
what makes the feed read as conversations rather than as a message list.

The archive itself is never modified here. Everything this module writes lives
in the derived tables and can be dropped and rebuilt.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import anthropic

MODEL = "claude-opus-5"

TOPICS = [
    "rules-and-patches",
    "results-and-ladder",
    "strategy-and-meta",
    "tooling-and-api",
    "opponent-intel",
    "logistics-and-deadlines",
]

SYSTEM = """\
You read chat from the Discord server of the Florent Code League, a programming \
competition in which entrants write Python bots that harvest titanium, build \
conveyors and turrets, and fight on a live leaderboard.

Your job is to find the threads of conversation that bear on actually competing, \
and to ignore everything else. A thread is a run of messages about one subject: \
it may be a handful of messages or a long argument, it may be interleaved with \
unrelated chatter, and it does not have to be contiguous.

Report a thread when it carries something a competitor would act on:

- rules-and-patches: rule or engine changes, version bumps, breaking changes,
  costs or limits being altered, bugs in the game itself.
- results-and-ladder: match results, standings, rating changes, replays being
  discussed, tournament structure and seeding.
- strategy-and-meta: openings, build orders, unit compositions, counters, map
  reading -- anything about how to play well.
- tooling-and-api: the CLI, the API surface, local testing, submission
  mechanics, performance and CPU limits.
- opponent-intel: what a specific bot or entrant does, and how it behaves.
- logistics-and-deadlines: submission windows, deadlines, event scheduling,
  eligibility.

Ignore greetings, jokes, off-topic chat, reaction-only exchanges, and anything \
about the competition as a social event rather than as a game to be played. When \
a thread is a mix, report it and describe only the part that matters.

Rules you must follow:

- Only messages in the NEW MESSAGES section may appear in message_ids. The
  CONTEXT section exists so that a reply lands in its argument; never file a
  context message as new activity.
- If new messages continue a thread listed under OPEN THREADS, set
  continues_thread_id to that thread's id and list only the new message ids.
  Otherwise leave continues_thread_id empty.
- title is a specific noun phrase, not a category: "harvester cost cut to 8Ti",
  not "game balance".
- summary states what was actually said and by whom where it matters, in two or
  three sentences.
- relevance states, in one sentence, what a competitor should do or know as a
  result. If the honest answer is that nothing follows yet, say so.
- If nothing in the new messages is game-relevant, return an empty list. That is
  a normal and frequent outcome -- do not invent a thread to fill the space.\
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "threads": {
            "type": "array",
            "description": "Game-relevant threads found in the new messages.",
            "items": {
                "type": "object",
                "properties": {
                    "continues_thread_id": {
                        "type": "string",
                        "description": "Id of an open thread this continues, or empty for a new thread.",
                    },
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "topic": {"type": "string", "enum": TOPICS},
                    "relevance": {"type": "string"},
                    "message_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ids of NEW messages belonging to this thread.",
                    },
                },
                "required": [
                    "continues_thread_id",
                    "title",
                    "summary",
                    "topic",
                    "relevance",
                    "message_ids",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["threads"],
    "additionalProperties": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _thread_id(channel_id: str, title: str, first_message: str) -> str:
    seed = f"{channel_id}:{first_message}:{title}".encode("utf-8")
    return "t_" + hashlib.sha256(seed).hexdigest()[:16]


def channels_with_backlog(conn) -> list[str]:
    """Channels holding at least one message past their watermark."""
    rows = conn.execute(
        "SELECT DISTINCT m.channel_id FROM messages m "
        "LEFT JOIN watermarks w ON w.channel_id = m.channel_id "
        "WHERE w.timestamp IS NULL OR m.timestamp > w.timestamp"
    ).fetchall()
    return [row["channel_id"] for row in rows]


def _watermark(conn, channel_id: str) -> str | None:
    row = conn.execute(
        "SELECT timestamp FROM watermarks WHERE channel_id = ?", (channel_id,)
    ).fetchone()
    return row["timestamp"] if row else None


def new_messages(conn, channel_id: str, watermark: str | None, limit: int) -> list:
    if watermark is None:
        return conn.execute(
            "SELECT * FROM messages WHERE channel_id = ? "
            "ORDER BY timestamp, id LIMIT ?",
            (channel_id, limit),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM messages WHERE channel_id = ? AND timestamp > ? "
        "ORDER BY timestamp, id LIMIT ?",
        (channel_id, watermark, limit),
    ).fetchall()


def context_messages(conn, channel_id: str, watermark: str | None, count: int) -> list:
    """The `count` messages immediately before the watermark, oldest first."""
    if watermark is None or count <= 0:
        return []
    rows = conn.execute(
        "SELECT * FROM messages WHERE channel_id = ? AND timestamp <= ? "
        "ORDER BY timestamp DESC, id DESC LIMIT ?",
        (channel_id, watermark, count),
    ).fetchall()
    return list(reversed(rows))


def open_threads(conn, channel_id: str, limit: int = 25) -> list:
    return conn.execute(
        "SELECT id, title, summary, topic, last_activity_at FROM threads "
        "WHERE channel_id = ? ORDER BY last_activity_at DESC LIMIT ?",
        (channel_id, limit),
    ).fetchall()


def _author(row) -> str:
    return row["author_nick"] or row["author_name"] or row["author_id"] or "unknown"


def render(rows) -> str:
    lines = []
    for row in rows:
        stamp = (row["timestamp"] or "")[:19].replace("T", " ")
        reply = f" (reply to {row['reply_to']})" if row["reply_to"] else ""
        pinned = " [pinned]" if row["is_pinned"] else ""
        content = row["content"] or ""
        attachments = json.loads(row["attachments"] or "[]")
        if attachments and not content:
            content = f"<{len(attachments)} attachment(s), no text>"
        elif attachments:
            content += f" <+{len(attachments)} attachment(s)>"
        lines.append(f"[{row['id']}] {stamp} {_author(row)}{reply}{pinned}: {content}")
    return "\n".join(lines)


def build_prompt(channel_name: str, context: list, new: list, threads: list) -> str:
    parts = [f"Channel: #{channel_name}"]

    if threads:
        parts.append(
            "\nOPEN THREADS (continue one by id if the new messages carry it forward):"
        )
        for thread in threads:
            parts.append(
                f"- {thread['id']} [{thread['topic']}] {thread['title']}\n"
                f"    {thread['summary']}"
            )

    if context:
        parts.append(
            "\nCONTEXT (already processed -- read for sense, never cite as new):\n"
            + render(context)
        )

    parts.append("\nNEW MESSAGES (only these may appear in message_ids):\n" + render(new))
    return "\n".join(parts)


def _client() -> anthropic.Anthropic:
    # An unset ANTHROPIC_API_KEY is fine -- the SDK also resolves an `ant auth
    # login` profile. Constructing bare lets whichever is configured win.
    return anthropic.Anthropic()


def call_model(client, prompt: str, effort: str = "high") -> tuple[dict, object]:
    """Ask Claude for the threads in one batch. Returns (parsed, usage)."""
    with client.messages.stream(
        model=MODEL,
        max_tokens=32000,
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        thinking={"type": "adaptive"},
        output_config={
            "effort": effort,
            "format": {"type": "json_schema", "schema": SCHEMA},
        },
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise RuntimeError("model declined to process this batch")

    text = next((b.text for b in message.content if b.type == "text"), "")
    if not text.strip():
        raise RuntimeError(f"empty response (stop_reason={message.stop_reason})")
    return json.loads(text), message.usage


def store(conn, channel_id: str, found: list[dict], by_id: dict) -> int:
    """Write threads and their memberships. Returns the number touched."""
    touched = 0
    for thread in found:
        ids = [str(m) for m in thread.get("message_ids") or [] if str(m) in by_id]
        if not ids:
            continue

        stamps = sorted(by_id[m]["timestamp"] for m in ids)
        existing = thread.get("continues_thread_id") or ""
        row = (
            conn.execute("SELECT * FROM threads WHERE id = ?", (existing,)).fetchone()
            if existing
            else None
        )

        if row is None:
            thread_id = _thread_id(channel_id, thread["title"], ids[0])
            conn.execute(
                "INSERT INTO threads (id, channel_id, title, summary, topic, relevance,"
                " started_at, last_activity_at, created_at, updated_at, model) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "  summary=excluded.summary, relevance=excluded.relevance,"
                "  last_activity_at=MAX(threads.last_activity_at, excluded.last_activity_at),"
                "  updated_at=excluded.updated_at",
                (
                    thread_id,
                    channel_id,
                    thread["title"],
                    thread.get("summary", ""),
                    thread.get("topic", "other"),
                    thread.get("relevance", ""),
                    stamps[0],
                    stamps[-1],
                    _now(),
                    _now(),
                    MODEL,
                ),
            )
        else:
            thread_id = row["id"]
            conn.execute(
                "UPDATE threads SET title=?, summary=?, topic=?, relevance=?,"
                " started_at=MIN(started_at, ?), last_activity_at=MAX(last_activity_at, ?),"
                " updated_at=?, model=? WHERE id=?",
                (
                    thread["title"],
                    thread.get("summary", ""),
                    thread.get("topic", row["topic"]),
                    thread.get("relevance", ""),
                    stamps[0],
                    stamps[-1],
                    _now(),
                    MODEL,
                    thread_id,
                ),
            )

        conn.executemany(
            "INSERT INTO thread_messages (thread_id, message_id) VALUES (?, ?) "
            "ON CONFLICT DO NOTHING",
            [(thread_id, m) for m in ids],
        )
        touched += 1
    return touched


def set_watermark(conn, channel_id: str, timestamp: str, message_id: str) -> None:
    conn.execute(
        "INSERT INTO watermarks (channel_id, timestamp, message_id, updated_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(channel_id) DO UPDATE SET "
        "  timestamp=excluded.timestamp, message_id=excluded.message_id,"
        "  updated_at=excluded.updated_at",
        (channel_id, timestamp, message_id, _now()),
    )


def extract_channel(
    conn,
    client,
    channel_id: str,
    *,
    batch: int = 250,
    context: int = 30,
    effort: str = "high",
    dry_run: bool = False,
) -> dict:
    """Process one channel's backlog, one batch per call, until it is clear."""
    channel = conn.execute(
        "SELECT name FROM channels WHERE id = ?", (channel_id,)
    ).fetchone()
    name = (channel["name"] if channel else None) or channel_id

    summary = {"channel": name, "batches": 0, "messages": 0, "threads": 0}

    while True:
        mark = _watermark(conn, channel_id)
        new = new_messages(conn, channel_id, mark, batch)
        if not new:
            break

        prior = context_messages(conn, channel_id, mark, context)
        prompt = build_prompt(name, prior, new, open_threads(conn, channel_id))

        if dry_run:
            summary["batches"] += 1
            summary["messages"] += len(new)
            summary["prompt_preview"] = prompt[:2000]
            break

        started = _now()
        try:
            parsed, usage = call_model(client, prompt, effort=effort)
        except Exception as exc:
            conn.execute(
                "INSERT INTO extract_runs (channel_id, started_at, finished_at,"
                " from_ts, to_ts, new_messages, context_messages, model, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    channel_id, started, _now(), new[0]["timestamp"],
                    new[-1]["timestamp"], len(new), len(prior), MODEL, str(exc),
                ),
            )
            conn.commit()
            raise

        by_id = {row["id"]: row for row in new}
        touched = store(conn, channel_id, parsed.get("threads") or [], by_id)
        set_watermark(conn, channel_id, new[-1]["timestamp"], new[-1]["id"])

        conn.execute(
            "INSERT INTO extract_runs (channel_id, started_at, finished_at, from_ts,"
            " to_ts, new_messages, context_messages, threads_touched, input_tokens,"
            " output_tokens, cache_read_tokens, model) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                channel_id, started, _now(), new[0]["timestamp"], new[-1]["timestamp"],
                len(new), len(prior), touched, usage.input_tokens, usage.output_tokens,
                getattr(usage, "cache_read_input_tokens", None), MODEL,
            ),
        )
        conn.commit()

        summary["batches"] += 1
        summary["messages"] += len(new)
        summary["threads"] += touched

        if len(new) < batch:
            break

    return summary


def extract_all(conn, **kwargs) -> list[dict]:
    pending = channels_with_backlog(conn)
    if not pending:
        return []
    client = None if kwargs.get("dry_run") else _client()
    return [extract_channel(conn, client, cid, **kwargs) for cid in pending]
