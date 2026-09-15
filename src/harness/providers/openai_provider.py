import time

from openai import BadRequestError, OpenAI
from harness.providers.base import LLMProvider, CompletionResult, ToolCall

# A 400 is normally deterministic — retrying an identical payload just loops, which
# is why every other 400 still aborts the run. `invalid_prompt` is the one exception:
# it is the provider's moderation classifier firing on benign source code and stack
# traces (confirmed false positive, see docs/todo/ISSUES.md item 2), and it is not
# reliably reproducible on the same payload. Retried narrowly, never widened.
INVALID_PROMPT_RETRIES = 2
INVALID_PROMPT_BACKOFF_SECONDS = 2.0


def _is_invalid_prompt(e: BadRequestError) -> bool:
    if getattr(e, "code", None) == "invalid_prompt":
        return True
    body = getattr(e, "body", None)
    if not isinstance(body, dict):
        return False
    # Observed shape is the flat error dict ({message, type, param, code}); the
    # {"error": {...}} envelope is checked too since both are documented.
    inner = body.get("error") if isinstance(body.get("error"), dict) else body
    return inner.get("code") == "invalid_prompt"


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key, base_url, model, reasoning_effort=None, temperature=None):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.reasoning_effort = reasoning_effort  # None | "minimal" | "low" | "medium" | "high"
        # None means the `temperature` kwarg is omitted entirely — the API's own
        # default applies. Only an explicit value gets sent. Reasoning models reject
        # `temperature` outright, so it's never sent alongside reasoning_effort
        # regardless of this setting.
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
                    # Carry the attempt count across the raise so a run that never
                    # got through still records how hard it tried; _error_detail
                    # picks this up into errors/<run>.json.
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
