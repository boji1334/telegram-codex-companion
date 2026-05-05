from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from openai import AsyncOpenAI

from .config import Settings
from .repository import MessageRecord


@dataclass(frozen=True)
class ToolObservation:
    mode: str
    command: str
    content: str


@dataclass(frozen=True)
class ReplyResult:
    text: str
    tool_observations: tuple[ToolObservation, ...] = ()


@dataclass(frozen=True)
class ProjectToolbox:
    run_local: Callable[[str], Awaitable[str]] | None = None
    run_ssh: Callable[[str], Awaitable[str]] | None = None

    @property
    def enabled(self) -> bool:
        return self.run_local is not None or self.run_ssh is not None


class OpenAIResponder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )

    async def reply(
        self,
        *,
        project_name: str,
        project_path: str | None,
        project_prompt: str,
        history: list[MessageRecord],
        user_message: str,
        model: str | None = None,
        toolbox: ProjectToolbox | None = None,
    ) -> ReplyResult:
        instructions = self._instructions(
            project_name=project_name,
            project_path=project_path,
            project_prompt=project_prompt,
            tools_enabled=bool(toolbox and toolbox.enabled),
        )
        input_messages = [
            {"role": message.role, "content": message.content}
            for message in history
            if message.role in {"user", "assistant", "system"}
        ]
        input_messages.append({"role": "user", "content": user_message})
        tools = _function_tools(toolbox)
        observations: list[ToolObservation] = []
        max_tool_rounds = getattr(self.settings, "command_tool_max_rounds", 16)

        for _ in range(max_tool_rounds):
            response_kwargs = {
                "model": model or self.settings.openai_model,
                "instructions": instructions,
                "input": input_messages,
                "store": self.settings.openai_store,
            }
            if tools:
                response_kwargs["tools"] = tools
                response_kwargs["parallel_tool_calls"] = False

            response = await self.client.responses.create(**response_kwargs)
            function_calls = [
                item
                for item in response.output
                if getattr(item, "type", None) == "function_call"
            ]
            if not function_calls:
                text = response.output_text.strip()
                return ReplyResult(
                    text=text or "我收到了，但这次没有生成有效文本。",
                    tool_observations=tuple(observations),
                )

            input_messages.extend(
                item.model_dump(exclude_none=True) for item in response.output
            )
            for call in function_calls:
                output, observation = await _run_tool_call(call, toolbox)
                if observation:
                    observations.append(observation)
                input_messages.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": output,
                    }
                )

        input_messages.append(
            {
                "role": "system",
                "content": (
                    "No more tool calls are available in this turn. Answer now using "
                    "the command outputs already provided. Do not ask the user to run "
                    "commands manually, paste outputs, or shrink the question."
                ),
            }
        )
        response = await self.client.responses.create(
            model=model or self.settings.openai_model,
            instructions=instructions,
            input=input_messages,
            store=self.settings.openai_store,
        )
        text = response.output_text.strip()
        return ReplyResult(
            text=text or "我已经读取了一部分项目/服务器信息，但这次没有生成有效总结。",
            tool_observations=tuple(observations),
        )

    @staticmethod
    def _instructions(
        *,
        project_name: str,
        project_path: str | None,
        project_prompt: str,
        tools_enabled: bool = False,
    ) -> str:
        parts = [
            "You are a Telegram remote client for the user's Codex Desktop conversations.",
            "Answer in the user's language unless they explicitly ask otherwise.",
            "Be concise, practical, and clear.",
            (
                "When prior Codex Desktop history is provided, "
                "treat it as the same ongoing conversation."
            ),
            "When history includes [Command output], treat it as observed shell/SSH output.",
            f"Current project: {project_name}.",
        ]
        if project_path:
            parts.append(f"Project path on the host machine: {project_path}.")
            if tools_enabled:
                parts.append(
                    "You may use the provided read-only project tools to inspect files, "
                    "logs, GPU status, and training outputs before answering."
                )
                parts.append(
                    "If the user asks to look at the server, training progress, logs, "
                    "artifacts, or current results, call the SSH/local tools instead of "
                    "asking the user to paste command output."
                )
                parts.append(
                    "Use a small number of targeted read-only commands. Prefer SSH for "
                    "remote server state when an SSH tool is available. Combine related "
                    "checks into one shell command when practical, then answer with a "
                    "clear conclusion rather than continuing to inspect indefinitely."
                )
            else:
                parts.append(
                    "Do not claim to have read local files unless file contents are provided."
                )
        if project_prompt:
            parts.append(f"Project-specific instruction: {project_prompt}")
        return "\n".join(parts)


def _function_tools(toolbox: ProjectToolbox | None) -> list[dict]:
    if not toolbox or not toolbox.enabled:
        return []

    tools: list[dict] = []
    if toolbox.run_ssh:
        tools.append(
            _command_tool(
                name="run_ssh_command",
                description=(
                    "Run a read-only shell command on the current project's configured "
                    "remote SSH server. Use this for server logs, GPU status, training "
                    "progress, artifacts, and result files."
                ),
            )
        )
    if toolbox.run_local:
        tools.append(
            _command_tool(
                name="run_local_command",
                description=(
                    "Run a read-only command in the current local project folder on the "
                    "always-on host computer. Use this for local files and project state."
                ),
            )
        )
    return tools


def _command_tool(*, name: str, description: str) -> dict:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": (
                        "A read-only shell command. Do not use delete, move, install, "
                        "permission-changing, process-kill, reboot, or write-redirection commands."
                    ),
                }
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    }


async def _run_tool_call(
    call,
    toolbox: ProjectToolbox | None,
) -> tuple[str, ToolObservation | None]:
    try:
        args = json.loads(call.arguments or "{}")
    except json.JSONDecodeError:
        return "Invalid JSON arguments.", None

    command = str(args.get("command", "")).strip()
    if not command:
        return "Missing required argument: command.", None

    try:
        if call.name == "run_ssh_command" and toolbox and toolbox.run_ssh:
            output = await toolbox.run_ssh(command)
            return output, ToolObservation(mode="ssh", command=command, content=output)
        if call.name == "run_local_command" and toolbox and toolbox.run_local:
            output = await toolbox.run_local(command)
            return output, ToolObservation(mode="local", command=command, content=output)
    except Exception as exc:
        return f"Tool execution failed: {type(exc).__name__}: {exc}", None

    return f"Unknown or unavailable tool: {call.name}.", None
