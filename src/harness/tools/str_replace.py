from typing import Optional
from pydantic import BaseModel, model_validator
from rich.panel import Panel
from harness.tools.base import Tool, run_script, console

class StrReplaceArgs(BaseModel):
    path: str
    old_str: str
    new_str: str
    replace_all: bool = False
    occurrence: Optional[int] = None

    @model_validator(mode="after")
    def _mutually_exclusive(self):
        if self.replace_all and self.occurrence is not None:
            raise ValueError("pass either replace_all or occurrence, not both")
        return self

DEFINITION = {
    "type": "function",
    "function": {
        "name": "str_replace",
        "description": (
            "Replace an exact string in a file. old_str must include exact indentation. "
            "By default old_str must appear exactly once; if it appears more than once, the "
            "error reports the line number of every match. Note: read_file output is prefixed "
            "with '<line>\\t' — strip that prefix before using its text as old_str. "
            "Duplicated code blocks are often identical below as well as above, so if old_str "
            "isn't unique, prefer extending it UPWARD (the preceding comment/def/class line) "
            "rather than downward. Pass replace_all=true to change every occurrence, or "
            "occurrence=N (1-based, in file order) to target one specific match. "
            "Prefer this over rewriting whole files."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path, e.g. utils.py"},
                "old_str": {"type": "string", "description": "Exact text to replace, including whitespace"},
                "new_str": {"type": "string", "description": "Replacement text"},
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace every occurrence of old_str instead of requiring a unique match.",
                },
                "occurrence": {
                    "type": "integer",
                    "description": "1-based index (in file order) of the specific occurrence to replace.",
                },
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
        "replace_all": args.replace_all,
        "occurrence": args.occurrence,
    })
    console.print(Panel(f"{args.path} → {out}", title="edit", border_style="yellow", title_align="left"))
    return out

TOOL = Tool("str_replace", StrReplaceArgs, DEFINITION, handler)
