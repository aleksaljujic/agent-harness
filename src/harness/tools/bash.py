from pydantic import BaseModel
from rich.panel import Panel
from harness.tools.base import Tool, console

class BashArgs(BaseModel):
    command: str

DEFINITION = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Executing bash command in /work and return stdout+stderr.",
        "parameters": {
            "type": "object",
            "properties": {
                "thought": {"type": "string", "description": "Why you run this command."},
                "command": {"type": "string"},
            },
            "required": ["thought", "command"],
        },
    },
}

def handler(sandbox, args: BashArgs) -> str:
    console.print(Panel(args.command, title="bash", border_style="cyan", title_align="left"))
    return sandbox.run(args.command)

TOOL = Tool("bash", BashArgs, DEFINITION, handler)
