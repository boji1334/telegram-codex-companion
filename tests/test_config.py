import json
from pathlib import Path

from pocket_codex.config import _load_projects


def test_load_projects_reads_command_and_ssh_fields(tmp_path: Path) -> None:
    projects_path = tmp_path / "projects.json"
    projects_path.write_text(
        json.dumps(
            [
                {
                    "id": "work",
                    "name": "Work",
                    "path": str(tmp_path),
                    "system_prompt": "Project prompt",
                    "allow_shell": True,
                    "ssh_target": "user@example.com",
                    "ssh_remote_path": "/srv/work",
                    "ssh_executable": "plink.exe",
                    "ssh_hostkey": "SHA256:test",
                    "ssh_password_env": "WORK_SSH_PASSWORD",
                    "ssh_password_file": str(tmp_path / "password.txt"),
                }
            ]
        ),
        encoding="utf-8",
    )

    project = _load_projects(projects_path)[0]

    assert project.allow_shell is True
    assert project.ssh_target == "user@example.com"
    assert project.ssh_remote_path == "/srv/work"
    assert project.ssh_executable.name == "plink.exe"
    assert project.ssh_hostkey == "SHA256:test"
    assert project.ssh_password_env == "WORK_SSH_PASSWORD"
    assert project.ssh_password_file == tmp_path / "password.txt"
