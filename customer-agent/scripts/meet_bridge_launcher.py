#!/usr/bin/env python3
"""Launcher for AgentCall meeting bridge."""
import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables
for env_path in (BASE_DIR / ".env", BASE_DIR / "customer-agent" / ".env"):
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k.strip(), v.strip("\"'"))

meeting_url = sys.argv[1] if len(sys.argv) > 1 else "https://meet.google.com/zoo-zhnm-itj"
name = sys.argv[2] if len(sys.argv) > 2 else "Horus AI"

events_file = BASE_DIR / "meeting-events.jsonl"
commands_file = BASE_DIR / "meeting-commands.jsonl"

events_file.touch()
commands_file.touch()

bridge_script = BASE_DIR / ".agents" / "skills" / "join-meeting" / "scripts" / "python" / "bridge.py"
python_bin = BASE_DIR / ".venv" / "bin" / "python"

print(f"Launching meeting bridge for {meeting_url} as {name}...")
cmd = [
    str(python_bin),
    str(bridge_script),
    meeting_url,
    "--name", name,
    "--voice", "af_heart",
    "--output", str(events_file)
]

# We need commands_file piped to stdin
tail_proc = subprocess.Popen(["tail", "-n", "0", "-f", str(commands_file)], stdout=subprocess.PIPE)
try:
    bridge_proc = subprocess.Popen(cmd, stdin=tail_proc.stdout, env=os.environ)
    bridge_proc.wait()
finally:
    tail_proc.terminate()
