from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .repository import MessageRecord


@dataclass(frozen=True)
class CodexThread:
    id: str
    title: str
    cwd: str
    rollout_path: Path
    updated_at: int
    archived: bool


class CodexStore:
    def __init__(self, codex_home: Path):
        self.codex_home = codex_home
        self.state_db = codex_home / "state_5.sqlite"

    def available(self) -> bool:
        return self.state_db.exists()

    def list_threads_for_path(
        self,
        project_path: Path | None,
        *,
        limit: int = 20,
    ) -> list[CodexThread]:
        if not self.available():
            return []

        threads = self._list_threads(limit=200)
        if project_path is None:
            return threads[:limit]

        target = _norm_path(project_path)
        matched = [thread for thread in threads if _norm_path(Path(thread.cwd)) == target]
        return matched[:limit]

    def get_thread(self, thread_id: str) -> CodexThread | None:
        if not self.available():
            return None
        with sqlite3.connect(f"file:{self.state_db}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT id, title, cwd, rollout_path, updated_at, archived
                FROM threads
                WHERE id = ?
                """,
                (thread_id,),
            ).fetchone()
        return _thread_from_row(row) if row else None

    def recent_messages(self, *, thread_id: str, limit: int) -> list[MessageRecord]:
        thread = self.get_thread(thread_id)
        if thread is None or not thread.rollout_path.exists():
            return []

        messages: list[MessageRecord] = []
        with thread.rollout_path.open("r", encoding="utf-8") as file:
            for line in file:
                record = self._message_from_line(line)
                if record:
                    messages.append(record)
        return messages[-limit:]

    def append_exchange(self, *, thread_id: str, user_text: str, assistant_text: str) -> None:
        thread = self.get_thread(thread_id)
        if thread is None:
            raise ValueError(f"Unknown Codex thread: {thread_id}")
        if not thread.rollout_path.exists():
            raise FileNotFoundError(thread.rollout_path)

        now = _timestamp()
        records = [
            _message_record(now, "user", f"[Telegram]\n{user_text}", "input_text"),
            _message_record(now, "assistant", assistant_text, "output_text"),
        ]
        with thread.rollout_path.open("a", encoding="utf-8", newline="\n") as file:
            for record in records:
                file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

        unix_seconds = int(datetime.now(UTC).timestamp())
        unix_ms = int(datetime.now(UTC).timestamp() * 1000)
        with sqlite3.connect(self.state_db) as conn:
            conn.execute(
                """
                UPDATE threads
                SET updated_at = ?, updated_at_ms = ?
                WHERE id = ?
                """,
                (unix_seconds, unix_ms, thread_id),
            )

    def _list_threads(self, *, limit: int) -> list[CodexThread]:
        with sqlite3.connect(f"file:{self.state_db}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, title, cwd, rollout_path, updated_at, archived
                FROM threads
                WHERE archived = 0
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_thread_from_row(row) for row in rows]

    @staticmethod
    def _message_from_line(line: str) -> MessageRecord | None:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return None
        payload = obj.get("payload") or {}
        if obj.get("type") != "response_item" or payload.get("type") != "message":
            return None
        role = payload.get("role")
        if role not in {"user", "assistant"}:
            return None

        parts: list[str] = []
        for item in payload.get("content") or []:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        text = "\n".join(part for part in parts if part).strip()
        if not text or text.startswith("<environment_context>"):
            return None
        return MessageRecord(
            role=role,
            content=text,
            created_at=obj.get("timestamp") or "",
        )


def _thread_from_row(row: sqlite3.Row) -> CodexThread:
    return CodexThread(
        id=row["id"],
        title=row["title"],
        cwd=_strip_unc_prefix(row["cwd"]),
        rollout_path=Path(_strip_unc_prefix(row["rollout_path"])),
        updated_at=row["updated_at"],
        archived=bool(row["archived"]),
    )


def _strip_unc_prefix(path: str) -> str:
    return path[4:] if path.startswith("\\\\?\\") else path


def _norm_path(path: Path) -> str:
    return str(path.expanduser().resolve()).casefold().replace("/", "\\")


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _message_record(timestamp: str, role: str, text: str, content_type: str) -> dict:
    return {
        "timestamp": timestamp,
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": role,
            "content": [{"type": content_type, "text": text}],
        },
    }
