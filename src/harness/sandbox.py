import os, subprocess, uuid
from pathlib import Path

from harness.config import settings, SCRIPTS

IMAGE = "agent-sandbox"
MEMORY = "2g"
PIDS = "256"
SANDBOX_TTL = 3600  # container self-destructs after this even if the harness process is killed


class Sandbox:
    def __init__(self, workdir):
        workdir = Path(workdir).resolve()
        workdir.mkdir(parents=True, exist_ok=True)
        if not os.access(workdir, os.W_OK):
            raise RuntimeError(f"workdir not writable: {workdir}")

        self.name = f"agent-{uuid.uuid4().hex[:8]}"
        p = subprocess.run([
            "docker", "run", "-d", "--rm", "--name", self.name,
            "--memory", MEMORY, "--pids-limit", PIDS,
            "--user", f"{os.getuid()}:{os.getgid()}",
            "-v", f"{workdir}:/work",
            "-v", f"{SCRIPTS.resolve()}:/opt/agent-scripts:ro",
            "-w", "/work",
            IMAGE, "sleep", str(SANDBOX_TTL)
        ], capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"docker run fail:\n{p.stderr}")
                
    def run(self, command, timeout=None):
        timeout = timeout if timeout is not None else settings.timeout
        try:
            p = subprocess.run(
                ["docker", "exec", self.name, "bash", "-lc", command],
                capture_output=True, text=True, timeout=timeout
            )
            return (p.stdout + p.stderr)[:8000] or f"Without return, exit = {p.returncode}"
        except subprocess.TimeoutExpired:
            return f"Error : exited after {timeout}s"
        
    def destroy(self):
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)
        
if __name__ == "__main__":
    s = Sandbox("./workspace")
    try:
        print(s.run("id -u && pwd && ls -la"))
        print(s.run("echo 'print(1+1)' > test.py && python test.py"))
    finally:
        s.destroy()