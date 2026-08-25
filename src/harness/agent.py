from openai import OpenAI
from harness.tools import TOOLS, SCHEMAS, do_str_replace, do_search
from pydantic import ValidationError
from harness.prompt import DEFAULT_SYSTEM_PROMPT
from harness.config import settings
from pydantic import BaseModel, computed_field
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown

console = Console()

MODEL = settings.azure_openai_deployment

client = OpenAI(
    base_url=settings.azure_openai_endpoint,
    api_key=settings.azure_openai_api_key,
)

class Usage(BaseModel):
    prompt: int = 0
    completion: int = 0
    calls: int = 0
    
    @computed_field
    @property
    def cost(self) -> float:
        return (self.prompt * settings.price_in
                + self.completion * settings.price_out) / 1_000_000
    
    

class Agent:
    def __init__(self, sandbox, system_promt = None, max_turns = 20):
        self.sandbox = sandbox
        self.max_turns = max_turns or settings.max_turns
        self.usage: Usage = Usage()
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
            resp = client.chat.completions.create(
                model=MODEL, messages=self.messages, tools=TOOLS
            )
            u = resp.usage
            self.usage.prompt += u.prompt_tokens
            self.usage.completion += u.completion_tokens
            self.usage.calls += 1
            
            msg = resp.choices[0].message
            if hasattr(msg, "reasoning_content") and msg.reasoning_content:
                console.print(Panel(msg.reasoning_content, title="thinking", border_style="dim", title_align="left"))
            self.messages.append(msg)
            
            if not msg.tool_calls:
                return msg.content
            
            for tc in msg.tool_calls:
                out = self._dispatch(tc)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": out
                })
        return "Maximum number of steps reached"
                
    def _dispatch(self, tc):
        name = tc.function.name
        schema = SCHEMAS.get(name)
        
        if schema is None:
            return f"ERROR: unknown tool: {name}"
        
        try:
            args = schema.model_validate_json(tc.function.arguments)
        except ValidationError as e:
            return f"ERROR: invalid arguments for {name}: {e}"
        
        match name:
            case "bash":
                console.print(Panel(args.command, title="bash", border_style="cyan", title_align="left"))
                return self.sandbox.run(args.command)
            case "search":
                label = f"{args.pattern}" + (f"  ({args.glob})" if args.glob else "")
                console.print(Panel(label, title="search", border_style="magenta", title_align="left"))
                return do_search(self.sandbox, args.pattern, args.glob)
            case "str_replace":
                out = do_str_replace(self.sandbox, args.path, args.old_str, args.new_str)
                console.print(Panel(f"{args.path} → {out}", title="edit", border_style="yellow", title_align="left"))
                return out
            
        return f"Unknown tool: {name}"
    
    