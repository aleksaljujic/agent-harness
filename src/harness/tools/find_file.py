from typing import Optional
from pydantic import BaseModel
from rich.panel import Panel
from harness.tools.base import Tool, run_script, console

class FindFileArgs(BaseModel):
    pattern: str
    limit: Optional[int] = None

DEFINITION = {
    "type": "function",
    "function": {
        "name": "find_file",
        "description": (
            "Find files by name or path, not by contents (use search for contents). "
            "pattern is a glob (e.g. *.py, src/**/test_*.py); if it has no glob "
            "characters it is matched as a substring of the filename. Returns "
            "matching relative paths, one per line, capped at 100 (override with limit)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob like *.py, or a filename substring"},
                "limit": {"type": "integer", "description": "Max results, default 100"},
            },
            "required": ["pattern"],
        },
    },
}

def handler(sandbox, args: FindFileArgs) -> str:
    label = args.pattern + (f"  (limit {args.limit})" if args.limit else "")
    console.print(Panel(label, title="find", border_style="green", title_align="left"))

    payload = {"pattern": args.pattern}
    if args.limit is not None:
        payload["limit"] = args.limit
    return run_script(sandbox, "find_file.py", payload)

TOOL = Tool("find_file", FindFileArgs, DEFINITION, handler)
