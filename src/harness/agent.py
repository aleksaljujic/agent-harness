from openai import OpenAI
from harness.tools import HANDLERS, get_active_tools
from pydantic import ValidationError
from harness.prompt import DEFAULT_SYSTEM_PROMPT
from harness.config import settings, MODEL_PRICING
from pydantic import BaseModel, computed_field
from harness.providers import make_provider
from harness.providers.base import ToolCall
import time

provider = make_provider(settings)

class Usage(BaseModel):
    prompt: int = 0
    completion: int = 0
    calls: int = 0
    model: str = ""
    llm_time_seconds: float = 0.0
    tool_time_seconds: float = 0.0
    
    @computed_field
    @property
    def cost(self) -> float:
        if self.model not in MODEL_PRICING:
            raise ValueError(
                f"No pricing entry for model {self.model!r}. "
                f"Add it to MODEL_PRICING in config.py."
            )
        price_in, price_out = MODEL_PRICING.get(self.model)
        return (self.prompt * price_in + self.completion * price_out) / 1_000_000

class Agent:
    def __init__(self, sandbox, provider = None, tools = None, system_promt = None, max_turns = None):
        self.provider = provider or globals()["provider"]
        self.sandbox = sandbox
        self.max_turns = max_turns or settings.max_turns
        self.tools, self.schemas = get_active_tools(tools)
        self.usage: Usage = Usage(model = self.provider.model)
        self.messages = [
            {
                "role": "system",
                "content": system_promt or DEFAULT_SYSTEM_PROMPT
            }
        ]
        
    def run(self, task):
        self.messages.append({
            "role": "user",
             "content": task
        })
        
        for _ in range(self.max_turns):
            
            t0 = time.perf_counter()
            result = self.provider.complete(self.messages, self.tools)
            llm_time = time.perf_counter() - t0
            
            self.usage.llm_time_seconds += llm_time
            
            prompt_tokens, completion_tokens = result.usage
            self.usage.prompt += prompt_tokens
            self.usage.completion += completion_tokens
            self.usage.calls += 1
            
            self.messages.append(result.raw_message)
            
            if not result.tool_calls:
                return result.content
            
            tool_timings = []
            
            for call in result.tool_calls:
                t0 = time.perf_counter()
                out = self._dispatch(call)
                tool_timings.append((call.name, time.perf_counter() - t0))
                tool_time = time.perf_counter() - t0
                self.usage.tool_time_seconds += tool_time
                
                self.messages.append({
                    "role": "tool", 
                    "tool_call_id": call.id, 
                    "content": str(out) if out is not None else "(no output)"
                })
                
        return "Maximum number of steps reached"
                
    def _dispatch(self, call: ToolCall):
        schema = self.schemas.get(call.name)
        
        if schema is None:
            return f"ERROR: unknown tool: {call.name}"
        
        try:
            args = schema.model_validate_json(call.arguments)
        except ValidationError as e:
            return f"ERROR: invalid arguments for {call.name}: {e}"

        handler = HANDLERS.get(call.name)
        if handler is None:
            return f"Unknown tool: {call.name}"
        return handler(self.sandbox, args)
    
    