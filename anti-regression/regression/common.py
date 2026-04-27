from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PASS = 0
PREREQ_FAIL = 10
TEST_FAIL = 20

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HARNESS_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = HARNESS_ROOT / "regression_artifacts"


def ensure_artifact_dir() -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    return ARTIFACT_DIR


def artifact_path(script_name: str, artifact_name: str) -> Path:
    ensure_artifact_dir()
    return ARTIFACT_DIR / f"{script_name}__{artifact_name}"


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def display_path(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def write_artifact(script_name: str, artifact_name: str, content: str) -> Path:
    path = artifact_path(script_name, artifact_name)
    try:
        path.write_text(content, encoding="utf-8")
        return path
    except PermissionError:
        alternate = ARTIFACT_DIR / f"{path.stem}__{_timestamp_slug()}{path.suffix}"
        alternate.write_text(content, encoding="utf-8")
        return alternate


def resolve_harness_output(primary_path: Path) -> Path:
    candidates = [primary_path]
    candidates.extend(sorted(ARTIFACT_DIR.glob(f"{primary_path.stem}__*{primary_path.suffix}")))
    existing = [path for path in candidates if path.exists()]
    if not existing:
        return primary_path
    return max(existing, key=lambda path: path.stat().st_mtime)


def print_header(script_name: str, ledger_ids: list[str], expected: str) -> None:
    print(f"Script: {script_name}")
    print(f"Tested ledger IDs: {', '.join(ledger_ids)}")
    print(f"Expected: {expected}")


def print_pass(script_name: str, ledger_ids: list[str], expected: str, observed: str) -> int:
    print_header(script_name, ledger_ids, expected)
    print(f"Observed: {observed}")
    print("Result: PASS")
    print("Exit code meaning: 0 = PASS")
    return PASS


def print_prereq_fail(
    script_name: str,
    ledger_ids: list[str],
    expected: str,
    observed: str,
    artifact: Path | None = None,
) -> int:
    print_header(script_name, ledger_ids, expected)
    print(f"Observed: {observed}")
    print("Result: PREREQ_FAIL")
    if artifact:
        print(f"Artifact: {display_path(artifact)}")
    print("Exit code meaning: 10 = PREREQ_FAIL")
    return PREREQ_FAIL


def print_failures(script_name: str, ledger_ids: list[str], expected: str, failures: list[dict[str, str]]) -> int:
    print_header(script_name, ledger_ids, expected)
    for failure in failures:
        print(f"[FAIL] {failure['ledger_id']}")
        print(f"Expected: {failure['expected']}")
        print(f"Observed: {failure['observed']}")
        print(f"Verifier: {script_name}")
        print("Exit code: 20")
        print(f"Artifact: {failure['artifact']}")
    print("Result: TEST_FAIL")
    print("Exit code meaning: 20 = TEST_FAIL")
    return TEST_FAIL


def run_node_json(script_source: str) -> dict:
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script_source],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            f"Node execution failed with code {completed.returncode}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )

    return json.loads(completed.stdout)


def run_python(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def run_python_json(args: list[str]) -> dict:
    completed = run_python(args)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Python execution failed with code {completed.returncode}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return json.loads(completed.stdout)
