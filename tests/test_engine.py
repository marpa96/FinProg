from __future__ import annotations

import unittest

from finprog_engine.engine import (
    build_forecast,
    generate_transaction_events,
    get_daily_rate,
    get_daily_savings_rate,
    validate_settings,
    validate_transaction,
)
from finprog_engine.forecast_io import day_to_markdown, timeline_to_csv


class EngineTests(unittest.TestCase):
    def test_weekly_recurring_transactions_generate_expected_dates(self) -> None:
        transaction = {
            "id": "pay",
            "name": "Weekly Pay",
            "type": "income",
            "kind": "recurring",
            "amount": 700,
            "frequency": "weekly",
            "startDate": "2026-04-01",
            "endDate": "",
            "schedule": {},
            "active": True,
        }
        events = generate_transaction_events(transaction, "2026-04-01", 21)
        self.assertEqual([event["date"] for event in events], ["2026-04-01", "2026-04-08", "2026-04-15"])

    def test_semimonthly_dates_clamp_without_duplicates(self) -> None:
        transaction = {
            "id": "bill",
            "name": "Semimonthly Bill",
            "type": "expense",
            "kind": "recurring",
            "amount": 100,
            "frequency": "semimonthly",
            "startDate": "2026-02-01",
            "endDate": "",
            "schedule": {"semimonthlyDays": [15, 31]},
            "active": True,
        }
        events = generate_transaction_events(transaction, "2026-02-01", 45)
        self.assertEqual([event["date"] for event in events], ["2026-02-15", "2026-02-28", "2026-03-15"])

    def test_one_time_items_appear_once(self) -> None:
        transaction = {
            "id": "bonus",
            "name": "Bonus",
            "type": "income",
            "kind": "one_time",
            "amount": 500,
            "startDate": "2026-04-10",
            "active": True,
        }
        self.assertEqual(len(generate_transaction_events(transaction, "2026-04-01", 15)), 1)
        self.assertEqual(len(generate_transaction_events(transaction, "2026-04-11", 15)), 0)

    def test_one_time_items_with_end_date_distribute_across_range(self) -> None:
        transaction = {
            "id": "trip",
            "name": "Trip Food",
            "type": "expense",
            "kind": "one_time",
            "cashflowClass": "variable",
            "amount": 90,
            "startDate": "2026-04-02",
            "endDate": "2026-04-04",
            "active": True,
        }
        events = generate_transaction_events(transaction, "2026-04-01", 5)
        self.assertEqual([event["date"] for event in events], ["2026-04-02", "2026-04-03", "2026-04-04"])
        self.assertEqual([event["entryKind"] for event in events], ["distributed_range", "distributed_range", "distributed_range"])
        self.assertEqual([event["amount"] for event in events], [-30, -30, -30])

    def test_daily_normalization_rates_include_savings(self) -> None:
        self.assertEqual(get_daily_rate({"type": "income", "kind": "recurring", "amount": 700, "frequency": "weekly", "active": True}), 100)
        self.assertEqual(get_daily_rate({"type": "expense", "kind": "recurring", "amount": 140, "frequency": "biweekly", "active": True}), -10)
        self.assertEqual(get_daily_rate({"type": "savings", "kind": "recurring", "amount": 70, "frequency": "weekly", "active": True}), -10)
        self.assertEqual(get_daily_savings_rate({"type": "savings", "kind": "recurring", "amount": 70, "frequency": "weekly", "active": True}), 10)

    def test_forecast_updates_running_cash_and_savings(self) -> None:
        forecast = build_forecast(
            {
                "startingBalance": 1000,
                "startingSavingsBalance": 200,
                "forecastStartDate": "2026-04-01",
                "forecastDays": 5,
            },
            [
                {"id": "salary", "name": "Salary", "type": "income", "kind": "one_time", "cashflowClass": "fixed", "amount": 500, "startDate": "2026-04-02", "active": True},
                {"id": "rent", "name": "Rent", "type": "expense", "kind": "one_time", "cashflowClass": "fixed", "amount": 300, "startDate": "2026-04-02", "active": True},
                {"id": "save", "name": "Save", "type": "savings", "kind": "one_time", "cashflowClass": "fixed", "amount": 50, "startDate": "2026-04-02", "active": True},
            ],
        )
        self.assertEqual(forecast["timeline"][1]["oneTimeInflow"], 500)
        self.assertEqual(forecast["timeline"][1]["oneTimeOutflow"], 350)
        self.assertEqual(forecast["timeline"][1]["net"], 150)
        self.assertEqual(forecast["timeline"][1]["balance"], 1150)
        self.assertEqual(forecast["timeline"][1]["savingsBalance"], 250)

    def test_income_savings_rules_reduce_cash_and_raise_savings(self) -> None:
        forecast = build_forecast(
            {
                "startingBalance": 0,
                "startingSavingsBalance": 0,
                "forecastStartDate": "2026-04-01",
                "forecastDays": 1,
            },
            [
                {
                    "id": "salary",
                    "name": "Salary",
                    "type": "income",
                    "kind": "one_time",
                    "cashflowClass": "fixed",
                    "amount": 1000,
                    "startDate": "2026-04-01",
                    "active": True,
                    "savingsRulePercent": 10,
                },
            ],
        )
        self.assertEqual(forecast["timeline"][0]["statement"]["fixedIncome"], 1000)
        self.assertEqual(forecast["timeline"][0]["statement"]["incomeSplits"], 100)
        self.assertEqual(forecast["timeline"][0]["net"], 900)
        self.assertEqual(forecast["timeline"][0]["balance"], 900)
        self.assertEqual(forecast["timeline"][0]["savingsBalance"], 100)

    def test_disabled_and_ended_transactions_do_not_create_invalid_events(self) -> None:
        disabled = generate_transaction_events(
            {"id": "off", "name": "Disabled", "type": "expense", "kind": "recurring", "amount": 50, "frequency": "weekly", "startDate": "2026-04-01", "active": False},
            "2026-04-01",
            14,
        )
        ended = generate_transaction_events(
            {"id": "ended", "name": "Ended", "type": "expense", "kind": "recurring", "amount": 50, "frequency": "weekly", "startDate": "2026-04-01", "endDate": "2026-04-08", "active": True},
            "2026-04-01",
            30,
        )
        self.assertEqual(disabled, [])
        self.assertEqual([event["date"] for event in ended], ["2026-04-01", "2026-04-08"])

    def test_validation_catches_missing_and_inconsistent_fields(self) -> None:
        issues = validate_transaction(
            {
                "id": "bad",
                "name": "",
                "type": "weird",
                "kind": "recurring",
                "amount": -5,
                "frequency": "daily",
                "startDate": "",
                "endDate": "2026-01-01",
                "active": True,
                "savingsRulePercent": 20,
            }
        )
        self.assertIn("Name is required.", issues)
        self.assertIn("Type must be income, expense, or savings.", issues)
        self.assertIn("Start date is required.", issues)
        self.assertIn("Recurring frequency is invalid.", issues)

    def test_settings_validation_rejects_bad_forecast_settings(self) -> None:
        issues = validate_settings(
            {
                "startingBalance": "abc",
                "startingSavingsBalance": "def",
                "forecastStartDate": "",
                "forecastDays": 0,
            }
        )
        self.assertIn("Forecast start date is required.", issues)
        self.assertIn("Starting balance must be a valid number.", issues)
        self.assertIn("Starting savings balance must be a valid number.", issues)
        self.assertIn("Forecast days must be a whole number greater than 0.", issues)

    def test_forecast_exposes_totals_risk_and_validation_issues(self) -> None:
        forecast = build_forecast(
            {
                "startingBalance": 100,
                "startingSavingsBalance": 0,
                "forecastStartDate": "2026-04-01",
                "forecastDays": 10,
            },
            [
                {"id": "income", "name": "Pay", "type": "income", "kind": "recurring", "cashflowClass": "fixed", "amount": 700, "frequency": "weekly", "startDate": "2026-04-01", "active": True, "savingsRulePercent": 10},
                {"id": "expense", "name": "Big Bill", "type": "expense", "kind": "one_time", "cashflowClass": "variable", "amount": 1000, "startDate": "2026-04-02", "active": True},
                {"id": "save", "name": "Emergency Fund", "type": "savings", "kind": "recurring", "cashflowClass": "fixed", "amount": 70, "frequency": "weekly", "startDate": "2026-04-01", "active": True},
                {"id": "invalid", "name": "", "type": "income", "kind": "one_time", "cashflowClass": "fixed", "amount": 100, "startDate": "", "active": True},
            ],
        )
        self.assertEqual(forecast["totals"]["scheduledIncome"], 1400)
        self.assertEqual(forecast["totals"]["scheduledExpenses"], 1000)
        self.assertEqual(forecast["totals"]["scheduledSavings"], 140)
        self.assertGreater(forecast["risk"]["negativeBalanceDayCount"], 0)
        self.assertGreater(len(forecast["validationIssues"]), 0)
        self.assertGreater(forecast["totals"]["incomeSplitTotal"], 0)

    def test_timeline_csv_export_produces_day_by_day_balances_with_savings(self) -> None:
        forecast = build_forecast(
            {
                "startingBalance": 500,
                "startingSavingsBalance": 50,
                "forecastStartDate": "2026-04-01",
                "forecastDays": 2,
            },
            [
                {"id": "weekly-pay", "name": "Weekly Pay", "type": "income", "kind": "recurring", "cashflowClass": "fixed", "amount": 700, "frequency": "weekly", "startDate": "2026-04-01", "active": True, "savingsRulePercent": 10},
                {"id": "save", "name": "Emergency Fund", "type": "savings", "kind": "recurring", "cashflowClass": "fixed", "amount": 70, "frequency": "weekly", "startDate": "2026-04-01", "active": True},
                {"id": "snack", "name": "Snack", "type": "expense", "kind": "one_time", "cashflowClass": "variable", "amount": 5, "startDate": "2026-04-02", "active": True},
            ],
        )
        csv = timeline_to_csv(forecast)
        self.assertEqual(
            csv,
            "\n".join(
                [
                    "date,fixed_income,variable_income,fixed_expenses,variable_expenses,fixed_savings,variable_savings,income_splits,total_inflow,total_outflow,net,balance,savings_balance,fixed_income_details,variable_income_details,fixed_expense_details,variable_expense_details,fixed_savings_details,variable_savings_details,income_split_details",
                    "2026-04-01,100.00,0.00,0.00,0.00,10.00,0.00,10.00,100.00,20.00,80.00,580.00,70.00,Weekly Pay: 100.00,,,,Emergency Fund: 10.00,,Weekly Pay Savings Split: 10.00",
                    "2026-04-02,100.00,0.00,0.00,5.00,10.00,0.00,10.00,100.00,25.00,75.00,655.00,90.00,Weekly Pay: 100.00,,,Snack (one-time): -5.00,Emergency Fund: 10.00,,Weekly Pay Savings Split: 10.00",
                    "",
                ]
            ),
        )

    def test_daily_markdown_breakdown_explains_savings_and_income_splits(self) -> None:
        forecast = build_forecast(
            {
                "startingBalance": 100,
                "startingSavingsBalance": 25,
                "forecastStartDate": "2026-04-01",
                "forecastDays": 2,
            },
            [
                {"id": "income", "name": "Weekly Income", "type": "income", "kind": "recurring", "cashflowClass": "fixed", "amount": 700, "frequency": "weekly", "startDate": "2026-04-01", "active": True, "savingsRulePercent": 10},
                {"id": "save", "name": "Emergency Fund", "type": "savings", "kind": "recurring", "cashflowClass": "fixed", "amount": 70, "frequency": "weekly", "startDate": "2026-04-01", "active": True},
                {"id": "bill", "name": "Coffee", "type": "expense", "kind": "one_time", "cashflowClass": "variable", "amount": 5, "startDate": "2026-04-02", "active": True},
            ],
        )
        markdown = day_to_markdown(forecast, forecast["timeline"][1])
        self.assertIn("# Daily Breakdown: 2026-04-02", markdown)
        self.assertIn("- Opening savings balance: $45.00", markdown)
        self.assertIn("## Fixed Savings", markdown)
        self.assertIn("## Income Splits", markdown)
        self.assertIn("- Weekly Income Savings Split: +$10.00", markdown)
        self.assertIn("- Closing savings balance: $65.00", markdown)


if __name__ == "__main__":
    unittest.main()
