# Building a coding agent harness

Notes from building `harness` — what the parts are, why they're shaped this way, and
what turned out to be true in practice.

---

## 1. The agent is a loop

The whole agent fits in about fifteen lines:

```python
for _ in range(max_turns):
    resp = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
    msg = resp.choices[0].message
    messages.append(msg)

    if not msg.tool_calls:
        return msg.content

    for tc in msg.tool_calls:
        out = dispatch(tc)
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})
```

The model never executes anything. It returns JSON describing a call it would like
made; the loop decides whether to make it. Autonomy is not a property of the model —
it is the absence of an `input()` on that one line.

Everything else in this repo is the harness: what the model is allowed to do, what it
can reach, what it sees, and what that costs.

## 2. Sandbox: the boundary is a path that doesn't exist

The container runs `sleep infinity` in the background and receives commands via
`docker exec`. State persists between calls, which is what lets the agent build
something across several steps.

`workspace/` on the host is bind-mounted to `/work` in the container. This is not a
copy and not a sync — the same inodes under two names. A write inside the container
is a write to the host disk, immediately.

The important consequence: everything outside that mount **does not exist** inside
the container. `~/.ssh` isn't forbidden, it has no path. This is the difference
between a rule and a boundary. A rule in a prompt is a bet that the model remembers
it. A missing path is not a bet.

Flags that earn their place:

- `--user $(id -u):$(id -g)` — files belong to you, not root. Skip this and Docker
  writes root-owned files into your project that you can't delete without `sudo`.
- `--pids-limit` — a badly written shell loop is a fork bomb, and agents write those
  more often than you'd expect.
- `--memory` — same reasoning.
- `:ro` on the scripts mount — the agent cannot modify its own tooling.

What Docker does not protect against: the agent destroying files *inside* the mount.
That's the permission you granted. The answer there is git, not a flag — commit before
each run and `git checkout` is a two-second recovery.

## 3. Tools: fewer than expected, and mostly about output

Three tools cover the space:

| Tool | Why it exists |
|---|---|
| `bash` | One tool, one parameter, the entire Linux userland |
| `search` | `grep` with the output capped and noise directories excluded |
| `str_replace` | Edit a file without regenerating it |

`bash` alone is startlingly capable — the model composes pipes, redirects, and `&&`
chains that no hand-designed tool list would have anticipated. The instinct to add
twenty specialized tools is wrong; each one is another chance to choose badly, and
another block of tokens in every single request.

Note what `search` actually adds. The model can already run `grep`. The value is that
the harness controls the output: 50 hits maximum, `.git` and `node_modules` excluded.
A raw `grep -r` on a real repository returns a wall of text and eats the context
window in one call. The tool doesn't add capability, it subtracts output.

`str_replace` is the exception — it adds something bash genuinely does badly. `sed`
works line by line, so it can't touch a multi-line block; every regex metacharacter in
the code needs escaping; and `sed -i` on a pattern that occurs five times silently
edits all five. The implementation reads the whole file in Python, does a literal
`str.replace`, and refuses unless the snippet appears exactly once.

Two details worth keeping:

**Literal, not regex.** The model sends a snippet of code as `old_str`, and code is
full of `.`, `*`, `(`, `[`. Literal matching means none of it needs escaping.

**The uniqueness check is the safety property.** Without it you get silent wrong
edits, which are worse than errors.

## 4. Tool output is a prompt

This turned out to be the single most useful idea in the project.

Every string a tool returns is an instruction about what to do next. It is not
diagnostics for a human — the model has that sentence and nothing else.

Observed directly. `str_replace` returned:

```
ERROR: old_str appears 2 times, must be unique. Include more surrounding lines.
```

The model read it, ran `nl -ba` to look at the context around both occurrences, and
sent two new calls with enough surrounding text to disambiguate each. No
intervention.

Compare with what an earlier version of the sandbox returned for an empty result:

```
Without return, exit = 0
```

That says nothing. Did the search succeed and find nothing, or did the tool break?
The model retried the same search, then abandoned the tool and fell back to bash.
Changing that string to `No matches.` changed the behaviour.

Rewriting error messages is prompt engineering that happens to live in a `try` block.

## 5. Evals: check the sandbox, not the answer

Nine tasks, each in a fresh container with a fresh workspace, with a seeded starting
state where the task needs one.

The rule that matters: **verify by inspecting the sandbox afterwards, never by reading
what the model said.** Models routinely report success on files they never wrote.

```python
("syntax", "The script calc.py won't run. Fix it so it prints 42.",
 lambda s: s.run("python calc.py").strip() == "42"),
```

Two failure modes showed up immediately, and both were the eval's fault rather than
the model's:

**A check that measures only the consequence passes when nothing happened.** The
`refactor` task checked that the script still printed `7` and `12`. The model read the
file three times, changed nothing, and passed — the original already printed that. The
fix was to also assert `"def "` appears in the file.

**A check can fail on the environment rather than the work.** The `pytest` task kept
failing. The model was writing correct code every time; pytest just wasn't installed
in the image. That line was pure noise until the Dockerfile changed.

Also: three runs of the identical code gave 8, 7, and 8. A one-task difference between
runs is variance, not signal. Average over several runs before believing anything.

## 6. Cost is where the harness pays for itself

The API returns `usage` on every response. Accumulating it takes three lines and
changes how you see the system.

The same edit task, measured before and after `str_replace` worked:

| | Input tokens | Output tokens |
|---|---|---|
| Rewriting the file with `cat > file` | 32,332 | 826 |
| Two `str_replace` calls | 7,586 | 371 |

Four times cheaper for identical output. Nothing about the model changed.

Input tokens grow **quadratically** with turn count — on the tenth call you are
paying for the full history of the previous nine, again. This is why output
truncation (`[:8000]` on command output) and hit caps on search are not cosmetic
details. They are the cost model.

This also matches what the literature reports: harness choice moves cost by up to 40x
while moving pass rates by 0–8 percentage points with confidence intervals crossing
zero. The harness does not make a weak model smart. It decides what a smart model
costs.

## 7. Getting the model to choose the right tool

Adding `str_replace` did nothing at first. The model kept rewriting whole files with
`cat > file`, because from its point of view one call beats five and it cannot see the
token bill.

The fix was in the system prompt, not the tool description:

```
When creating a NEW file, use bash with a heredoc.
When modifying an EXISTING file, you MUST use str_replace for each change.
Never rewrite a file that already exists — rewriting risks losing code and wastes tokens.
Multiple str_replace calls are expected and preferred over one full rewrite.
```

The load-bearing sentence is the last one. Without explicitly saying that several
calls are *expected*, the model optimizes for fewest calls.

And the tool should not always win. Asked to rename a character appearing nine times
throughout a document, the model wrote a Python heredoc doing a global `replace()` —
the correct choice. `str_replace` is for localized edits; forcing it everywhere would
be worse.

## 8. Things that cost hours

Recorded because none of them announced themselves.

**Docker silently creates a missing mount directory, as root.** Point the sandbox at a
path that doesn't exist and you get no error — just an empty, root-owned directory,
and then `Permission denied` on every write from a container running as UID 1000. The
symptom looks like a broken tool. Three lines in `Sandbox.__init__` fix it permanently:

```python
workdir = Path(workdir).resolve()
workdir.mkdir(parents=True, exist_ok=True)
if not os.access(workdir, os.W_OK):
    raise RuntimeError(f"workdir not writable: {workdir}")
```

`os.makedirs` from Python creates the directory as *you*, so Docker never has to
invent it.

**Relative paths resolve against the working directory, not the file.** `./workspace`
means something different depending on where you launched from, which produced several
stray empty workspaces in subdirectories. Anchor everything to the project root:

```python
ROOT = Path(__file__).parent.parent.parent
```

**`capture_output=True` hides the error you need.** `check=True` on a failing
`docker run` raises `CalledProcessError: exit status 1` and nothing else. Checking
`returncode` and raising with `p.stderr` turned an opaque failure into a one-line
answer.

**A tool returning `None` fails one call later.** The API rejects a `tool` message with
null content, so the traceback points at `client.chat.completions.create` — far from
the function that forgot its `return`. Coerce at the boundary:

```python
content = str(out) if out is not None else "(no output)"
```

**Host paths and container paths are different things.** Using the host-side scripts
path inside a container command produced
`/home/user/.../scripts/opt/agent-scripts/str_replace.py` — two paths concatenated. The
mount source belongs in `sandbox.py`; the mount target is what tool implementations
use.

## 9. Model behaviour worth noting

Collected from transcripts. Specific to a small model, but the categories generalize.

**It has habits from other harnesses.** Asked to refactor a file, it attempted
`apply_patch` with `*** Begin Patch` syntax — a tool from the harness it was trained
in, which does not exist here. When that failed it fell back to `cat > file`. Practical
implication: an edit tool that resembles what the model already expects will be adopted
faster than an invented format.

**It avoids installing packages.** Across many sessions it never once tried
`pip install pytest`, even with network access available. It wrote its own test runner
instead. Consistent enough to be a property rather than chance.

**It defaults to conversation.** "Make me a calculator script" got a code block in the
reply and no tool call at all. "Make script calc.py and put a calculator in it" got a
file. The system prompt has to say explicitly: write files, don't paste code.

**Failure behaviour is good.** Given an unwritable directory it tried twice, then ran
`ls -ld .` and `touch testfile` to diagnose, then stopped and explained the problem
instead of looping. Given an ambiguous edit it read more context and retried. This is
what makes error messages worth writing carefully — there is something on the other
side that reads them.

**It self-corrects mid-task.** A first attempt at concatenating `*.txt` files caught
the output file in its own glob; the model noticed and reran with
`! -name 'merged.txt'`.

## 10. What's next

In order of expected value:

1. **Context compaction.** `messages` grows without bound; long tasks will hit the
   limit mid-run. Summarize older turns, keep the last N verbatim.
3. **Repeat detection.** The same call with the same arguments three times means stuck.
   Break, or return a different message so the loop has something new to react to.
4. **A held-out eval set.** The current nine tasks are the ones the system was tuned
   against. Any improvement measured on them is suspect. A second set the harness never
   sees during development is the only instrument that distinguishes learning from
   overfitting.

Notably absent: more tools. The transcripts have not shown a gap that bash can't
cover. The remaining wins are all in the loop.
