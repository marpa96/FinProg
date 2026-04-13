from __future__ import annotations

import csv
import json

from common import PROJECT_ROOT, display_path, print_failures, print_pass, print_prereq_fail, run_python_json, write_artifact


SCRIPT_NAME = "reg_behavior_sample_export"
LEDGER_IDS = ["CASH-007", "CASH-008", "CASH-009"]
EXPECTED = (
    "The simple household scenario stays representable as JSON input and exports a day-by-day CSV "
    "with fixed and variable statement buckets, savings balances, income split detail, and a markdown sample-day breakdown from the forecast engine."
)


def normalize_text(value: str) -> str:
    return value.replace("\r\n", "\n").strip()


def main() -> int:
    json_path = PROJECT_ROOT / "examples" / "simple_household.json"
    csv_path = PROJECT_ROOT / "examples" / "simple_household_forecast.csv"
    markdown_path = PROJECT_ROOT / "examples" / "simple_household_day_2026-04-18.md"

    if not json_path.exists():
        artifact = write_artifact(SCRIPT_NAME, "missing_json.txt", "examples/simple_household.json was not found.")
        return print_prereq_fail(
            SCRIPT_NAME,
            LEDGER_IDS,
            EXPECTED,
            "The simple household JSON scenario is missing.",
            artifact,
        )

    try:
        scenario = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        artifact = write_artifact(SCRIPT_NAME, "invalid_json.txt", str(exc))
        return print_prereq_fail(
            SCRIPT_NAME,
            LEDGER_IDS,
            EXPECTED,
            "The simple household JSON scenario could not be parsed.",
            artifact,
        )

    try:
        observed = run_python_json(
            [
                "-c",
                f"""
import json
from pathlib import Path

from finprog_engine import build_forecast, day_to_markdown, timeline_to_csv

scenario = json.loads(Path(r"{json_path}").read_text(encoding="utf-8"))
forecast = build_forecast(scenario["settings"], scenario["transactions"])
csv = timeline_to_csv(forecast)
sample_day = next((entry for entry in forecast["timeline"] if entry["date"] == "2026-04-18"), None)
print(json.dumps({{
  "validationIssues": forecast["validationIssues"],
  "totals": forecast["totals"],
  "csv": csv,
  "markdown": day_to_markdown(forecast, sample_day) if sample_day else None,
}}))
""",
            ]
        )
    except Exception as exc:
        artifact = write_artifact(SCRIPT_NAME, "python_exception.txt", str(exc))
        return print_prereq_fail(
            SCRIPT_NAME,
            LEDGER_IDS,
            EXPECTED,
            "The sample export verification could not execute the engine.",
            artifact,
        )

    artifact = write_artifact(SCRIPT_NAME, "observed.json", json.dumps(observed, indent=2))
    failures = []

    if scenario.get("transactions") is None or len(scenario["transactions"]) < 2:
        failures.append(
            {
                "ledger_id": "CASH-007",
                "expected": "The sample JSON contains recurring income and normal household expenses.",
                "observed": f"Scenario transactions were {scenario.get('transactions')}.",
                "artifact": display_path(artifact),
            }
        )
    else:
        income_count = sum(1 for item in scenario["transactions"] if item.get("type") == "income")
        expense_count = sum(1 for item in scenario["transactions"] if item.get("type") == "expense")
        class_count = sum(1 for item in scenario["transactions"] if item.get("cashflowClass") in {"fixed", "variable"})
        if income_count < 1 or expense_count < 1 or class_count != len(scenario["transactions"]):
            failures.append(
                {
                    "ledger_id": "CASH-007",
                    "expected": "The sample JSON includes income, expenses, and fixed-or-variable cashflow classification on each item.",
                    "observed": f"Income count was {income_count}, expense count was {expense_count}, and classified items were {class_count} of {len(scenario['transactions'])}.",
                    "artifact": display_path(artifact),
                }
            )

    if observed["validationIssues"]:
        failures.append(
            {
                "ledger_id": "CASH-007",
                "expected": "The sample JSON is valid input for the forecast engine.",
                "observed": f"Validation issues were {observed['validationIssues']}.",
                "artifact": display_path(artifact),
            }
        )

    csv_lines = observed["csv"].splitlines()
    expected_header = (
        "date,fixed_income,variable_income,fixed_expenses,variable_expenses,fixed_savings,variable_savings,income_splits,"
        "total_inflow,total_outflow,net,balance,savings_balance,fixed_income_details,variable_income_details,"
        "fixed_expense_details,variable_expense_details,fixed_savings_details,variable_savings_details,income_split_details"
    )
    if not csv_lines or csv_lines[0] != expected_header:
        failures.append(
            {
                "ledger_id": "CASH-008",
                "expected": "The CSV export starts with the daily allocation and balance header row.",
                "observed": f"CSV header was {csv_lines[0] if csv_lines else 'missing'}.",
                "artifact": display_path(artifact),
            }
        )
    else:
        rows = list(csv.DictReader(csv_lines))
        expected_days = int(scenario["settings"]["forecastDays"])
        if len(rows) != expected_days:
            failures.append(
                {
                    "ledger_id": "CASH-008",
                    "expected": f"The CSV export contains {expected_days} daily rows for the forecast window.",
                    "observed": f"CSV row count was {len(rows)}.",
                    "artifact": display_path(artifact),
                }
            )
        if not rows or "balance" not in rows[0] or "savings_balance" not in rows[0] or "income_split_details" not in rows[0]:
            failures.append(
                {
                    "ledger_id": "CASH-008",
                    "expected": "The CSV export includes cash balance, savings balance, and savings or split detail columns.",
                    "observed": f"First CSV row was {rows[0] if rows else 'missing'}.",
                    "artifact": display_path(artifact),
                }
            )
        elif not any(
            row["fixed_income_details"] or row["variable_income_details"] or row["fixed_expense_details"] or row["variable_expense_details"] or row["fixed_savings_details"] or row["income_split_details"]
            for row in rows
        ):
            failures.append(
                {
                    "ledger_id": "CASH-008",
                    "expected": "The CSV export shows where fixed and variable additions and deductions come from.",
                    "observed": "No fixed-or-variable detail text was present in any CSV row.",
                    "artifact": display_path(artifact),
                }
            )

    if csv_path.exists():
        saved_csv = normalize_text(csv_path.read_text(encoding="utf-8"))
        generated_csv = normalize_text(observed["csv"])
        if saved_csv != generated_csv:
            saved_artifact = write_artifact(SCRIPT_NAME, "csv_mismatch.txt", saved_csv)
            failures.append(
                {
                    "ledger_id": "CASH-008",
                    "expected": "The committed sample CSV matches the engine-generated export from the sample JSON.",
                    "observed": f"Saved CSV at {display_path(csv_path)} did not match the generated export.",
                    "artifact": display_path(saved_artifact),
                }
            )
    else:
        failures.append(
            {
                "ledger_id": "CASH-008",
                "expected": "A committed sample CSV exists for the sample household scenario.",
                "observed": f"Missing file {display_path(csv_path)}.",
                "artifact": display_path(artifact),
            }
            )

    if markdown_path.exists():
        saved_markdown = normalize_text(markdown_path.read_text(encoding="utf-8"))
        if observed["markdown"] is None:
            failures.append(
                {
                    "ledger_id": "CASH-009",
                    "expected": "The sample-day markdown is generated from a real day in the forecast timeline.",
                    "observed": "No markdown was generated for the configured sample day.",
                    "artifact": display_path(artifact),
                }
            )
        elif saved_markdown != normalize_text(observed["markdown"]):
            saved_artifact = write_artifact(SCRIPT_NAME, "markdown_mismatch.txt", saved_markdown)
            failures.append(
                {
                    "ledger_id": "CASH-009",
                    "expected": "The committed sample-day markdown matches the engine-generated breakdown.",
                    "observed": f"Saved markdown at {display_path(markdown_path)} did not match the generated breakdown.",
                    "artifact": display_path(saved_artifact),
                }
            )
        elif "# Daily Breakdown: 2026-04-18" not in saved_markdown or "## Fixed Savings" not in saved_markdown or "## Income Splits" not in saved_markdown:
            failures.append(
                {
                    "ledger_id": "CASH-009",
                    "expected": "The sample-day markdown contains the savings and income split statement sections.",
                    "observed": f"Markdown content was missing expected sections in {display_path(markdown_path)}.",
                    "artifact": display_path(artifact),
                }
            )
    else:
        failures.append(
            {
                "ledger_id": "CASH-009",
                "expected": "A committed sample-day markdown file exists for the chosen sample date.",
                "observed": f"Missing file {display_path(markdown_path)}.",
                "artifact": display_path(artifact),
            }
        )

    if failures:
        return print_failures(SCRIPT_NAME, LEDGER_IDS, EXPECTED, failures)

    return print_pass(
        SCRIPT_NAME,
        LEDGER_IDS,
        EXPECTED,
        "The sample household JSON is valid and the committed CSV and markdown day breakdown match the engine-generated exports.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
