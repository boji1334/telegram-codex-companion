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
    assert repo.has_user(42)

    work_state = repo.set_current_project(user_id=42, project_id="work")
    assert work_state.project_id == "work"

    session = repo.create_session(user_id=42, project_id="work", title="Research")
    repo.append_message(session_id=session.id, role="user", content="hi")
    repo.append_message(session_id=session.id, role="assistant", content="hello")

    messages = repo.recent_messages(session_id=session.id, limit=10)
    assert [message.role for message in messages] == ["user", "assistant"]
    assert repo.list_sessions(user_id=42, project_id="work")[0].title == "Research"

