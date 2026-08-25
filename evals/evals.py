import os, shutil, traceback, json, time
from harness.sandbox import Sandbox
from harness.utils import run_agent

from tasks import TASKS2, SEEDS2

def prepare(name):
    d = os.path.abspath(f"./eval_ws/{name}")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    
    for fname, content in SEEDS2.get(name, {}).items():
        with open(os.path.join(d, fname), "w") as f:
            f.write(content)
            
    return d

def log_run(name, messages, ok):
    with open("runs.jsonl", "a") as f:
        f.write(json.dumps({
            "ts":time.time(),
            "task":name,
            "ok":ok,
            "messages":[m if isinstance(m, dict) else m.model_dump() for m in messages]
        }, ensure_ascii=False) +"\n")

def main():
    passed = 0
    
    for name, task, check in TASKS2:
        workdir = prepare(name)
        s = Sandbox(workdir)
        
        try:
            _, messages = run_agent(task, s)
            ok = bool(check(s))
        except Exception:
            ok = False
            traceback.print_exc()
        finally:
            s.destroy()
        
        passed += ok
        log_run(name, messages, ok)
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    
    
    print(f"\n{passed}/{len(TASKS2)}")
    
if __name__ == "__main__":
    main()