import json, shlex
from dataclasses import dataclass
from typing import Callable, Type
from pydantic import BaseModel
from rich.console import Console

console = Console()

@dataclass(frozen=True)
class Tool:
    name: str
    args_model: Type[BaseModel]
    definition: dict           
    handler: Callable          

def run_script(sandbox, script: str, payload: dict, timeout: int | None = None) -> str:
    data = json.dumps(payload)
    cmd = f"printf %s {shlex.quote(data)} | python3 /opt/agent-scripts/{script}"
    return sandbox.run(cmd, timeout=timeout) if timeout else sandbox.run(cmd)
