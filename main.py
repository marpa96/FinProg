from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
API_URL = "http://127.0.0.1:8001/api/health"
REQUIREMENTS_PATH = ROOT / "requirements.txt"


def get_npm_command() -> str:
    npm_command = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm_command:
        raise RuntimeError("npm was not found on PATH. Install Node.js first.")
    return npm_command


def run_command(command: list[str]) -> int:
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return completed.returncode


def ensure_python_dependencies() -> int:
    if not REQUIREMENTS_PATH.exists():
        return 0

    missing_playwright = importlib.util.find_spec("playwright") is None
    missing_rich = importlib.util.find_spec("rich") is None
    if not missing_playwright and not missing_rich:
        return 0

    print("Installing Python dependencies from requirements.txt...")
    return run_command([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS_PATH)])


def ensure_playwright_browser() -> int:
    print("Ensuring Playwright Chromium browser is installed...")
    return run_command([sys.executable, "-m", "playwright", "install", "chromium"])


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
    parser.add_argument("--install-only", action="store_true", help="Only install Python and npm dependencies.")
    parser.add_argument("--dev", action="store_true", help="Start the Vite dev server after installing.")
    parser.add_argument("--build", action="store_true", help="Run the production build after installing.")
    parser.add_argument("--test", action="store_true", help="Run the Python source-of-truth test suite after installing.")
    parser.add_argument("--regression", action="store_true", help="Run the anti-regression harness after installing.")
    parser.add_argument("--api", action="store_true", help="Run only the Python forecast API.")
    parser.add_argument("--rocketmoney-login", action="store_true", help="Open browser login and refresh Rocket Money cookies.")
    parser.add_argument("--rocketmoney-update", action="store_true", help="Refresh Rocket Money cookies if needed and sync Rocket Money into the local database.")
    parser.add_argument("--rocketmoney-import-curls", action="store_true", help="Import Rocket Money cURL captures from data/private/rocketmoney_login_curls.txt into .env.")
    parser.add_argument("--rocketmoney-output", default="data/private/rocketmoney_transactions.json", help="Output path for Rocket Money transaction JSON.")
    parser.add_argument("--rocketmoney-database", default="data/private/rocketmoney.db", help="SQLite database path for Rocket Money data.")
    parser.add_argument(
        "--rocketmoney-detail-mode",
        choices=("quick", "full", "skip"),
        default="quick",
        help="Rocket Money detail enrichment mode: quick fetches missing details only, full refetches all, skip fetches none.",
    )
    parser.add_argument(
        "--rocketmoney-transaction-mode",
        choices=("quick", "full"),
        default="quick",
        help="Rocket Money transaction paging mode: quick stops at known history, full pages through everything.",
    )
    parser.add_argument(
        "--rocketmoney-detail-throttle-delay",
        type=float,
        default=900.0,
        help="Seconds Rocket Money deep sync should pause before resuming after 403/429/5xx pressure.",
    )
    parser.add_argument(
        "--rocketmoney-detail-request-delay",
        type=float,
        default=None,
        help="Seconds to wait between Rocket Money detail bundles.",
    )
    parser.add_argument("--max-pages", type=int, default=None, help="Optional Rocket Money page limit for extraction.")
    args = parser.parse_args()

    try:
      npm_command = get_npm_command()
    except RuntimeError as error:
      print(error)
      return 1

    python_install_code = ensure_python_dependencies()
    if python_install_code != 0:
        return python_install_code

    install_code = ensure_npm_dependencies()
    if install_code != 0:
        return install_code

    if args.install_only:
        print("Setup complete.")
        return 0

    if args.rocketmoney_import_curls:
        return run_command([sys.executable, "scripts/import_rocketmoney_curls.py"])

    if args.rocketmoney_login:
        browser_code = ensure_playwright_browser()
        if browser_code != 0:
            return browser_code
        return run_command([sys.executable, "scripts/browser_login_rocketmoney.py"])

    if args.rocketmoney_update:
        browser_code = ensure_playwright_browser()
        if browser_code != 0:
            return browser_code
        login_code = run_command([sys.executable, "scripts/browser_login_rocketmoney.py"])
        if login_code != 0:
            return login_code
        extract_command = [
            sys.executable,
            "scripts/sync_rocketmoney_database.py",
            "--no-refresh",
            "--database",
            args.rocketmoney_database,
            "--snapshot-output",
            args.rocketmoney_output,
            "--transaction-mode",
            args.rocketmoney_transaction_mode,
            "--detail-mode",
            args.rocketmoney_detail_mode,
            "--detail-throttle-delay",
            str(args.rocketmoney_detail_throttle_delay),
        ]
        if args.rocketmoney_detail_request_delay is not None:
            extract_command.extend(["--detail-request-delay", str(args.rocketmoney_detail_request_delay)])
        if args.max_pages is not None:
            extract_command.extend(["--max-pages", str(args.max_pages)])
        return run_command(extract_command)

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
