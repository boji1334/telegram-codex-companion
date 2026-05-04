import json
import sqlite3
from pathlib import Path

from pocket_codex.codex_store import CodexStore

IMAGE_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


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

    records = [
        json.loads(line)
        for line in rollout_path.read_text(encoding="utf-8").splitlines()
    ]
    event_types = [
        record["payload"]["type"]
        for record in records
        if record["type"] == "event_msg"
    ]
    assert "user_message" in event_types
    assert "agent_message" in event_types
    assert records[-2]["payload"]["phase"] == "final_answer"
    assert records[-1]["payload"]["phase"] == "final_answer"


def test_codex_store_backfills_existing_telegram_records(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    rollout_path = codex_home / "sessions" / "rollout.jsonl"
    codex_home.mkdir()
    rollout_path.parent.mkdir()
    rollout_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-05-04T00:00:00.000Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "[Telegram]\nhello"}],
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-05-04T00:00:01.000Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "hi"}],
                        },
                    }
                ),
            ]
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

    inserted = CodexStore(codex_home).backfill_telegram_events(thread_id="thread-1")
    records = [
        json.loads(line)
        for line in rollout_path.read_text(encoding="utf-8").splitlines()
    ]

    assert inserted == 2
    assert records[1]["payload"]["type"] == "user_message"
    assert records[2]["payload"]["type"] == "agent_message"
    assert records[3]["payload"]["role"] == "assistant"


def test_codex_store_reads_user_images_from_rollout(tmp_path: Path) -> None:
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
                    "content": [
                        {"type": "input_text", "text": "look at this"},
                        {"type": "input_text", "text": "<image>"},
                        {"type": "input_image", "image_url": IMAGE_DATA_URL},
                        {"type": "input_text", "text": "</image>"},
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _create_thread_db(codex_home, rollout_path, tmp_path)

    messages = CodexStore(codex_home).messages(thread_id="thread-1")

    assert messages[0].content == "look at this"
    assert messages[0].images == (IMAGE_DATA_URL,)


def test_codex_store_reads_generated_images_from_rollout(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    rollout_path = codex_home / "sessions" / "rollout.jsonl"
    image_path = codex_home / "generated_images" / "thread-1" / "ig_test.png"
    codex_home.mkdir()
    rollout_path.parent.mkdir()
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"fake png")
    rollout_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-05-04T00:00:00.000Z",
                "type": "response_item",
                "payload": {
                    "type": "image_generation_call",
                    "id": "ig_test",
                    "status": "completed",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _create_thread_db(codex_home, rollout_path, tmp_path)

    messages = CodexStore(codex_home).messages(thread_id="thread-1")

    assert messages[0].role == "assistant"
    assert messages[0].content == "生成图片"
    assert messages[0].images == (str(image_path),)


def _create_thread_db(codex_home: Path, rollout_path: Path, cwd: Path) -> None:
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
            ("thread-1", "Test Thread", str(cwd), str(rollout_path), 1, 0, 1000),
        )
