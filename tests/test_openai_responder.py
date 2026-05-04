import asyncio
from types import SimpleNamespace

from pocket_codex.openai_responder import (
    OpenAIResponder,
    ProjectToolbox,
    _function_tools,
    _run_tool_call,
)
from pocket_codex.repository import MessageRecord


def test_function_tools_include_available_project_tools() -> None:
    async def run(command: str) -> str:
        return command

    tools = _function_tools(ProjectToolbox(run_local=run, run_ssh=run))

    assert [tool["name"] for tool in tools] == ["run_ssh_command", "run_local_command"]
    assert tools[0]["parameters"]["required"] == ["command"]
    assert tools[0]["parameters"]["additionalProperties"] is False


def test_run_tool_call_dispatches_to_ssh_tool() -> None:
    async def run_ssh(command: str) -> str:
        return f"ran: {command}"

    call = SimpleNamespace(
        name="run_ssh_command",
        arguments='{"command":"pwd"}',
    )

    output, observation = asyncio.run(
        _run_tool_call(call, ProjectToolbox(run_ssh=run_ssh))
    )

    assert output == "ran: pwd"
    assert observation is not None
    assert observation.mode == "ssh"
    assert observation.command == "pwd"


def test_reply_runs_function_tool_loop() -> None:
    async def run_ssh(command: str) -> str:
        return f"[Command output]\nCommand: {command}\nOutput:\nremote ok"

    responder = OpenAIResponder.__new__(OpenAIResponder)
    responder.settings = SimpleNamespace(openai_model="gpt-test", openai_store=False)
    responder.client = SimpleNamespace(responses=_FakeResponses())

    result = asyncio.run(
        responder.reply(
            project_name="steel_cxx",
            project_path="D:/code/steel_cxx",
            project_prompt="",
            history=[
                MessageRecord(role="user", content="之前的消息", created_at="now"),
            ],
            user_message="看一下服务器",
            model="gpt-test",
            toolbox=ProjectToolbox(run_ssh=run_ssh),
        )
    )

    assert result.text == "远端可以访问。"
    assert len(result.tool_observations) == 1
    assert result.tool_observations[0].command == "pwd"


class _FakeResponses:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(
                output_text="",
                output=[
                    _FakeFunctionCall(
                        name="run_ssh_command",
                        arguments='{"command":"pwd"}',
                        call_id="call_1",
                    )
                ],
            )

        assert any(
            item.get("type") == "function_call_output"
            for item in kwargs["input"]
            if isinstance(item, dict)
        )
        return SimpleNamespace(output_text="远端可以访问。", output=[])


class _FakeFunctionCall:
    type = "function_call"

    def __init__(self, *, name: str, arguments: str, call_id: str) -> None:
        self.name = name
        self.arguments = arguments
        self.call_id = call_id

    def model_dump(self, *, exclude_none: bool = False):
        return {
            "type": "function_call",
            "name": self.name,
            "arguments": self.arguments,
            "call_id": self.call_id,
        }
