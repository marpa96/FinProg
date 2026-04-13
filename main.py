from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
API_URL = "http://127.0.0.1:8001/api/health"


def get_npm_command() -> str:
    npm_command = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm_command:
        raise RuntimeError("npm was not found on PATH. Install Node.js first.")
    return npm_command


def run_command(command: list[str]) -> int:
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return completed.returncode


def start_api_server() -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=ROOT,
        text=True,
    )


def wait_for_api(timeout_seconds: float = 10.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(API_URL, timeout=1) as response:  # noqa: S310
                return response.status == 200
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.2)
    return False


def ensure_npm_dependencies() -> int:
    print("Installing npm dependencies...")
    return run_command([get_npm_command(), "install"])


def main() -> int:
    parser = argparse.ArgumentParser(description="FinProg helper runner")
    parser.add_argument("--install-only", action="store_true", help="Only install npm dependencies.")
    parser.add_argument("--dev", action="store_true", help="Start the Vite dev server after installing.")
    parser.add_argument("--build", action="store_true", help="Run the production build after installing.")
    parser.add_argument("--test", action="store_true", help="Run the Python source-of-truth test suite after installing.")
    parser.add_argument("--regression", action="store_true", help="Run the anti-regression harness after installing.")
    parser.add_argument("--api", action="store_true", help="Run only the Python forecast API.")
    args = parser.parse_args()

    try:
      npm_command = get_npm_command()
    except RuntimeError as error:
      print(error)
      return 1

    install_code = ensure_npm_dependencies()
    if install_code != 0:
        return install_code

    if args.install_only:
        print("Setup complete.")
        return 0

    if args.api:
        print("Starting the Python API...")
        return run_command([sys.executable, "app.py"])

    if args.build:
        return run_command([npm_command, "run", "build"])

    if args.test:
        return run_command([npm_command, "test"])

    if args.regression:
        return run_command([sys.executable, "anti-regression/run_regression.py"])

    print("Starting the web app...")
    api_process = None
    if wait_for_api(timeout_seconds=0.5):
        print("Python API is already running.")
    else:
        api_process = start_api_server()
    try:
        if not wait_for_api():
            print("Python API did not become ready in time.")
            return 1
        return run_command([npm_command, "run", "dev", "--", "--open"])
    finally:
        if api_process is not None and api_process.poll() is None:
            api_process.terminate()
            try:
                api_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                api_process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
