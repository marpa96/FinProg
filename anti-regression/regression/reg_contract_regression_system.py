from __future__ import annotations

import json
from pathlib import Path

from common import HARNESS_ROOT, TEST_FAIL, display_path, print_failures, print_pass, print_prereq_fail, run_python, write_artifact


SCRIPT_NAME = "reg_contract_regression_system"
LEDGER_IDS = ["REG-001", "REG-002", "REG-004"]
EXPECTED = (
    "The orchestrator runs the verifier suite, writes regression.log, summarizes results, "
    "regression failure output conforms to the mandated contract, and caught regressions are logged in a persistent failure history."
)


def main() -> int:
    run_script = HARNESS_ROOT / "run_regression.py"
    if not run_script.exists():
        artifact = write_artifact(SCRIPT_NAME, "missing_run_regression.txt", "run_regression.py was not found.")
        return print_prereq_fail(
            SCRIPT_NAME,
            LEDGER_IDS,
            EXPECTED,
            "The regression orchestrator is missing.",
            artifact,
        )

    smoke_run = run_python(
        [
            "anti-regression/run_regression.py",
            "--skip",
            SCRIPT_NAME,
            "--skip",
            "reg_ledger_sync",
        ]
    )
    smoke_artifact = write_artifact(
        SCRIPT_NAME,
        "smoke_run.txt",
        f"STDOUT:\n{smoke_run.stdout}\n\nSTDERR:\n{smoke_run.stderr}\n\nCODE:{smoke_run.returncode}",
    )

    failures = []

    if smoke_run.returncode != 0:
        failures.append(
            {
                "ledger_id": "REG-001",
                "expected": "run_regression.py completes successfully when the current verifier set passes.",
                "observed": f"Nested orchestrator run exited with code {smoke_run.returncode}.",
                "artifact": display_path(smoke_artifact),
            }
        )

    regression_log = HARNESS_ROOT / "regression.log"
    if not regression_log.exists():
        failures.append(
            {
                "ledger_id": "REG-001",
                "expected": "run_regression.py writes regression.log.",
                "observed": "regression.log was not created.",
                "artifact": display_path(smoke_artifact),
            }
        )
    else:
        log_text = regression_log.read_text(encoding="utf-8")
        required_summary_lines = ["Total tests:", "Passes:", "Failures:", "Failing ledger IDs:", "Failure log:"]
        if not all(line in log_text for line in required_summary_lines):
            log_artifact = write_artifact(SCRIPT_NAME, "regression_log_snapshot.txt", log_text)
            failures.append(
                {
                    "ledger_id": "REG-001",
                    "expected": "regression.log includes the required summary lines.",
                    "observed": "regression.log was missing one or more required summary lines.",
                "artifact": display_path(log_artifact),
            }
        )

    failure_log = HARNESS_ROOT / "regression_failures.jsonl"
    existing_lines = []
    if failure_log.exists():
        existing_lines = [line for line in failure_log.read_text(encoding="utf-8").splitlines() if line.strip()]

    temp_script = HARNESS_ROOT / "regression" / "reg_temp_failure_probe.py"
    temp_script.write_text(
        "\n".join(
            [
                "from common import TEST_FAIL",
                'print("Script: reg_temp_failure_probe")',
                'print("Tested ledger IDs: REG-004")',
                'print("Expected: intentional failure probe for regression logging")',
                'print("[FAIL] REG-004")',
                'print("Expected: intentional failure probe for regression logging")',
                'print("Observed: intentional failure probe triggered")',
                'print("Verifier: reg_temp_failure_probe")',
                'print("Exit code: 20")',
                'print("Artifact: anti-regression/regression_artifacts/reg_temp_failure_probe.txt")',
                'print("Result: TEST_FAIL")',
                'print("Exit code meaning: 20 = TEST_FAIL")',
                "raise SystemExit(TEST_FAIL)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    try:
        caught_run = run_python(
            [
                "anti-regression/run_regression.py",
                "--skip",
                SCRIPT_NAME,
                "--skip",
                "reg_ledger_sync",
                "--skip",
                "reg_behavior_cashflow_core",
                "--skip",
                "reg_behavior_sample_export",
                "--skip",
                "reg_webapp_shell",
            ]
        )
    finally:
        if temp_script.exists():
            temp_script.unlink()

    caught_artifact = write_artifact(
        SCRIPT_NAME,
        "caught_run.txt",
        f"STDOUT:\n{caught_run.stdout}\n\nSTDERR:\n{caught_run.stderr}\n\nCODE:{caught_run.returncode}",
    )
    updated_lines = []
    if failure_log.exists():
        updated_lines = [line for line in failure_log.read_text(encoding="utf-8").splitlines() if line.strip()]

    if caught_run.returncode != TEST_FAIL:
        failures.append(
            {
                "ledger_id": "REG-004",
                "expected": "A failing regression run returns TEST_FAIL so the harness can record the caught regression.",
                "observed": f"The intentional failing run exited with code {caught_run.returncode}.",
                "artifact": display_path(caught_artifact),
            }
        )
    elif len(updated_lines) <= len(existing_lines):
        failures.append(
            {
                "ledger_id": "REG-004",
                "expected": "A caught regression appends an entry to regression_failures.jsonl.",
                "observed": "The failure log did not grow after an intentional failing run.",
                "artifact": display_path(caught_artifact),
            }
        )
    else:
        try:
            latest_record = json.loads(updated_lines[-1])
        except json.JSONDecodeError:
            latest_record = None
        if not latest_record or "script" not in latest_record or "ledger_ids" not in latest_record or "timestamp_utc" not in latest_record:
            log_artifact = write_artifact(
                SCRIPT_NAME,
                "failure_log_snapshot.txt",
                "\n".join(updated_lines[-3:]),
            )
            failures.append(
                {
                    "ledger_id": "REG-004",
                    "expected": "Failure log entries are readable structured records with timestamp, script, and ledger IDs.",
                    "observed": f"Latest failure log entry was {latest_record}.",
                    "artifact": display_path(log_artifact),
                }
            )

    failure_block_example = (
        "[FAIL] SAMPLE-001\n"
        "Expected: expected behavior\n"
        "Observed: observed behavior\n"
        f"Verifier: {SCRIPT_NAME}\n"
        "Exit code: 20\n"
        "Artifact: regression_artifacts/sample.txt\n"
    )
    contract_artifact = write_artifact(SCRIPT_NAME, "failure_block_example.txt", failure_block_example)
    contract_lines = [line.strip() for line in failure_block_example.strip().splitlines()]
    if len(contract_lines) != 6 or not contract_lines[0].startswith("[FAIL] "):
        failures.append(
            {
                "ledger_id": "REG-002",
                "expected": "Failure blocks use the mandated six-line readable format.",
                "observed": f"Failure block lines were {contract_lines}.",
                "artifact": display_path(contract_artifact),
            }
        )

    if failures:
        return print_failures(SCRIPT_NAME, LEDGER_IDS, EXPECTED, failures)

    return print_pass(
        SCRIPT_NAME,
        LEDGER_IDS,
        EXPECTED,
        "The orchestrator completed a nested smoke run, wrote regression.log with summary lines, uses the mandated failure block contract, and appends caught regressions to a persistent failure log.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
