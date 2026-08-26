from openai import OpenAI
from harness.providers.base import LLMProvider, CompletionResult, ToolCall

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key, base_url, model):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        
    def complete(self, messages, tools):
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools = tools
        )
        latency = getattr(resp, "latency_checkpoint", None)
        msg = resp.choices[0].message
        
        return CompletionResult(
            content=msg.content,
            tool_calls=[
                ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
                for tc in (msg.tool_calls or [])
            ],
            raw_message=msg,
            usage=(resp.usage.prompt_tokens, resp.usage.completion_tokens),
            latency=latency
        )