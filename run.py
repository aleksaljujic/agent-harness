from harness.sandbox import Sandbox
from harness.agent import Agent
from pathlib import Path

WORKSPACE = Path(__file__).parent / "workspace"

print(WORKSPACE)

def run():
    s = Sandbox(WORKSPACE)
    agent = Agent(s, max_turns=50)
    try:
        while True:
            task = input("prompt: ")
            answer = agent.run(task)
            print(answer)
            
            print(f"""
                  In {agent.usage.calls} calss | 
                  Tokens: {agent.usage.prompt:,} in | {agent.usage.completion:,} out |
                  Cost: {agent.usage.cost:6f}$"
                  """)
    finally:
        s.destroy()
        
if __name__ == "__main__":
    run()