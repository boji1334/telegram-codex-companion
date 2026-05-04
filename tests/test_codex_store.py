import json
import sqlite3
from pathlib import Path

from pocket_codex.codex_store import CodexStore


def test_codex_store_reads_and_appends_rollout_messages(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    rollout_path = codex_home / "sessions" / "rollout.jsonl"
    codex_home.mkdir()
    rollout_path.parent.mkdir()
    rollout_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-05-04T00:00:00.000Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello"}],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    db_path = codex_home / "state_5.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE threads (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              cwd TEXT NOT NULL,
              rollout_path TEXT NOT NULL,
              updated_at INTEGER NOT NULL,
              archived INTEGER NOT NULL,
              updated_at_ms INTEGER
            )
            """
        )
        conn.execute(
            """
            INSERT INTO threads
              (id, title, cwd, rollout_path, updated_at, archived, updated_at_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("thread-1", "Test Thread", str(tmp_path), str(rollout_path), 1, 0, 1000),
        )

    store = CodexStore(codex_home)
    assert store.list_threads_for_path(tmp_path)[0].title == "Test Thread"
    assert store.recent_messages(thread_id="thread-1", limit=10)[0].content == "hello"

    store.append_exchange(thread_id="thread-1", user_text="from phone", assistant_text="reply")
    messages = store.recent_messages(thread_id="thread-1", limit=10)

    assert messages[-2].role == "user"
    assert messages[-2].content == "[Telegram]\nfrom phone"
    assert messages[-1].role == "assistant"
    assert messages[-1].content == "reply"
