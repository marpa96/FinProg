from __future__ import annotations

import json
import subprocess
import sys

from common import PROJECT_ROOT, display_path, print_failures, print_pass, write_artifact


SCRIPT_NAME = "reg_project_structure"
LEDGER_IDS = ["EXT-001", "EXT-002", "EXT-003", "EXT-004", "EXT-005"]
EXPECTED = "Rocket Money extractor code has its own folder under extractors, can generate JSON through the mock request path, supports captured Auth0 login request fields, has a browser-backed login helper, and can be run from main.py."


def main() -> int:
    rocket_money_dir = PROJECT_ROOT / "extractors" / "rocket_money"
    required_paths = [
        rocket_money_dir,
        rocket_money_dir / "__init__.py",
        rocket_money_dir / "csv_export.py",
        rocket_money_dir / "graphql.py",
        PROJECT_ROOT / "scripts" / "extract_rocketmoney_transactions.py",
        PROJECT_ROOT / "scripts" / "refresh_rocketmoney_cookie.py",
        PROJECT_ROOT / "scripts" / "import_rocketmoney_curls.py",
        PROJECT_ROOT / "scripts" / "browser_login_rocketmoney.py",
        PROJECT_ROOT / "requirements.txt",
        PROJECT_ROOT / "main.py",
    ]
    missing = [path for path in required_paths if not path.exists()]

    failures = []
    if missing:
        failures.append(
            {
                "ledger_id": "EXT-001",
                "expected": "Rocket Money extractor package exists under extractors with CSV and GraphQL extractor starters.",
                "observed": f"Missing paths: {[display_path(path) for path in missing]}.",
                "artifact": "anti-regression/regression_artifacts/reg_project_structure__run.txt",
            }
        )

    output_path = PROJECT_ROOT / "data" / "private" / "rocketmoney_regression_mock.json"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/extract_rocketmoney_transactions.py",
            "--mock",
            "--output",
            str(output_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    artifact = write_artifact(
        SCRIPT_NAME,
        "mock_extract.txt",
        f"STDOUT:\n{completed.stdout}\n\nSTDERR:\n{completed.stderr}\n\nCODE:{completed.returncode}",
    )
    if completed.returncode != 0 or not output_path.exists():
        failures.append(
            {
                "ledger_id": "EXT-002",
                "expected": "Mock Rocket Money request pagination writes a JSON extraction file.",
                "observed": f"Mock extraction exited {completed.returncode}; output exists: {output_path.exists()}.",
                "artifact": display_path(artifact),
            }
        )
    else:
        extracted = json.loads(output_path.read_text(encoding="utf-8"))
        transaction_count = extracted.get("metadata", {}).get("transactionCount")
        page_count = extracted.get("metadata", {}).get("pageCount")
        if transaction_count != 3 or page_count != 2:
            failures.append(
                {
                    "ledger_id": "EXT-002",
                    "expected": "Mock Rocket Money JSON includes 3 transactions across 2 request pages.",
                    "observed": f"metadata.transactionCount={transaction_count}; metadata.pageCount={page_count}.",
                    "artifact": display_path(artifact),
                }
            )

    refresh_source = (PROJECT_ROOT / "scripts" / "refresh_rocketmoney_cookie.py").read_text(encoding="utf-8")
    importer_source = (PROJECT_ROOT / "scripts" / "import_rocketmoney_curls.py").read_text(encoding="utf-8")
    captured_env_markers = [
        "ROCKETMONEY_AUTH_LOGIN_URL",
        "ROCKETMONEY_AUTH_COOKIE",
        "ROCKETMONEY_AUTH_STATE",
        "ROCKETMONEY_ULP_ANONYMOUS_ID",
        "ROCKETMONEY_COOKIE",
        "ROCKETMONEY_ANALYTICS_SESSION",
    ]
    missing_markers = [marker for marker in captured_env_markers if marker not in refresh_source and marker not in importer_source]
    if missing_markers:
        failures.append(
            {
                "ledger_id": "EXT-003",
                "expected": "Cookie refresh supports captured Auth0 login request fields from env.",
                "observed": f"Refresh script was missing markers: {missing_markers}.",
                "artifact": display_path(artifact),
            }
        )

    browser_source = (PROJECT_ROOT / "scripts" / "browser_login_rocketmoney.py").read_text(encoding="utf-8")
    browser_markers = [
        "launch_persistent_context",
        "ROCKETMONEY_COOKIE",
        "rocketmoney_browser_profile",
        "playwright",
    ]
    missing_browser_markers = [marker for marker in browser_markers if marker not in browser_source]
    if missing_browser_markers:
        failures.append(
            {
                "ledger_id": "EXT-004",
                "expected": "Browser-backed login helper uses a persistent browser profile and updates ROCKETMONEY_COOKIE.",
                "observed": f"Missing browser helper markers: {missing_browser_markers}.",
                "artifact": display_path(artifact),
            }
        )

    requirements_source = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    main_source = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
    runner_markers = [
        "playwright",
        "--rocketmoney-update",
        "--rocketmoney-login",
        "ensure_python_dependencies",
        "ensure_playwright_browser",
        "scripts/extract_rocketmoney_transactions.py",
    ]
    missing_runner_markers = [
        marker for marker in runner_markers
        if marker not in requirements_source and marker not in main_source
    ]
    if missing_runner_markers:
        failures.append(
            {
                "ledger_id": "EXT-005",
                "expected": "requirements.txt and main.py install dependencies and expose one-command Rocket Money updating.",
                "observed": f"Missing runner/dependency markers: {missing_runner_markers}.",
                "artifact": display_path(artifact),
            }
        )

    if failures:
        return print_failures(SCRIPT_NAME, LEDGER_IDS, EXPECTED, failures)

    return print_pass(
        SCRIPT_NAME,
        LEDGER_IDS,
        EXPECTED,
        "Rocket Money extractor package exists under extractors and mock request extraction generated JSON.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
