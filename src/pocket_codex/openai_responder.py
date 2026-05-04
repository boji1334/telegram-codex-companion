from __future__ import annotations

from openai import AsyncOpenAI

from .config import Settings
from .repository import MessageRecord


class OpenAIResponder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def reply(
        self,
        *,
        project_name: str,
        project_path: str | None,
        project_prompt: str,
        history: list[MessageRecord],
        user_message: str,
    ) -> str:
        instructions = self._instructions(
            project_name=project_name,
            project_path=project_path,
            project_prompt=project_prompt,
        )
        input_messages = [
            {"role": message.role, "content": message.content}
            for message in history
            if message.role in {"user", "assistant", "system"}
        ]
        input_messages.append({"role": "user", "content": user_message})

        response = await self.client.responses.create(
            model=self.settings.openai_model,
            instructions=instructions,
            input=input_messages,
            store=self.settings.openai_store,
        )
        text = response.output_text.strip()
        return text or "我收到了，但这次没有生成有效文本。"

    @staticmethod
    def _instructions(*, project_name: str, project_path: str | None, project_prompt: str) -> str:
        parts = [
            "You are a private, long-running conversation companion inside Telegram.",
            "Answer in the user's language unless they explicitly ask otherwise.",
            "Be concise, practical, and clear.",
            f"Current project: {project_name}.",
        ]
        if project_path:
            parts.append(f"Project path on the host machine: {project_path}.")
            parts.append("Do not claim to have read local files unless file contents are provided.")
        if project_prompt:
            parts.append(f"Project-specific instruction: {project_prompt}")
        return "\n".join(parts)

