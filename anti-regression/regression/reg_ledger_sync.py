from __future__ import annotations

from pathlib import Path

from common import HARNESS_ROOT, PROJECT_ROOT, display_path, print_failures, print_pass, print_prereq_fail, write_artifact


SCRIPT_NAME = "reg_ledger_sync"
LEDGER_IDS = ["META-001", "REG-003"]
EXPECTED = (
    "The canonical ledger, compact ledger, coverage index, and referenced verifier scripts stay synchronized, "
    "and ledger files are not older than the tracked code surfaces they protect."
)


def parse_ledger(path: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
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


def parse_compact(path: Path) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 3:
            continue
        entries[parts[0]] = {"behavior": parts[1], "verifier": parts[2]}
    return entries


def parse_coverage(path: Path) -> dict[str, set[str]]:
    sections = {"COVERED": set(), "UNCOVERED": set(), "FAILING": set(), "PARTIAL": set()}
    current = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.rstrip(":") in sections:
            current = line.rstrip(":")
            continue
        if current and line:
            sections[current].update(part.strip() for part in line.split(",") if part.strip())
    return sections


def main() -> int:
    ledger_path = HARNESS_ROOT / "feature_ledger.txt"
    compact_path = HARNESS_ROOT / "feature_ledger_compact.txt"
    coverage_path = HARNESS_ROOT / "regression_coverage.txt"
    regression_dir = HARNESS_ROOT / "regression"

    required_paths = [ledger_path, compact_path, coverage_path, regression_dir]
    missing = [path.as_posix() for path in required_paths if not path.exists()]
    if missing:
        artifact = write_artifact(SCRIPT_NAME, "missing_paths.txt", "\n".join(missing))
        return print_prereq_fail(
            SCRIPT_NAME,
            LEDGER_IDS,
            EXPECTED,
            f"Required ledger or regression paths are missing: {missing}",
            artifact,
        )

    ledger_entries = parse_ledger(ledger_path)
    compact_entries = parse_compact(compact_path)
    coverage = parse_coverage(coverage_path)
    active_entries = [entry for entry in ledger_entries if entry.get("STATUS") == "active"]
    active_ids = {entry["ID"] for entry in active_entries}
    known_coverage_ids = set().union(*coverage.values())

    failures = []

    meta_entry = next((entry for entry in active_entries if entry.get("ID") == "META-001"), None)
    if not meta_entry or meta_entry.get("VERIFY") != "reg_ledger_sync":
        artifact = write_artifact(SCRIPT_NAME, "meta_entry.txt", str(meta_entry))
        failures.append(
            {
                "ledger_id": "META-001",
                "expected": "META-001 is present as an active entry and is verified by reg_ledger_sync.",
                "observed": f"META-001 entry was {meta_entry}.",
                "artifact": display_path(artifact),
            }
        )

    for entry in active_entries:
        verifier = entry.get("VERIFY", "")
        verifier_path = regression_dir / f"{verifier}.py"
        if not verifier_path.exists():
            artifact = write_artifact(SCRIPT_NAME, f"missing_verifier_{entry['ID']}.txt", verifier_path.as_posix())
            failures.append(
                {
                    "ledger_id": "REG-003",
                    "expected": f"Verifier {verifier}.py exists for active entry {entry['ID']}.",
                    "observed": f"Missing verifier at {verifier_path.as_posix()}.",
                    "artifact": display_path(artifact),
                }
            )

        compact_entry = compact_entries.get(entry["ID"])
        if not compact_entry or compact_entry["verifier"] != verifier:
            artifact = write_artifact(SCRIPT_NAME, f"compact_mismatch_{entry['ID']}.txt", str(compact_entry))
            failures.append(
                {
                    "ledger_id": "REG-003",
                    "expected": f"Compact ledger contains {entry['ID']} with verifier {verifier}.",
                    "observed": f"Compact entry was {compact_entry}.",
                    "artifact": display_path(artifact),
                }
            )

    uncovered_in_index = sorted(active_ids - known_coverage_ids)
    if uncovered_in_index:
        artifact = write_artifact(SCRIPT_NAME, "coverage_missing_ids.txt", ", ".join(uncovered_in_index))
        failures.append(
            {
                "ledger_id": "REG-003",
                "expected": "Every active ledger ID appears in regression_coverage.txt.",
                "observed": f"Coverage index was missing {uncovered_in_index}.",
                "artifact": display_path(artifact),
            }
        )

    tracked_paths = [
        PROJECT_ROOT / "app.py",
        PROJECT_ROOT / "finprog_engine" / "engine.py",
        PROJECT_ROOT / "finprog_engine" / "forecast_io.py",
        PROJECT_ROOT / "tests" / "test_engine.py",
        HARNESS_ROOT / "run_regression.py",
        regression_dir / "reg_behavior_cashflow_core.py",
        regression_dir / "reg_contract_regression_system.py",
    ]
    ledger_mtime = min(ledger_path.stat().st_mtime, compact_path.stat().st_mtime)
    newer_tracked_paths = [path.as_posix() for path in tracked_paths if path.exists() and path.stat().st_mtime > ledger_mtime]
    if newer_tracked_paths:
        artifact = write_artifact(SCRIPT_NAME, "mtime_drift.txt", "\n".join(newer_tracked_paths))
        failures.append(
            {
                "ledger_id": "META-001",
                "expected": "Ledger files are updated alongside meaningful user-facing code changes.",
                "observed": f"Tracked files newer than the ledger were {newer_tracked_paths}.",
                "artifact": display_path(artifact),
            }
        )

    if failures:
        return print_failures(SCRIPT_NAME, LEDGER_IDS, EXPECTED, failures)

    return print_pass(
        SCRIPT_NAME,
        LEDGER_IDS,
        EXPECTED,
        "Ledger files, coverage index, verifiers, and modification times are synchronized.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
