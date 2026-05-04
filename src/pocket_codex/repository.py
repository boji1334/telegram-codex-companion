from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import ProjectConfig


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class SessionRecord:
    id: str
    project_id: str
    title: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class MessageRecord:
    role: str
    content: str
    created_at: str


@dataclass(frozen=True)
class CurrentState:
    project_id: str
    session_id: str


class Repository:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def migrate(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                  user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  display_name TEXT,
                  role TEXT NOT NULL DEFAULT 'admin',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS projects (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  path TEXT,
                  system_prompt TEXT NOT NULL DEFAULT '',
                  enabled INTEGER NOT NULL DEFAULT 1,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                  id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL REFERENCES projects(id),
                  title TEXT NOT NULL,
                  created_by INTEGER NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                  role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                  content TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_state (
                  user_id INTEGER PRIMARY KEY,
                  current_project_id TEXT NOT NULL REFERENCES projects(id),
                  current_session_id TEXT NOT NULL REFERENCES sessions(id),
                  updated_at TEXT NOT NULL
                );
                """
            )

    def sync_projects(self, projects: Iterable[ProjectConfig]) -> None:
        now = utc_now()
        with self.connect() as conn:
            for project in projects:
                conn.execute(
                    """
                    INSERT INTO projects (id, name, path, system_prompt, enabled, updated_at)
                    VALUES (?, ?, ?, ?, 1, ?)
                    ON CONFLICT(id) DO UPDATE SET
                      name = excluded.name,
                      path = excluded.path,
                      system_prompt = excluded.system_prompt,
                      enabled = 1,
                      updated_at = excluded.updated_at
                    """,
                    (
                        project.id,
                        project.name,
                        str(project.path) if project.path else None,
                        project.system_prompt,
                        now,
                    ),
                )

    def add_or_update_user(
        self,
        *,
        user_id: int,
        username: str | None,
        display_name: str | None,
        role: str = "admin",
    ) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (user_id, username, display_name, role, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  username = excluded.username,
                  display_name = excluded.display_name,
                  role = excluded.role,
                  updated_at = excluded.updated_at
                """,
                (user_id, username, display_name, role, now, now),
            )

    def has_user(self, user_id: int) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return row is not None

    def list_projects(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, path, system_prompt
                FROM projects
                WHERE enabled = 1
                ORDER BY CASE WHEN id = 'general' THEN 0 ELSE 1 END, name COLLATE NOCASE
                """
            ).fetchall()
        return list(rows)

    def get_project(self, project_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, name, path, system_prompt FROM projects WHERE id = ? AND enabled = 1",
                (project_id,),
            ).fetchone()
        return row

    def ensure_state(self, user_id: int) -> CurrentState:
        with self.connect() as conn:
            state = conn.execute(
                "SELECT current_project_id, current_session_id FROM user_state WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if state:
                return CurrentState(
                    project_id=state["current_project_id"],
                    session_id=state["current_session_id"],
                )

            project = conn.execute(
                """
                SELECT id
                FROM projects
                WHERE enabled = 1
                ORDER BY CASE WHEN id = 'general' THEN 0 ELSE 1 END, name COLLATE NOCASE
                LIMIT 1
                """
            ).fetchone()
            if project is None:
                raise RuntimeError("No enabled projects are configured.")

            session_id = uuid.uuid4().hex
            now = utc_now()
            conn.execute(
                """
                INSERT INTO sessions (id, project_id, title, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, project["id"], "New chat", user_id, now, now),
            )
            conn.execute(
                """
                INSERT INTO user_state (user_id, current_project_id, current_session_id, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, project["id"], session_id, now),
            )
        return CurrentState(project_id=project["id"], session_id=session_id)

    def set_current_project(self, *, user_id: int, project_id: str) -> CurrentState:
        if self.get_project(project_id) is None:
            raise ValueError(f"Unknown project: {project_id}")

        session = self.latest_session(user_id=user_id, project_id=project_id)
        if session is None:
            session = self.create_session(
                user_id=user_id,
                project_id=project_id,
                title="New chat",
            )
        self.set_current_session(user_id=user_id, session_id=session.id)
        return CurrentState(project_id=project_id, session_id=session.id)

    def create_session(self, *, user_id: int, project_id: str, title: str) -> SessionRecord:
        if self.get_project(project_id) is None:
            raise ValueError(f"Unknown project: {project_id}")
        session_id = uuid.uuid4().hex
        now = utc_now()
        title = title.strip() or "New chat"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, project_id, title, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, project_id, title[:120], user_id, now, now),
            )
            conn.execute(
                """
                INSERT INTO user_state (user_id, current_project_id, current_session_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  current_project_id = excluded.current_project_id,
                  current_session_id = excluded.current_session_id,
                  updated_at = excluded.updated_at
                """,
                (user_id, project_id, session_id, now),
            )
        return SessionRecord(
            id=session_id,
            project_id=project_id,
            title=title[:120],
            created_at=now,
            updated_at=now,
        )

    def latest_session(self, *, user_id: int, project_id: str) -> SessionRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, project_id, title, created_at, updated_at
                FROM sessions
                WHERE created_by = ? AND project_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (user_id, project_id),
            ).fetchone()
        return _session_from_row(row) if row else None

    def list_sessions(
        self,
        *,
        user_id: int,
        project_id: str,
        limit: int = 20,
    ) -> list[SessionRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, project_id, title, created_at, updated_at
                FROM sessions
                WHERE created_by = ? AND project_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (user_id, project_id, limit),
            ).fetchall()
        return [_session_from_row(row) for row in rows]

    def get_session(self, session_id: str) -> SessionRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, project_id, title, created_at, updated_at
                FROM sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
        return _session_from_row(row) if row else None

    def set_current_session(self, *, user_id: int, session_id: str) -> CurrentState:
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Unknown session: {session_id}")
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_state (user_id, current_project_id, current_session_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  current_project_id = excluded.current_project_id,
                  current_session_id = excluded.current_session_id,
                  updated_at = excluded.updated_at
                """,
                (user_id, session.project_id, session.id, now),
            )
        return CurrentState(project_id=session.project_id, session_id=session.id)

    def rename_session(self, *, session_id: str, title: str) -> None:
        title = title.strip()[:120]
        if not title:
            raise ValueError("Session title cannot be empty.")
        with self.connect() as conn:
            conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title, utc_now(), session_id),
            )

    def append_message(self, *, session_id: str, role: str, content: str) -> None:
        if role not in {"user", "assistant", "system"}:
            raise ValueError(f"Unsupported message role: {role}")
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, now),
            )
            conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))

    def recent_messages(self, *, session_id: str, limit: int) -> list[MessageRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        messages = [
            MessageRecord(role=row["role"], content=row["content"], created_at=row["created_at"])
            for row in rows
        ]
        return list(reversed(messages))


def _session_from_row(row: sqlite3.Row) -> SessionRecord:
    return SessionRecord(
        id=row["id"],
        project_id=row["project_id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
