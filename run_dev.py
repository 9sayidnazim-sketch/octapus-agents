#!/usr/bin/env python3
import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PYTHON = ROOT / ".venv" / "bin" / "python3"
UVICORN = ROOT / ".venv" / "bin" / "uvicorn"

if not UVICORN.exists():
    UVICORN = "uvicorn"


def run():
    parser = argparse.ArgumentParser(description="Octapus Agents Dev Server Runner")
    parser.add_argument(
        "--app",
        choices=["all", "customer", "staff", "bridge"],
        default="all",
        help="Which agent to run (default: all)",
    )
    parser.add_argument("--customer-port", type=int, default=8000, help="Port for customer agent")
    parser.add_argument("--staff-port", type=int, default=8001, help="Port for staff assistant")
    parser.add_argument("--with-bridge", action="store_true", help="Also start WhatsApp Orbit bridge on port 3000")
    args = parser.parse_args()

    procs = []

    def cleanup(*_):
        print("\nShutting down dev servers...")
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            p.wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    if args.app in ("all", "customer"):
        cmd = [str(UVICORN), "app:app", "--reload", "--port", str(args.customer_port)]
        p = subprocess.Popen(cmd, cwd=str(ROOT / "customer-agent"))
        procs.append(p)
        print(f"🚀 Customer Agent running at: http://localhost:{args.customer_port}")

    if args.app in ("all", "staff"):
        cmd = [str(UVICORN), "app:app", "--reload", "--port", str(args.staff_port)]
        p = subprocess.Popen(cmd, cwd=str(ROOT / "staff-assistant"))
        procs.append(p)
        print(f"🔒 Staff Assistant running at: http://localhost:{args.staff_port}")

    if args.app == "bridge" or args.with_bridge:
        cmd = ["node", "whatsapp-bridge.js"]
        p = subprocess.Popen(cmd, cwd=str(ROOT))
        procs.append(p)
        print("📲 WhatsApp / Orbit Gateway Bridge running at: http://localhost:3000")

    print("Press Ctrl+C to stop.\n")

    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    run()
