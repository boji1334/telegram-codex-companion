import asyncio
from pathlib import Path

import pytest

from pocket_codex.command_runner import (
    CommandRejected,
    _read_ssh_password,
    run_local_command,
    validate_read_only_command,
)
from pocket_codex.config import ProjectConfig


def test_validate_read_only_command_blocks_destructive_commands() -> None:
    with pytest.raises(CommandRejected):
        validate_read_only_command("rm -rf artifacts")

    with pytest.raises(CommandRejected):
        validate_read_only_command("git reset --hard")

    assert validate_read_only_command("find artifacts -type f | sort | tail -n 20")


def test_run_local_command_captures_output(tmp_path: Path) -> None:
    project = ProjectConfig(
        id="demo",
        name="Demo",
        path=tmp_path,
        allow_shell=True,
    )

    result = asyncio.run(
        run_local_command(
            project=project,
            command="python -c \"print('hello from command')\"",
            timeout_seconds=10,
            output_max_chars=1000,
        )
    )

    assert result.ok
    assert "hello from command" in result.stdout


def test_ssh_password_file_supports_data_path_style(tmp_path: Path) -> None:
    password_file = tmp_path / "data_path.txt"
    password_file.write_text(
        "ssh user@example.com:\n"
        "pwd:secret-value\n"
        "code: /srv/project\n",
        encoding="utf-8",
    )
    project = ProjectConfig(
        id="remote",
        name="Remote",
        ssh_password_file=password_file,
    )

    assert _read_ssh_password(project) == "secret-value"
