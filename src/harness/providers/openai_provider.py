from openai import OpenAI
from harness.providers.base import LLMProvider, CompletionResult, ToolCall


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key, base_url, model, reasoning_effort=None):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.reasoning_effort = reasoning_effort  # None | "minimal" | "low" | "medium" | "high"

    def complete(self, messages, tools):
        kwargs = {"model": self.model, "messages": messages, "tools": tools}
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        else:
            kwargs["temperature"] = 0.0

        resp = self.client.chat.completions.create(**kwargs)
        latency = getattr(resp, "latency_checkpoint", None)
        msg = resp.choices[0].message

        details = getattr(resp.usage, "completion_tokens_details", None)
        reasoning_tokens = getattr(details, "reasoning_tokens", 0) or 0

        assistant_message = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]

        return CompletionResult(
            content=msg.content,
            tool_calls=[
                ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
                for tc in (msg.tool_calls or [])
            ],
            assistant_message=assistant_message,
            raw_message=msg,
            usage=(resp.usage.prompt_tokens, resp.usage.completion_tokens),
            reasoning_tokens=reasoning_tokens,
            latency=latency,
        )
