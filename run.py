import sys
import select
from pathlib import Path
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from harness.sandbox import Sandbox
from harness.agent import Agent

console = Console()
WORKSPACE = Path(__file__).parent / "workspace"


def run():
    s = Sandbox(WORKSPACE)
    agent = Agent(s, max_turns=50)
    try:
        while True:
            task = read_multiline_input().strip()
            if task in ("exit", "quit", ""):
                break
            
            console.rule("[dim]agent[/]", style="dim")
            answer = agent.run(task)
            console.print(Markdown(answer))

            u = agent.usage
            console.print(
                f"[dim]{u.calls} calls · {u.prompt:,} in · {u.completion:,} out · ${u.cost:.4f}[/]"
            )
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        s.destroy()

def read_multiline_input(prompt="\n› "):
    console.print(prompt, end="", style="bold green")
    lines = []
    first = sys.stdin.readline()
    if not first:
        raise EOFError
    lines.append(first.rstrip("\n"))
    while select.select([sys.stdin], [], [], 0.05)[0]:
        line = sys.stdin.readline()
        if not line:
            break
        lines.append(line.rstrip("\n"))
    
    return "\n".join(lines)

if __name__ == "__main__":
    run()