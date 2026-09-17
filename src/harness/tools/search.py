from typing import Optional
from pydantic import BaseModel
from rich.panel import Panel
from harness.tools.base import Tool, run_script, console

class SearchArgs(BaseModel):
    pattern: str
    glob: Optional[str] = None

DEFINITION = {
    "type": "function",
    "function": {
        "name": "search",
        "description": (
            "Search file contents by extended regex (grep -E). Returns path:line:content, "
            "capped at 50 hits; when capped, a last line gives the total. glob optionally "
            "limits which files are searched: a filename glob (*.py), a path glob matched "
            "like find_file (sympy/**/*.py), or a file or directory path (sympy/core)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Extended regex"},
                "glob": {
                    "type": "string",
                    "description": "Optional: *.py, sympy/**/*.py, or a file/directory path",
                },
            },
            "required": ["pattern"],
        },
    },
}

def handler(sandbox, args: SearchArgs) -> str:
    label = f"{args.pattern}" + (f"  ({args.glob})" if args.glob else "")
    console.print(Panel(label, title="search", border_style="magenta", title_align="left"))

    payload = {"pattern": args.pattern}
    if args.glob:
        payload["glob"] = args.glob
    return run_script(sandbox, "search.py", payload)

TOOL = Tool("search", SearchArgs, DEFINITION, handler)
