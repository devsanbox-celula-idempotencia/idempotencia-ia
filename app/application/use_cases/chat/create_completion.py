"""POST /v1/completions (API legacy): se traduce a un chat de un solo mensaje."""
from __future__ import annotations

from app.application.dto.chat_dto import ChatCompletionInput, ChatCompletionOutput, ChatMessageDTO
from app.application.use_cases.chat.create_chat_completion import CreateChatCompletion


class CreateCompletion:
    def __init__(self, chat_use_case: CreateChatCompletion) -> None:
        self._chat = chat_use_case

    async def execute(
        self, data: ChatCompletionInput, prompt: str, provider_model: str
    ) -> ChatCompletionOutput:
        data.messages = [ChatMessageDTO(role="user", content=prompt)]
        return await self._chat.execute(data, provider_model)
