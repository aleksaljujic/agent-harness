import shlex
from typing import Optional
from pydantic import BaseModel
from rich.panel import Panel
from harness.tools.base import Tool, console

class SearchArgs(BaseModel):
    pattern: str
    glob: Optional[str] = None

DEFINITION = {
    "type": "function",
    "function": {
        "name": "search",
        "description": "Search files by regex. Returns path:line:content, max 50 hits.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "glob": {"type": "string", "description": "e.g. *.py, optional"},
            },
            "required": ["pattern"],
        },
    },
}

def handler(sandbox, args: SearchArgs) -> str:
    label = f"{args.pattern}" + (f"  ({args.glob})" if args.glob else "")
    console.print(Panel(label, title="search", border_style="magenta", title_align="left"))

    include = f"--include={shlex.quote(args.glob)}" if args.glob else ""
    cmd = (
        f"grep -rn {include} --exclude-dir=.git --exclude-dir=node_modules "
        f"-E {shlex.quote(args.pattern)} . | head -50"
    )
    out = sandbox.run(cmd).strip()
    if not out or out.startswith("(no output)"):
        return "No matches."
    return out

TOOL = Tool("search", SearchArgs, DEFINITION, handler)
