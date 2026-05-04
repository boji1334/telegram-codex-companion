import sqlite3
from pathlib import Path

from pocket_codex.config import ProjectConfig
from pocket_codex.repository import Repository


def test_repository_creates_state_and_sessions(tmp_path: Path) -> None:
    repo = Repository(tmp_path / "test.sqlite3")
    repo.migrate()
    repo.sync_projects(
        [
            ProjectConfig(id="general", name="General Chat"),
            ProjectConfig(id="work", name="Work"),
        ]
    )

    repo.add_or_update_user(user_id=42, username="alice", display_name="Alice")
    state = repo.ensure_state(42)

    assert state.project_id == "general"
    assert state.is_active is True
    assert repo.has_user(42)

    inactive_state = repo.set_user_active(user_id=42, active=False)
    assert inactive_state.is_active is False
    assert repo.ensure_state(42).is_active is False

    work_state = repo.set_current_project(user_id=42, project_id="work")
    assert work_state.project_id == "work"
    assert work_state.is_active is True

    session = repo.create_session(user_id=42, project_id="work", title="Research")
    repo.append_message(session_id=session.id, role="user", content="hi")
    repo.append_message(session_id=session.id, role="assistant", content="hello")

    messages = repo.recent_messages(session_id=session.id, limit=10)
    assert [message.role for message in messages] == ["user", "assistant"]
    assert repo.list_sessions(user_id=42, project_id="work")[0].title == "Research"


def test_repository_migrates_existing_user_state_active_flag(tmp_path: Path) -> None:
    database_path = tmp_path / "old.sqlite3"
    with sqlite3.connect(database_path) as conn:
        conn.executescript(
            """
            CREATE TABLE users (
              user_id INTEGER PRIMARY KEY,
              username TEXT,
              display_name TEXT,
              role TEXT NOT NULL DEFAULT 'admin',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE projects (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              path TEXT,
              system_prompt TEXT NOT NULL DEFAULT '',
              enabled INTEGER NOT NULL DEFAULT 1,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE sessions (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(id),
              title TEXT NOT NULL,
              created_by INTEGER NOT NULL,
              codex_thread_id TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
              role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
              content TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE user_state (
              user_id INTEGER PRIMARY KEY,
              current_project_id TEXT NOT NULL REFERENCES projects(id),
              current_session_id TEXT NOT NULL REFERENCES sessions(id),
              updated_at TEXT NOT NULL
            );
            """
        )

    repo = Repository(database_path)
    repo.migrate()

    with repo.connect() as conn:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(user_state)").fetchall()
        }
    assert "is_active" in columns
