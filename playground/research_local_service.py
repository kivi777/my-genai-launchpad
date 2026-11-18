"""Run the local research API and Worker from the Launchpad service controls."""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def run(role: str, port: int) -> None:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / "docker" / ".env")
    if role == "worker":
        from launchpad.worker.config import celery_app

        redis_url = os.environ["RESEARCH_LOCAL_REDIS_URL"]
        celery_app.conf.update(broker_url=redis_url, result_backend=redis_url)
        celery_app.worker_main(["worker", "--pool=solo", "--loglevel=info"])
    else:
        import uvicorn
        from launchpad.worker.config import celery_app

        redis_url = os.environ["RESEARCH_LOCAL_REDIS_URL"]
        celery_app.conf.update(broker_url=redis_url, result_backend=redis_url)
        uvicorn.run("launchpad.main:app", host="127.0.0.1", port=port)


def supervise(port: int) -> int:
    parent = os.getppid()
    stopping = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)

    children = []
    try:
        for role in ("worker", "api"):
            children.append(
                subprocess.Popen([sys.executable, __file__, str(port), "--role", role])
            )
        while not stopping and os.getppid() == parent:
            if any(child.poll() is not None for child in children):
                return 1
            time.sleep(0.25)
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=35)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("port", type=int)
    parser.add_argument("--role", choices=("worker", "api"))
    args = parser.parse_args()
    if args.role:
        run(args.role, args.port)
    else:
        sys.exit(supervise(args.port))
