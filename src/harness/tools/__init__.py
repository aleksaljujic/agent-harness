from harness.tools.base import Tool, console
from harness.tools import bash, search, str_replace, read_file, find_file, run_tests

_TOOLS = [
    bash.TOOL,
    search.TOOL,
    str_replace.TOOL,
    read_file.TOOL,
    find_file.TOOL,
    run_tests.TOOL,
]

REGISTRY: dict[str, Tool] = {t.name: t for t in _TOOLS}
TOOLS = [t.definition for t in _TOOLS]
SCHEMAS = {t.name: t.args_model for t in _TOOLS}
HANDLERS = {t.name: t.handler for t in _TOOLS}

def get_active_tools(enabled: list[str] | None = None):
    if enabled is None:
        return TOOLS, SCHEMAS

    active_tools = [t for t in TOOLS if t["function"]["name"] in enabled]
    active_schemas = {k: v for k, v in SCHEMAS.items() if k in enabled}
    return active_tools, active_schemas
