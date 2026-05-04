from __future__ import annotations

import asyncio
import os
import re
import shlex
import time
from dataclasses import dataclass
from pathlib import Path

from .config import ProjectConfig


class CommandRejected(ValueError):
    """Raised when a command is blocked by the read-only safety policy."""


class CommandNotConfigured(RuntimeError):
    """Raised when command execution is disabled or missing project config."""


@dataclass(frozen=True)
class CommandResult:
    mode: str
    command: str
    location: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    truncated: bool

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    @property
    def combined_output(self) -> str:
        parts: list[str] = []
        if self.stdout.strip():
            parts.append(self.stdout.rstrip())
        if self.stderr.strip():
            parts.append("[stderr]\n" + self.stderr.rstrip())
        return "\n\n".join(parts).strip()


_DANGEROUS_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(?i)(^|[\s;&|])(?:sudo|su)\b"),
        "提权命令默认不允许。",
    ),
    (
        re.compile(r"(?i)(^|[\s;&|])(?:rm|rmdir|del|erase|remove-item)\b"),
        "删除文件/目录的命令默认不允许。",
    ),
    (
        re.compile(r"(?i)(^|[\s;&|])(?:mv|move|ren|rename-item)\b"),
        "移动或重命名文件的命令默认不允许。",
    ),
    (
        re.compile(r"(?i)(^|[\s;&|])(?:cp|copy|xcopy|robocopy|scp|rsync)\b"),
        "复制/同步文件的命令默认不允许。",
    ),
    (
        re.compile(r"(?i)(^|[\s;&|])(?:chmod|chown|icacls|takeown)\b"),
        "修改权限/所有权的命令默认不允许。",
    ),
    (
        re.compile(r"(?i)(^|[\s;&|])(?:kill|pkill|taskkill|stop-process)\b"),
        "终止进程的命令默认不允许。",
    ),
    (
        re.compile(r"(?i)(^|[\s;&|])(?:shutdown|reboot|poweroff|halt|restart-computer)\b"),
        "关机或重启命令默认不允许。",
    ),
    (
        re.compile(r"(?i)(^|[\s;&|])(?:mkfs|format|diskpart|parted|fdisk)\b"),
        "磁盘/分区类命令默认不允许。",
    ),
    (
        re.compile(r"(?i)\bgit\s+(?:reset|clean|checkout|restore|push|pull|commit|merge|rebase)\b"),
        "会改动 Git 工作区或远端的命令默认不允许。",
    ),
    (
        re.compile(
            r"(?i)\b(?:pip|conda|npm|pnpm|yarn|apt|apt-get|yum|dnf|pacman|brew)\s+"
            r"(?:install|remove|uninstall|update|upgrade|add)\b"
        ),
        "安装、卸载或升级依赖的命令默认不允许。",
    ),
    (
        re.compile(r"(?<!\d)>{1,2}"),
        "输出重定向会写文件，默认不允许。",
    ),
    (
        re.compile(r"(?i)(^|[\s;&|])tee\b"),
        "tee 通常会写文件，默认不允许。",
    ),
)


def validate_read_only_command(command: str) -> str:
    normalized = command.strip()
    if not normalized:
        raise CommandRejected("命令不能为空。")
    if "\x00" in normalized:
        raise CommandRejected("命令包含非法字符。")

    for pattern, reason in _DANGEROUS_PATTERNS:
        if pattern.search(normalized):
            raise CommandRejected(reason)
    return normalized


async def run_local_command(
    *,
    project: ProjectConfig,
    command: str,
    timeout_seconds: int,
    output_max_chars: int,
) -> CommandResult:
    command = validate_read_only_command(command)
    if project.path is None:
        raise CommandNotConfigured("当前项目没有本机路径，不能执行 /run。")
    if not project.path.exists():
        raise CommandNotConfigured(f"项目路径不存在：{project.path}")

    argv = _local_shell_argv(command)
    return await _run_process(
        argv,
        command=command,
        mode="local",
        location=str(project.path),
        cwd=project.path,
        timeout_seconds=timeout_seconds,
        output_max_chars=output_max_chars,
    )


async def run_ssh_command(
    *,
    project: ProjectConfig,
    command: str,
    timeout_seconds: int,
    output_max_chars: int,
) -> CommandResult:
    command = validate_read_only_command(command)
    if not project.ssh_target:
        raise CommandNotConfigured("当前项目没有配置 ssh_target，不能执行 /ssh。")

    remote_command = command
    if project.ssh_remote_path:
        remote_command = f"cd {shlex.quote(project.ssh_remote_path)} && {command}"

    argv = _ssh_argv(
        project=project,
        remote_command=remote_command,
        timeout_seconds=timeout_seconds,
    )
    location = project.ssh_target
    if project.ssh_remote_path:
        location = f"{location}:{project.ssh_remote_path}"

    return await _run_process(
        argv,
        command=command,
        mode="ssh",
        location=location,
        cwd=project.path if project.path and project.path.exists() else None,
        timeout_seconds=timeout_seconds,
        output_max_chars=output_max_chars,
    )


def command_memory_block(result: CommandResult) -> str:
    output = result.combined_output or "(no output)"
    status = "timeout" if result.timed_out else str(result.exit_code)
    truncated = "\nOutput was truncated for context safety." if result.truncated else ""
    return "\n".join(
        [
            "[Command output]",
            f"Mode: {result.mode}",
            f"Location: {result.location}",
            f"Command: {result.command}",
            f"Exit code: {status}",
            f"Duration: {result.duration_seconds:.1f}s",
            "Output:",
            output,
            truncated,
        ]
    ).strip()


def _local_shell_argv(command: str) -> list[str]:
    if os.name == "nt":
        return [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ]
    return ["/bin/sh", "-lc", command]


def _ssh_argv(
    *,
    project: ProjectConfig,
    remote_command: str,
    timeout_seconds: int,
) -> list[str]:
    executable = str(project.ssh_executable or "ssh")
    if _looks_like_plink(executable):
        argv = [executable, "-batch", "-ssh", project.ssh_target or ""]
        password = _read_ssh_password(project)
        if password:
            argv.extend(["-pw", password])
        if project.ssh_hostkey:
            argv.extend(["-hostkey", project.ssh_hostkey])
        argv.append(remote_command)
        return argv

    connect_timeout = max(1, min(15, timeout_seconds))
    return [
        executable,
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={connect_timeout}",
        project.ssh_target or "",
        remote_command,
    ]


def _looks_like_plink(executable: str) -> bool:
    return "plink" in Path(executable).name.casefold()


def _read_ssh_password(project: ProjectConfig) -> str | None:
    if project.ssh_password_env:
        value = os.getenv(project.ssh_password_env, "").strip()
        if value:
            return value

    if project.ssh_password_file:
        try:
            text = project.ssh_password_file.read_text(encoding="utf-8")
        except OSError:
            return None
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("pwd:"):
                return stripped.split(":", maxsplit=1)[1].strip() or None
        non_empty = [line.strip() for line in text.splitlines() if line.strip()]
        if len(non_empty) == 1:
            return non_empty[0]
    return None


async def _run_process(
    argv: list[str],
    *,
    command: str,
    mode: str,
    location: str,
    cwd: Path | None,
    timeout_seconds: int,
    output_max_chars: int,
) -> CommandResult:
    start = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    timed_out = False
    try:
        stdout_raw, stderr_raw = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        timed_out = True
        process.kill()
        stdout_raw, stderr_raw = await process.communicate()

    stdout = _decode(stdout_raw)
    stderr = _decode(stderr_raw)
    stdout, stderr, truncated = _trim_outputs(
        stdout=stdout,
        stderr=stderr,
        output_max_chars=output_max_chars,
    )
    return CommandResult(
        mode=mode,
        command=command,
        location=location,
        exit_code=None if timed_out else process.returncode,
        stdout=stdout,
        stderr=stderr,
        duration_seconds=time.monotonic() - start,
        timed_out=timed_out,
        truncated=truncated,
    )


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").replace("\r\n", "\n")


def _trim_outputs(
    *,
    stdout: str,
    stderr: str,
    output_max_chars: int,
) -> tuple[str, str, bool]:
    if output_max_chars <= 0:
        return stdout, stderr, False

    combined_len = len(stdout) + len(stderr)
    if combined_len <= output_max_chars:
        return stdout, stderr, False

    stderr_budget = min(len(stderr), max(1000, output_max_chars // 4))
    stdout_budget = max(0, output_max_chars - stderr_budget)
    return (
        _trim_middle(stdout, stdout_budget),
        _trim_middle(stderr, stderr_budget),
        True,
    )


def _trim_middle(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars < 80:
        return text[:max_chars]
    head = max_chars // 2
    tail = max_chars - head - 36
    return f"{text[:head]}\n...[truncated middle]...\n{text[-tail:]}"
