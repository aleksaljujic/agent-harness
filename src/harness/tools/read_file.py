from typing import Optional
from pydantic import BaseModel
from rich.panel import Panel
from harness.tools.base import Tool, run_script, console

class ReadFileArgs(BaseModel):
    path: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None

DEFINITION = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": (
            "Read a file and return line-numbered content (like `cat -n`). "
            "Optionally restrict to a 1-indexed inclusive line range via "
            "start_line and/or end_line."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path, e.g. utils.py"},
                "start_line": {"type": "integer", "description": "First line to read, 1-indexed, optional"},
                "end_line": {"type": "integer", "description": "Last line to read, inclusive, optional"},
            },
            "required": ["path"],
        },
    },
}

def handler(sandbox, args: ReadFileArgs) -> str:
    rng = ""
    if args.start_line is not None or args.end_line is not None:
        rng = f"  [{args.start_line or ''}:{args.end_line or ''}]"
    console.print(Panel(f"{args.path}{rng}", title="read", border_style="blue", title_align="left"))
    return run_script(sandbox, "read_file.py", {
        "path": args.path,
        "start_line": args.start_line,
        "end_line": args.end_line,
    })

TOOL = Tool("read_file", ReadFileArgs, DEFINITION, handler)
