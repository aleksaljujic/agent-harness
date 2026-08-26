from abc import ABC, abstractmethod
from pydantic import BaseModel

class ToolCall(BaseModel):
    id: str
    name: str
    arguments: str

class CompletionResult(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = []
    usage: tuple[int, int]
    raw_message: object = None
    latency: float | None = None

class LLMProvider(ABC):
    @abstractmethod
    def complete(self, messages: list, tools: list) -> CompletionResult:
        ...