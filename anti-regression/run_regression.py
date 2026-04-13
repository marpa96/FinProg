from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict


PASS = 0
PREREQ_FAIL = 10
TEST_FAIL = 20

HARNESS_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = HARNESS_ROOT.parent
REGRESSION_DIR = HARNESS_ROOT / "regression"
ARTIFACT_DIR = HARNESS_ROOT / "regression_artifacts"
LOG_PATH = HARNESS_ROOT / "regression.log"
COVERAGE_PATH = HARNESS_ROOT / "regression_coverage.txt"
FAILURE_LOG_PATH = HARNESS_ROOT / "regression_failures.jsonl"


class RegressionResult(TypedDict):
    script: str
    returncode: int
    stdout: str
    stderr: str
    ledger_ids: list[str]
    artifact: str


def parse_ledger() -> list[dict[str, str]]:
    ledger_path = HARNESS_ROOT / "feature_ledger.txt"
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw_line in ledger_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                entries.append(current)
                current = {}
            continue
        key, _, value = line.partition(":")
        current[key.strip()] = value.strip()
    if current:
        entries.append(current)
    return entries


def discover_scripts(skip_names: set[str]) -> list[Path]:
    scripts = []
    for path in sorted(REGRESSION_DIR.glob("reg_*.py")):
        if path.name in skip_names or path.stem in skip_names:
            continue
        scripts.append(path)
    return scripts


def parse_tested_ids(output: str) -> list[str]:
    for line in output.splitlines():
        if line.startswith("Tested ledger IDs:"):
            return [part.strip() for part in line.split(":", 1)[1].split(",") if part.strip()]
    return []


def display_path(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def update_coverage(results: list[RegressionResult]) -> None:
    ledger_entries = [entry for entry in parse_ledger() if entry.get("STATUS") == "active"]
    active_ids = {entry["ID"] for entry in ledger_entries}
    failing_ids = set()
    covered_ids = set()

    for result in results:
        ids = set(result["ledger_ids"])
        if result["returncode"] == PASS:
            covered_ids.update(ids)
        elif result["returncode"] != PREREQ_FAIL:
            failing_ids.update(ids)

    covered_ids -= failing_ids
    uncovered_ids = active_ids - covered_ids - failing_ids
    partial_ids: set[str] = set()

    COVERAGE_PATH.write_text(
        "\n".join(
            [
                "COVERED:",
                ", ".join(sorted(covered_ids)),
                "",
                "UNCOVERED:",
                ", ".join(sorted(uncovered_ids)),
                "",
                "FAILING:",
                ", ".join(sorted(failing_ids)),
                "",
                "PARTIAL:",
                ", ".join(sorted(partial_ids)),
                "",
            ]
        ),
        encoding="utf-8",
    )


def append_failure_history(results: list[RegressionResult]) -> None:
    failing_results = [result for result in results if result["returncode"] != PASS]
    if not failing_results:
        return

    FAILURE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with FAILURE_LOG_PATH.open("a", encoding="utf-8") as handle:
        for result in failing_results:
            payload = {
                "timestamp_utc": timestamp,
                "script": result["script"],
                "returncode": result["returncode"],
                "ledger_ids": result["ledger_ids"],
                "artifact": result["artifact"],
            }
            handle.write(json.dumps(payload) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip", action="append", default=[], help="Script stem or filename to skip.")
    args = parser.parse_args()

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    skip_names = set(args.skip)
    scripts = discover_scripts(skip_names)
    results: list[RegressionResult] = []
    stop_on_prereq = False

    for script in scripts:
        completed = subprocess.run(
            [sys.executable, str(script)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        combined_output = f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        artifact_path = ARTIFACT_DIR / f"{script.stem}__run.txt"
        artifact_path.write_text(combined_output, encoding="utf-8")

        result: RegressionResult = {
            "script": script.stem,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "ledger_ids": parse_tested_ids(completed.stdout),
            "artifact": display_path(artifact_path),
        }
        results.append(result)

        if completed.returncode == PREREQ_FAIL:
            stop_on_prereq = True
            break

    update_coverage(results)
    append_failure_history(results)

    passes = sum(1 for result in results if result["returncode"] == PASS)
    failures = sum(1 for result in results if result["returncode"] not in (PASS, PREREQ_FAIL))
    prereq_failures = sum(1 for result in results if result["returncode"] == PREREQ_FAIL)
    failing_ledger_ids = sorted(
        {
            ledger_id
            for result in results
            if result["returncode"] != PASS
            for ledger_id in result["ledger_ids"]
        }
    )

    summary_lines = [
        "Regression Orchestrator Summary",
        f"Total tests: {len(results)}",
        f"Passes: {passes}",
        f"Failures: {failures}",
        f"Prereq failures: {prereq_failures}",
        f"Failing ledger IDs: {', '.join(failing_ledger_ids) if failing_ledger_ids else 'none'}",
        f"Failure log: {display_path(FAILURE_LOG_PATH) if FAILURE_LOG_PATH.exists() else 'none'}",
        f"Stopped early: {'yes' if stop_on_prereq else 'no'}",
        "",
    ]

    for result in results:
        summary_lines.extend(
            [
                f"Script: {result['script']}",
                f"Return code: {result['returncode']}",
                f"Ledger IDs: {', '.join(result['ledger_ids']) if result['ledger_ids'] else 'none'}",
                f"Artifact: {result['artifact']}",
                "",
            ]
        )

    LOG_PATH.write_text("\n".join(summary_lines), encoding="utf-8")
    print("\n".join(summary_lines))

    if prereq_failures:
        return PREREQ_FAIL
    if failures:
        return TEST_FAIL
    return PASS


if __name__ == "__main__":
    raise SystemExit(main())
