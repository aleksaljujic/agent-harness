import json, shlex
from pydantic import BaseModel
from typing import Optional

#PYDANTCI CLASSES

class BashArgs(BaseModel):
    command: str
    
class SearchArgs(BaseModel):
    pattern: str
    glob: Optional[str] = None

class SrtReplaceArgs(BaseModel):
    path: str
    old_str: str
    new_str: str
    
#TOOLS
    
SCHEMAS = {
    "bash": BashArgs,
    "search": SearchArgs,
    "str_replace": SrtReplaceArgs,
}

TOOLS = [
    {
    "type":"function",
    "function":{
        "name":"bash",
        "description": "Executing bash command in /work and return stdout+stderr.",
        "parameters": {
            "type": "object",
            "properties": {
                "thought": {"type": "string", "description": "Why you run this command."},
                "command": {"type": "string"},
            },
            "required": ["thought","command"],
        },
    },
    },
    {
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
    },
    {
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
]

#TOOL FUNCTIONS

def do_search(sandbox, pattern, glob=None):
    include = f"--include={shlex.quote(glob)}" if glob else ""
    cmd = (
        f"grep -rn {include} --exclude-dir=.git --exclude-dir=node_modules "
        f"-E {shlex.quote(pattern)} . | head -50"
    )
    out = sandbox.run(cmd).strip()
    if not out or out.startswith("(no output)"):
        return "No matches."
    return out

def do_str_replace(sandbox, path, old_str, new_str): 
    payload = json.dumps({
        "path": path,
        "old": old_str,
        "new": new_str
    })
    return sandbox.run(
        f"printf %s {shlex.quote(payload)} | python3 /opt/agent-scripts/str_replace.py"
    )