from pydantic import BaseModel, field_validator
from rich.panel import Panel
from harness.tools.base import Tool, run_script, console

DOCKER_EXEC_TIMEOUT = 300  # run_tests can be slow; override sandbox's 60s default

class RunTestsArgs(BaseModel):
    tests: list[str]
    path: str = "."

    @field_validator("tests")
    @classmethod
    def _nonempty(cls, v):
        if not v or not all(isinstance(t, str) and t.strip() for t in v):
            raise ValueError('tests must be a non-empty list of test node ids; use ["all"] to run everything')
        return v

DEFINITION = {
    "type": "function",
    "function": {
        "name": "run_tests",
        "description": (
            "Run pytest and return structured pass/fail results (not raw stdout). "
            'tests is a list of node ids like "test_math.py::test_add", or the single '
            'element ["all"] to run everything under path. Result is JSON: '
            "summary counts, and passed/failed/errors/skipped lists of node ids, "
            "plus one-line failure_details per failing test."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tests": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": 'Test node ids, or ["all"] to run everything under path',
                },
                "path": {
                    "type": "string",
                    "description": 'Root to collect from when tests is ["all"] (default ".")',
                },
            },
            "required": ["tests"],
        },
    },
}

def handler(sandbox, args: RunTestsArgs) -> str:
    label = "all" if args.tests == ["all"] else f"{len(args.tests)} test(s)"
    console.print(Panel(f"{label}  ({args.path})", title="run_tests", border_style="red", title_align="left"))
    return run_script(
        sandbox, "run_tests.py",
        {"tests": args.tests, "path": args.path},
        timeout=DOCKER_EXEC_TIMEOUT,
    )

TOOL = Tool("run_tests", RunTestsArgs, DEFINITION, handler)
