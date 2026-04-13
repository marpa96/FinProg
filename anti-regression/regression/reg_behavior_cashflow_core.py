from __future__ import annotations

import json
from pathlib import Path

from common import PROJECT_ROOT, display_path, print_failures, print_pass, print_prereq_fail, run_python_json, write_artifact


SCRIPT_NAME = "reg_behavior_cashflow_core"
LEDGER_IDS = ["CASH-001", "CASH-002", "CASH-003", "CASH-004", "CASH-005", "CASH-006", "CASH-010", "CASH-011"]
EXPECTED = (
    "Python cashflow engine preserves recurring schedules, daily recurring allocations, one-time handling, "
    "cash and savings balances, supported frequencies, semimonthly short-month fallback, and income savings splits."
)


def main() -> int:
    if not Path(PROJECT_ROOT / "finprog_engine" / "engine.py").exists():
        artifact = write_artifact(SCRIPT_NAME, "missing_engine.txt", "finprog_engine/engine.py was not found.")
        return print_prereq_fail(SCRIPT_NAME, LEDGER_IDS, EXPECTED, "The Python cashflow engine module is missing.", artifact)

    try:
        result = run_python_json(
            [
                "-c",
                """
import json
from finprog_engine.engine import build_forecast, generate_transaction_events, get_daily_rate, get_daily_savings_rate

weekly_events = [event["date"] for event in generate_transaction_events({
  "id": "pay", "name": "Weekly Pay", "type": "income", "kind": "recurring", "amount": 700,
  "frequency": "weekly", "startDate": "2026-04-01", "endDate": "", "schedule": {}, "active": True
}, "2026-04-01", 21)]

frequency_checks = {
  "weekly": len(generate_transaction_events({"id":"weekly","name":"Weekly","type":"income","kind":"recurring","amount":10,"frequency":"weekly","startDate":"2026-04-01","active":True},"2026-04-01",30)) > 0,
  "biweekly": len(generate_transaction_events({"id":"biweekly","name":"Biweekly","type":"income","kind":"recurring","amount":10,"frequency":"biweekly","startDate":"2026-04-01","active":True},"2026-04-01",30)) > 0,
  "semimonthly": len(generate_transaction_events({"id":"semi","name":"Semi","type":"expense","kind":"recurring","amount":10,"frequency":"semimonthly","startDate":"2026-04-01","schedule":{"semimonthlyDays":[15,31]},"active":True},"2026-04-01",60)) > 0,
  "monthly": len(generate_transaction_events({"id":"monthly","name":"Monthly","type":"expense","kind":"recurring","amount":10,"frequency":"monthly","startDate":"2026-04-01","active":True},"2026-04-01",60)) > 0,
  "yearly": len(generate_transaction_events({"id":"yearly","name":"Yearly","type":"income","kind":"recurring","amount":10,"frequency":"yearly","startDate":"2026-04-01","active":True},"2026-04-01",500)) > 0,
}

semimonthly_events = [event["date"] for event in generate_transaction_events({
  "id": "bill", "name": "Semimonthly Bill", "type": "expense", "kind": "recurring", "amount": 100,
  "frequency": "semimonthly", "startDate": "2026-02-01", "schedule": {"semimonthlyDays": [15, 31]}, "active": True
}, "2026-02-01", 45)]

one_time_events = [event["date"] for event in generate_transaction_events({
  "id":"bonus","name":"Bonus","type":"income","kind":"one_time","amount":500,"startDate":"2026-04-10","active":True
}, "2026-04-01", 15)]

forecast = build_forecast(
    {"startingBalance":1000,"startingSavingsBalance":200,"forecastStartDate":"2026-04-01","forecastDays":5},
    [
      {"id":"weekly-income","name":"Weekly Income","type":"income","kind":"recurring","amount":700,"frequency":"weekly","startDate":"2026-04-01","active":True,"cashflowClass":"fixed","savingsRulePercent":10},
      {"id":"weekly-expense","name":"Weekly Expense","type":"expense","kind":"recurring","amount":140,"frequency":"weekly","startDate":"2026-04-01","active":True,"cashflowClass":"variable"},
      {"id":"weekly-save","name":"Weekly Save","type":"savings","kind":"recurring","amount":70,"frequency":"weekly","startDate":"2026-04-01","active":True,"cashflowClass":"fixed"},
      {"id":"salary","name":"Salary","type":"income","kind":"one_time","amount":500,"startDate":"2026-04-02","active":True,"cashflowClass":"fixed"},
      {"id":"rent","name":"Rent","type":"expense","kind":"one_time","amount":300,"startDate":"2026-04-02","active":True,"cashflowClass":"fixed"},
    ],
)

print(json.dumps({
  "weeklyEvents": weekly_events,
  "frequencyChecks": frequency_checks,
  "semimonthlyEvents": semimonthly_events,
  "oneTimeEvents": one_time_events,
  "dailyRates": {
    "weekly": get_daily_rate({"type":"income","kind":"recurring","amount":700,"frequency":"weekly","active":True}),
    "biweeklyExpense": get_daily_rate({"type":"expense","kind":"recurring","amount":140,"frequency":"biweekly","active":True}),
    "weeklySavings": get_daily_savings_rate({"type":"savings","kind":"recurring","amount":70,"frequency":"weekly","active":True}),
  },
  "forecast": {
    "dayOneNet": forecast["timeline"][0]["net"],
    "dayOneBalance": forecast["timeline"][0]["balance"],
    "dayOneSavingsBalance": forecast["timeline"][0]["savingsBalance"],
    "dayOneIncomeSplit": forecast["timeline"][0]["statement"]["incomeSplits"],
    "dayTwoOneTimeInflow": forecast["timeline"][1]["oneTimeInflow"],
    "dayTwoOneTimeOutflow": forecast["timeline"][1]["oneTimeOutflow"],
    "projectedEndBalance": forecast["projectedEndBalance"],
    "projectedEndSavingsBalance": forecast["projectedEndSavingsBalance"],
  }
}))
""",
            ]
        )
    except Exception as exc:
        artifact = write_artifact(SCRIPT_NAME, "python_exception.txt", str(exc))
        return print_prereq_fail(SCRIPT_NAME, LEDGER_IDS, EXPECTED, "Python-based engine verification could not run.", artifact)

    artifact = write_artifact(SCRIPT_NAME, "observed.json", json.dumps(result, indent=2))
    failures = []

    if result["weeklyEvents"] != ["2026-04-01", "2026-04-08", "2026-04-15"]:
        failures.append({"ledger_id": "CASH-001", "expected": "Recurring items generate expected scheduled dates.", "observed": f"Weekly dates were {result['weeklyEvents']}.", "artifact": display_path(artifact)})
    if not all(result["frequencyChecks"].values()):
        failures.append({"ledger_id": "CASH-005", "expected": "All supported recurring frequencies produce events.", "observed": f"Frequency checks were {result['frequencyChecks']}.", "artifact": display_path(artifact)})
    if result["semimonthlyEvents"] != ["2026-02-15", "2026-02-28", "2026-03-15"]:
        failures.append({"ledger_id": "CASH-006", "expected": "Semimonthly dates clamp without duplicates.", "observed": f"Semimonthly dates were {result['semimonthlyEvents']}.", "artifact": display_path(artifact)})
    if result["oneTimeEvents"] != ["2026-04-10"]:
        failures.append({"ledger_id": "CASH-003", "expected": "One-time transactions appear exactly once inside the window.", "observed": f"One-time dates were {result['oneTimeEvents']}.", "artifact": display_path(artifact)})
    if result["dailyRates"] != {"weekly": 100.0, "biweeklyExpense": -10.0, "weeklySavings": 10.0}:
        failures.append({"ledger_id": "CASH-002", "expected": "Daily normalization rates remain correct.", "observed": f"Daily rates were {result['dailyRates']}.", "artifact": display_path(artifact)})

    forecast = result["forecast"]
    expected_forecast = {
        "dayOneNet": 60.0,
        "dayOneBalance": 1060.0,
        "dayOneSavingsBalance": 220.0,
        "dayOneIncomeSplit": 10.0,
        "dayTwoOneTimeInflow": 500.0,
        "dayTwoOneTimeOutflow": 300.0,
        "projectedEndBalance": 1500.0,
        "projectedEndSavingsBalance": 300.0,
    }
    if forecast != expected_forecast:
        failures.append({"ledger_id": "CASH-004", "expected": "Forecast updates cash and savings balances correctly.", "observed": f"Forecast summary was {forecast}.", "artifact": display_path(artifact)})

    if forecast["dayOneSavingsBalance"] <= 200.0:
        failures.append({"ledger_id": "CASH-010", "expected": "Savings uses a separate running balance that grows when savings entries apply.", "observed": f"Day-one savings balance was {forecast['dayOneSavingsBalance']}.", "artifact": display_path(artifact)})
    if forecast["dayOneIncomeSplit"] != 10.0:
        failures.append({"ledger_id": "CASH-011", "expected": "Income savings rules create visible split amounts.", "observed": f"Income split amount was {forecast['dayOneIncomeSplit']}.", "artifact": display_path(artifact)})

    if failures:
        return print_failures(SCRIPT_NAME, LEDGER_IDS, EXPECTED, failures)

    return print_pass(SCRIPT_NAME, LEDGER_IDS, EXPECTED, "Python engine schedules, balances, savings, and income split behavior all matched the expected scenarios.")


if __name__ == "__main__":
    raise SystemExit(main())
