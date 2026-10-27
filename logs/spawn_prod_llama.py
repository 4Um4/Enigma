import subprocess
import sys
from pathlib import Path
import time

LLAMA_SERVER = r"C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\llama\llama-server.exe"
HERMES_PATH = r"C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\Hermes-3-Llama-3.1-8B.Q4_K_M.gguf"
LOG_DIR = Path(r"C:\DDD\Codex\VSC_Enigma\Enigma\logs")
LOG_DIR.mkdir(exist_ok=True)
STDOUT_LOG = LOG_DIR / "llama-server-prod.log"
STDERR_LOG = LOG_DIR / "llama-server-prod.err"

stdout_f = open(STDOUT_LOG, "w", encoding="utf-8", errors="replace")
stderr_f = open(STDERR_LOG, "w", encoding="utf-8", errors="replace")

args = [
    LLAMA_SERVER,
    "-m", HERMES_PATH,
    "--host", "127.0.0.1",
    "--port", "8181",
    "--ctx-size", "8192",
    "--n-gpu-layers", "99",
    "--jinja",
]

print("Spawning with args:")
for i, a in enumerate(args):
    print(f"  arg[{i}]: {a}")

proc = subprocess.Popen(
    args,
    stdout=stdout_f,
    stderr=stderr_f,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    close_fds=True,
)

# Wait 3s, check it didn't die immediately
time.sleep(3)
if proc.poll() is not None:
    print(f"FAILED: process exited immediately with code {proc.returncode}")
    stderr_f.close()
    with open(STDERR_LOG, "r", encoding="utf-8", errors="replace") as f:
        print("STDERR (last 2000 chars):")
        print(f.read()[-2000:])
    sys.exit(1)

print(f"OK: spawned PID={proc.pid}, still alive after 3s")
print(f"STDOUT log: {STDOUT_LOG}")
print(f"STDERR log: {STDERR_LOG}")
