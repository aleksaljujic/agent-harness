from pydantic import BaseModel
from rich.panel import Panel
from harness.tools.base import Tool, run_script, console

class StrReplaceArgs(BaseModel):
    path: str
    old_str: str
    new_str: str

DEFINITION = {
    "type": "function",
    "function": {
        "name": "str_replace",
        "description": (
            "Replace an exact string in a file. old_str must appear exactly once "
            "and must include exact indentation. Prefer this over rewriting whole files."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path, e.g. utils.py"},
                "old_str": {"type": "string", "description": "Exact text to replace, including whitespace"},
                "new_str": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_str", "new_str"],
        },
    },
}

def handler(sandbox, args: StrReplaceArgs) -> str:
    out = run_script(sandbox, "str_replace.py", {
        "path": args.path,
        "old": args.old_str,
        "new": args.new_str,
    })
    console.print(Panel(f"{args.path} → {out}", title="edit", border_style="yellow", title_align="left"))
    return out

TOOL = Tool("str_replace", StrReplaceArgs, DEFINITION, handler)
