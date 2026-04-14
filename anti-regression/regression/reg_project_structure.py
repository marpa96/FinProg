from __future__ import annotations

from common import PROJECT_ROOT, display_path, print_failures, print_pass


SCRIPT_NAME = "reg_project_structure"
LEDGER_IDS = ["EXT-001"]
EXPECTED = "Rocket Money extractor code has its own folder under extractors."


def main() -> int:
    rocket_money_dir = PROJECT_ROOT / "extractors" / "rocket_money"
    required_paths = [
        rocket_money_dir,
        rocket_money_dir / "__init__.py",
        rocket_money_dir / "csv_export.py",
    ]
    missing = [path for path in required_paths if not path.exists()]

    if missing:
        return print_failures(
            SCRIPT_NAME,
            LEDGER_IDS,
            EXPECTED,
            [
                {
                    "ledger_id": "EXT-001",
                    "expected": "Rocket Money extractor package exists under extractors with an importable CSV extractor starter.",
                    "observed": f"Missing paths: {[display_path(path) for path in missing]}.",
                    "artifact": "anti-regression/regression_artifacts/reg_project_structure__run.txt",
                }
            ],
        )

    return print_pass(
        SCRIPT_NAME,
        LEDGER_IDS,
        EXPECTED,
        "Rocket Money extractor package exists under extractors.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
