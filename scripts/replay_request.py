"""Re-send a saved SWE-bench run's message list to diagnose a BadRequestError.

The harness persists every run's exact request payload to
`<experiment>/messages/<session_id>__<instance_id>__<run_index>.json` (see
evals/swebench/pipeline.py). When a run dies with `api_error`, feed that file
here to get the server's verbatim error body without re-running the agent.

Examples:
    python scripts/replay_request.py path/to/messages.json
    python scripts/replay_request.py path/to/messages.json --prefix 8
    python scripts/replay_request.py path/to/messages.json --bisect
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from openai import APIStatusError, OpenAI

from harness.config import settings
from harness.tools import get_active_tools


def _client() -> OpenAI:
    return OpenAI(api_key=settings.api_key, base_url=settings.endpoint, max_retries=0)


def _tool_end_index(messages: list[dict], cutoff: int) -> int:
    """Extend `cutoff` past any trailing tool replies whose assistant call it belongs to.

    A prefix must never end with an assistant message that has tool_calls but not
    all of the matching tool replies — that alone can produce a 400 that has
    nothing to do with the bug you're chasing.
    """
    i = cutoff
    while i < len(messages) and messages[i].get("role") == "tool":
        i += 1
    return i


def _send(client: OpenAI, model: str, messages: list[dict], tools: list[dict],
          reasoning_effort: str | None) -> None:
    kwargs = {"model": model, "messages": messages, "tools": tools}
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort
    else:
        kwargs["temperature"] = 0.0

    try:
        client.chat.completions.create(**kwargs)
        print(f"OK ({len(messages)} messages)")
    except APIStatusError as e:
        print(f"FAIL ({len(messages)} messages): status={e.status_code} "
              f"request_id={getattr(e, 'request_id', None)}")
        print("body:", json.dumps(e.body, indent=2, default=str) if e.body else None)
        text = getattr(getattr(e, "response", None), "text", None)
        if text:
            print("response.text:", text)
        raise


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("messages_json", help="path to a saved messages/<run>.json file")
    p.add_argument("--prefix", type=int, default=None,
                   help="send only the first N messages (extended past any dangling tool replies)")
    p.add_argument("--bisect", action="store_true",
                   help="binary-search the prefix length for the minimal failing payload")
    args = p.parse_args()

    payload = json.loads(Path(args.messages_json).read_text())
    model = payload["model"]
    messages = payload["messages"]
    reasoning_effort = payload.get("reasoning_effort") or None
    tools, _ = get_active_tools(payload.get("tools"))

    client = _client()

    if args.bisect:
        lo, hi = 1, len(messages)
        if not lo <= hi:
            raise SystemExit("nothing to bisect")
        first_failing = None
        while lo <= hi:
            mid = (lo + hi) // 2
            cutoff = _tool_end_index(messages, mid)
            try:
                _send(client, model, messages[:cutoff], tools, reasoning_effort)
                lo = mid + 1
            except APIStatusError:
                first_failing = cutoff
                hi = mid - 1
        if first_failing is None:
            print("\nNo prefix failed — the full transcript may only fail with later turns "
                  "not present in this file, or the failure is non-deterministic.")
        else:
            print(f"\nMinimal failing prefix: {first_failing} messages "
                  f"(message[{first_failing - 1}] = {messages[first_failing - 1].get('role')})")
        return

    cutoff = _tool_end_index(messages, args.prefix) if args.prefix is not None else len(messages)
    try:
        _send(client, model, messages[:cutoff], tools, reasoning_effort)
    except APIStatusError:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
