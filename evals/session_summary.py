import json

def summarize(path="runs.jsonl"):
    total_cost = 0.0
    total_prompt = 0
    total_completion = 0
    by_task = {}

    with open(path) as f:
        for line in f:
            entry = json.loads(line)
            u = entry["usage"]
            total_cost += u["cost"]
            total_prompt += u["prompt"]
            total_completion += u["completion"]
            by_task.setdefault(entry["task"], []).append(u["cost"])

    print(f"Total: {total_prompt:,} in · {total_completion:,} out · ${total_cost:.4f}")
    for task, costs in by_task.items():
        avg = sum(costs) / len(costs)
        print(f"  {task}: avg ${avg:.4f} over {len(costs)} runs")

if __name__ == "__main__":
    summarize()