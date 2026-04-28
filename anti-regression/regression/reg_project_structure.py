from __future__ import annotations

import json
import subprocess
import sys

from common import ARTIFACT_DIR, PROJECT_ROOT, display_path, print_failures, print_pass, write_artifact


SCRIPT_NAME = "reg_project_structure"
LEDGER_IDS = ["EXT-001", "EXT-002", "EXT-003", "EXT-004", "EXT-005", "EXT-006", "EXT-007", "EXT-008", "EXT-009"]
EXPECTED = "Rocket Money extractor code has its own folder under extractors, can generate JSON through the mock request path, supports captured Auth0 login request fields, has a browser-backed login helper, can be run from main.py, can sync the full source plus transaction-detail/history data into one local SQLite database, can feed a consolidated finance database, and prints visible sync progress."


def main() -> int:
    rocket_money_dir = PROJECT_ROOT / "extractors" / "rocket_money"
    required_paths = [
        rocket_money_dir,
        rocket_money_dir / "__init__.py",
        rocket_money_dir / "csv_export.py",
        rocket_money_dir / "graphql.py",
        rocket_money_dir / "details.py",
        PROJECT_ROOT / "scripts" / "extract_rocketmoney_transactions.py",
        PROJECT_ROOT / "scripts" / "refresh_rocketmoney_cookie.py",
        PROJECT_ROOT / "scripts" / "import_rocketmoney_curls.py",
        PROJECT_ROOT / "scripts" / "browser_login_rocketmoney.py",
        PROJECT_ROOT / "scripts" / "sync_rocketmoney_database.py",
        PROJECT_ROOT / "requirements.txt",
        PROJECT_ROOT / "main.py",
        PROJECT_ROOT / "storage" / "rocketmoney_sqlite.py",
        PROJECT_ROOT / "storage" / "consolidated_finance_sqlite.py",
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

    output_path = ARTIFACT_DIR / "rocketmoney_regression_mock.json"
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

    db_path = ARTIFACT_DIR / "rocketmoney_regression.db"
    if db_path.exists():
        db_path.unlink()
    db_completed = subprocess.run(
        [
            sys.executable,
            "scripts/sync_rocketmoney_database.py",
            "--mock",
            "--database",
            str(db_path),
            "--snapshot-output",
            str(ARTIFACT_DIR / "rocketmoney_regression_snapshot.json"),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    db_artifact = write_artifact(
        SCRIPT_NAME,
        "db_sync.txt",
        f"STDOUT:\n{db_completed.stdout}\n\nSTDERR:\n{db_completed.stderr}\n\nCODE:{db_completed.returncode}",
    )
    if db_completed.returncode != 0 or not db_path.exists():
        failures.append(
            {
                "ledger_id": "EXT-006",
                "expected": "Rocket Money sync writes the full source into one local SQLite database.",
                "observed": f"DB sync exited {db_completed.returncode}; database exists: {db_path.exists()}.",
                "artifact": display_path(db_artifact),
            }
        )
    else:
        query_completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sqlite3; "
                    f"conn = sqlite3.connect(r'{db_path}'); "
                    "tx = conn.execute('SELECT COUNT(*) FROM rocketmoney_transactions').fetchone()[0]; "
                    "pages = conn.execute('SELECT COUNT(*) FROM rocketmoney_sync_pages').fetchone()[0]; "
                    "runs = conn.execute('SELECT COUNT(*) FROM rocketmoney_sync_runs').fetchone()[0]; "
                    "print(f'{tx},{pages},{runs}'); "
                    "conn.close()"
                ),
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if query_completed.returncode != 0:
            failures.append(
                {
                    "ledger_id": "EXT-006",
                    "expected": "The synced Rocket Money database can be queried for transactions, pages, and sync runs.",
                    "observed": f"Database query exited {query_completed.returncode}.",
                    "artifact": display_path(db_artifact),
                }
            )
        else:
            tx_count, page_count, run_count = [int(part) for part in query_completed.stdout.strip().split(",")]
            detail_query = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import sqlite3; "
                        f"conn = sqlite3.connect(r'{db_path}'); "
                        "detail = conn.execute('SELECT COUNT(*) FROM rocketmoney_transaction_details').fetchone()[0]; "
                        "related = conn.execute('SELECT COUNT(*) FROM rocketmoney_transaction_related').fetchone()[0]; "
                        "history = conn.execute('SELECT COUNT(*) FROM rocketmoney_transaction_monthly_history').fetchone()[0]; "
                        "print(f'{detail},{related},{history}'); "
                        "conn.close()"
                    ),
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            if tx_count != 3 or page_count != 2 or run_count != 1:
                failures.append(
                    {
                        "ledger_id": "EXT-006",
                        "expected": "Mock DB sync stores 3 transactions across 2 pages in one sync run.",
                        "observed": f"Query counts were transactions={tx_count}, pages={page_count}, runs={run_count}.",
                        "artifact": display_path(db_artifact),
                    }
                )
            elif detail_query.returncode != 0:
                failures.append(
                    {
                        "ledger_id": "EXT-007",
                        "expected": "The synced Rocket Money database can be queried for detail and history tables.",
                        "observed": f"Detail query exited {detail_query.returncode}.",
                        "artifact": display_path(db_artifact),
                    }
                )
            else:
                detail_count, related_count, history_count = [int(part) for part in detail_query.stdout.strip().split(",")]
                if detail_count != 3 or related_count != 6 or history_count != 6:
                    failures.append(
                        {
                            "ledger_id": "EXT-007",
                            "expected": "Mock DB sync stores per-transaction detail, related, and monthly history rows.",
                            "observed": f"Detail counts were details={detail_count}, related={related_count}, history={history_count}.",
                            "artifact": display_path(db_artifact),
                    }
                )

        consolidated_path = ARTIFACT_DIR / "finprog_consolidated_regression.db"
        if consolidated_path.exists():
            consolidated_path.unlink()
        consolidated_completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sqlite3; "
                    "from pathlib import Path; "
                    "from storage import ConsolidatedFinanceStore, sync_rocketmoney_to_consolidated; "
                    f"summary = sync_rocketmoney_to_consolidated(Path(r'{db_path}'), Path(r'{consolidated_path}')); "
                    "store = ConsolidatedFinanceStore(Path(r'" + str(consolidated_path) + "')); "
                    "conn = store.connect(); "
                    "store.ensure_schema(conn); "
                    "store.upsert_classification_rule(conn, {"
                    "'ruleId':'rule-rent','sourceId':'rocketmoney','matchField':'description',"
                    "'matchOperator':'contains','matchValue':'Rent','planningLabel':'Rent',"
                    "'normalizedType':'expense','cashflowClass':'fixed'}); "
                    "conn.commit(); "
                    "tx = conn.execute('SELECT COUNT(*) FROM finance_source_transactions').fetchone()[0]; "
                    "rules = conn.execute('SELECT COUNT(*) FROM finance_classification_rules').fetchone()[0]; "
                    "unit, sign, magnitude, planning, guess = conn.execute(\"SELECT source_amount_unit, source_amount_sign, normalized_magnitude_cents, planning_amount_cents, planning_type_guess FROM finance_source_transactions WHERE source_transaction_id = 'rocket_mock_0'\").fetchone(); "
                    "expense_sign, income_sign = conn.execute(\"SELECT expense_sign, income_sign FROM finance_sources WHERE source_id = 'rocketmoney'\").fetchone(); "
                    "print(f'{summary[\"sourceTransactionCount\"]},{tx},{rules},{unit},{sign},{magnitude},{planning},{guess},{expense_sign},{income_sign}'); "
                    "conn.close()"
                ),
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if consolidated_completed.returncode != 0:
            failures.append(
                {
                    "ledger_id": "EXT-009",
                    "expected": "Rocket Money rows can feed the consolidated finance database and store user classification rules.",
                    "observed": f"Consolidated sync exited {consolidated_completed.returncode}: {consolidated_completed.stderr}",
                    "artifact": display_path(db_artifact),
                }
            )
        else:
            source_count, consolidated_count, rule_count, unit, sign, magnitude, planning, guess, expense_sign, income_sign = consolidated_completed.stdout.strip().split(",")
            if (
                int(source_count),
                int(consolidated_count),
                int(rule_count),
                unit,
                sign,
                int(magnitude),
                int(planning),
                guess,
                expense_sign,
                income_sign,
            ) != (3, 3, 1, "cents", "negative", 180000, 180000, "income", "positive", "negative"):
                failures.append(
                    {
                        "ledger_id": "EXT-009",
                        "expected": "Consolidated DB preserves source rows, source sign convention, amount units/signs/magnitudes, planning direction, and classification rules.",
                        "observed": consolidated_completed.stdout.strip(),
                        "artifact": display_path(db_artifact),
                    }
                )

    sync_source = (PROJECT_ROOT / "scripts" / "sync_rocketmoney_database.py").read_text(encoding="utf-8")
    progress_markers = [
        "Starting Rocket Money transaction extraction...",
        "Fetched transaction page",
        "Fetching transaction details for",
        "Fetched detail bundle",
        "Writing sync results into SQLite database",
    ]
    missing_progress_markers = [marker for marker in progress_markers if marker not in sync_source]
    if missing_progress_markers:
        failures.append(
            {
                "ledger_id": "EXT-008",
                "expected": "Rocket Money sync prints visible extraction, enrichment, and database progress.",
                "observed": f"Missing progress markers: {missing_progress_markers}.",
                "artifact": display_path(db_artifact),
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
        "--rocketmoney-database",
        "ensure_python_dependencies",
        "ensure_playwright_browser",
        "scripts/sync_rocketmoney_database.py",
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
        "Rocket Money extractor package exists under extractors, mock extraction generated JSON, and mock sync generated a local SQLite database.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
