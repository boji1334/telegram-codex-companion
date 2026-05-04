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
        messages = self.messages(thread_id=thread_id)
        return messages[-limit:]

    def messages(self, *, thread_id: str, limit: int | None = None) -> list[MessageRecord]:
        thread = self.get_thread(thread_id)
        if thread is None or not thread.rollout_path.exists():
            return []

        messages: list[MessageRecord] = []
        with thread.rollout_path.open("r", encoding="utf-8") as file:
            for line in file:
                record = self._message_from_line(line, thread_id=thread_id)
                if record:
                    messages.append(record)
        return messages[-limit:] if limit is not None else messages

    def append_exchange(self, *, thread_id: str, user_text: str, assistant_text: str) -> None:
        thread = self.get_thread(thread_id)
        if thread is None:
            raise ValueError(f"Unknown Codex thread: {thread_id}")
        if not thread.rollout_path.exists():
            raise FileNotFoundError(thread.rollout_path)

        now = _timestamp()
        records = [
            _message_record(now, "user", f"[Telegram]\n{user_text}", "input_text"),
            _event_message(now, "user_message", f"[Telegram]\n{user_text}"),
            _event_message(now, "agent_message", assistant_text),
            _message_record(now, "assistant", assistant_text, "output_text"),
        ]
        with thread.rollout_path.open("a", encoding="utf-8", newline="\n") as file:
            for record in records:
                file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

        self._touch_thread(thread_id)

    def append_user_note(self, *, thread_id: str, text: str) -> None:
        thread = self.get_thread(thread_id)
        if thread is None:
            raise ValueError(f"Unknown Codex thread: {thread_id}")
        if not thread.rollout_path.exists():
            raise FileNotFoundError(thread.rollout_path)

        now = _timestamp()
        records = [
            _message_record(now, "user", text, "input_text"),
            _event_message(now, "user_message", text),
        ]
        with thread.rollout_path.open("a", encoding="utf-8", newline="\n") as file:
            for record in records:
                file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

        self._touch_thread(thread_id)

    def _touch_thread(self, thread_id: str) -> None:
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

    def backfill_telegram_events(self, *, thread_id: str) -> int:
        thread = self.get_thread(thread_id)
        if thread is None:
            raise ValueError(f"Unknown Codex thread: {thread_id}")
        if not thread.rollout_path.exists():
            raise FileNotFoundError(thread.rollout_path)

        raw_lines = thread.rollout_path.read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in raw_lines if line.strip()]
        patched: list[dict] = []
        inserted = 0
        i = 0

        while i < len(records):
            current = records[i]
            patched.append(current)
            payload = current.get("payload") or {}
            payload_text = _text_from_payload(payload)
            if _is_message(current, "user") and payload_text.startswith("[Telegram]"):
                timestamp = current.get("timestamp") or _timestamp()
                if not _next_is_event(records, i, "user_message"):
                    patched.append(_event_message(timestamp, "user_message", payload_text))
                    inserted += 1

                if i + 1 < len(records):
                    next_record = records[i + 1]
                    next_payload = next_record.get("payload") or {}
                    if _is_message(next_record, "assistant"):
                        assistant_text = _text_from_payload(next_payload)
                        if assistant_text and not _previous_is_event(
                            patched,
                            "agent_message",
                            assistant_text,
                        ):
                            patched.append(
                                _event_message(
                                    next_record.get("timestamp") or timestamp,
                                    "agent_message",
                                    assistant_text,
                                )
                            )
                            inserted += 1
            i += 1

        if inserted:
            backup = thread.rollout_path.with_suffix(thread.rollout_path.suffix + ".bak")
            backup.write_text("\n".join(raw_lines) + "\n", encoding="utf-8")
            thread.rollout_path.write_text(
                "\n".join(
                    json.dumps(record, ensure_ascii=False, separators=(",", ":"))
                    for record in patched
                )
                + "\n",
                encoding="utf-8",
            )
        return inserted

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

    def _message_from_line(self, line: str, *, thread_id: str) -> MessageRecord | None:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return None
        payload = obj.get("payload") or {}

        if obj.get("type") == "response_item" and payload.get("type") == "image_generation_call":
            image_path = self._generated_image_path(thread_id=thread_id, call_id=payload.get("id"))
            if image_path is None:
                return None
            return MessageRecord(
                role="assistant",
                content="生成图片",
                created_at=obj.get("timestamp") or "",
                images=(str(image_path),),
            )

        if obj.get("type") != "response_item" or payload.get("type") != "message":
            return None
        role = payload.get("role")
        if role not in {"user", "assistant"}:
            return None

        parts: list[str] = []
        images: list[str] = []
        for item in payload.get("content") or []:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and not _is_image_marker(text):
                    parts.append(text)
                images.extend(_image_refs_from_item(item))
        text = "\n".join(part for part in parts if part).strip()
        images = _dedupe(images)
        if (not text and not images) or text.startswith("<environment_context>"):
            return None
        return MessageRecord(
            role=role,
            content=text,
            created_at=obj.get("timestamp") or "",
            images=tuple(images),
        )

    def _generated_image_path(self, *, thread_id: str, call_id: object) -> Path | None:
        if not isinstance(call_id, str) or not call_id:
            return None
        image_dir = self.codex_home / "generated_images" / thread_id
        for suffix in (".png", ".jpg", ".jpeg", ".webp"):
            image_path = image_dir / f"{call_id}{suffix}"
            if image_path.exists():
                return image_path
        return next(image_dir.glob(f"{call_id}.*"), None) if image_dir.exists() else None


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
    payload = {
        "type": "message",
        "role": role,
        "content": [{"type": content_type, "text": text}],
    }
    if role == "assistant":
        payload["phase"] = "final_answer"
    return {
        "timestamp": timestamp,
        "type": "response_item",
        "payload": payload,
    }


def _event_message(timestamp: str, event_type: str, text: str) -> dict:
    if event_type == "user_message":
        payload = {
            "type": "user_message",
            "message": text,
            "images": [],
            "local_images": [],
            "text_elements": [],
        }
    elif event_type == "agent_message":
        payload = {
            "type": "agent_message",
            "message": text,
            "phase": "final_answer",
            "memory_citation": None,
        }
    else:
        raise ValueError(f"Unsupported event type: {event_type}")
    return {
        "timestamp": timestamp,
        "type": "event_msg",
        "payload": payload,
    }


def _is_message(record: dict, role: str) -> bool:
    payload = record.get("payload") or {}
    return (
        record.get("type") == "response_item"
        and payload.get("type") == "message"
        and payload.get("role") == role
    )


def _text_from_payload(payload: dict) -> str:
    parts: list[str] = []
    for item in payload.get("content") or []:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts)


def _image_refs_from_item(item: dict) -> list[str]:
    refs: list[str] = []
    for key in ("image_url", "path", "local_path", "file_path"):
        value = item.get(key)
        if isinstance(value, str) and value:
            refs.append(value)
    return refs


def _is_image_marker(text: str) -> bool:
    marker = text.strip()
    return marker == "</image>" or (
        marker.startswith("<image") and marker.endswith(">") and "\n" not in marker
    )


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _next_is_event(records: list[dict], index: int, event_type: str) -> bool:
    if index + 1 >= len(records):
        return False
    payload = records[index + 1].get("payload") or {}
    return records[index + 1].get("type") == "event_msg" and payload.get("type") == event_type


def _previous_is_event(records: list[dict], event_type: str, text: str) -> bool:
    if not records:
        return False
    payload = records[-1].get("payload") or {}
    return (
        records[-1].get("type") == "event_msg"
        and payload.get("type") == event_type
        and payload.get("message") == text
    )
