import time

from openai import BadRequestError, OpenAI
from harness.providers.base import LLMProvider, CompletionResult, ToolCall

# Only `invalid_prompt` 400s are retried: a moderation false positive that is not
# reproducible on the same payload (docs/todo/ISSUES.md item 2).
INVALID_PROMPT_RETRIES = 2
INVALID_PROMPT_BACKOFF_SECONDS = 2.0


def _is_invalid_prompt(e: BadRequestError) -> bool:
    if getattr(e, "code", None) == "invalid_prompt":
        return True
    body = getattr(e, "body", None)
    if not isinstance(body, dict):
        return False
    # Flat error dict or {"error": {...}} envelope.
    inner = body.get("error") if isinstance(body.get("error"), dict) else body
    return inner.get("code") == "invalid_prompt"


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key, base_url, model, reasoning_effort=None, temperature=None):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.reasoning_effort = reasoning_effort  # None | "minimal" | "low" | "medium" | "high"
        # None = not sent. Never sent together with reasoning_effort.
        self.temperature = temperature

    def complete(self, messages, tools):
        kwargs = {"model": self.model, "messages": messages, "tools": tools}
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        elif self.temperature is not None:
            kwargs["temperature"] = self.temperature

        retries = 0
        while True:
            try:
                resp = self.client.chat.completions.create(**kwargs)
                break
            except BadRequestError as e:
                if not _is_invalid_prompt(e) or retries >= INVALID_PROMPT_RETRIES:
                    # Read by _error_detail for errors/<run>.json.
                    e.invalid_prompt_retries = retries
                    raise
                retries += 1
                time.sleep(INVALID_PROMPT_BACKOFF_SECONDS)

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
            invalid_prompt_retries=retries,
            raw_message=msg,
            usage=(resp.usage.prompt_tokens, resp.usage.completion_tokens),
            reasoning_tokens=reasoning_tokens,
            latency=latency,
        )
