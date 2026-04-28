import sqlite3
import unittest
from pathlib import Path

from extractors.rocket_money import RocketMoneyGraphqlExtractor
from scripts.extract_rocketmoney_transactions import build_mock_transport
from storage import ConsolidatedFinanceStore, sync_rocketmoney_payload_to_db, sync_rocketmoney_to_consolidated


class ConsolidatedFinanceSqliteTests(unittest.TestCase):
    def test_rocketmoney_transactions_sync_into_consolidated_source_table(self) -> None:
        rocket_db = Path("anti-regression/regression_artifacts/test_consolidated_rocketmoney_source.db")
        consolidated_db = Path("anti-regression/regression_artifacts/test_consolidated_finance.db")
        for path in (rocket_db, consolidated_db):
            if path.exists():
                path.unlink()

        extracted = RocketMoneyGraphqlExtractor(
            headers={"cookie": "mock"},
            transport=build_mock_transport(),
        ).extract()
        sync_rocketmoney_payload_to_db(rocket_db, extracted)

        summary = sync_rocketmoney_to_consolidated(rocket_db, consolidated_db)

        self.assertEqual(summary["sourceId"], "rocketmoney")
        self.assertEqual(summary["sourceTransactionCount"], 3)

        connection = sqlite3.connect(consolidated_db)
        try:
            tx_count = connection.execute("SELECT COUNT(*) FROM finance_source_transactions").fetchone()[0]
            paycheck = connection.execute(
                """
                SELECT source_amount_unit, source_amount_cents, source_amount_sign,
                    normalized_magnitude_cents, planning_amount_cents, planning_direction, planning_type_guess
                FROM finance_source_transactions
                WHERE source_transaction_id = 'rocket_mock_0'
                """
            ).fetchone()
            grocery = connection.execute(
                """
                SELECT source_amount_cents, source_amount_sign, planning_amount_cents, planning_direction, planning_type_guess
                FROM finance_source_transactions
                WHERE source_transaction_id = 'rocket_mock_1'
                """
            ).fetchone()
        finally:
            connection.close()

        self.assertEqual(tx_count, 3)
        self.assertEqual(tuple(paycheck), ("cents", -180000, "negative", 180000, 180000, "positive", "income"))
        self.assertEqual(tuple(grocery), (8245, "positive", -8245, "negative", "expense"))

        store = ConsolidatedFinanceStore(consolidated_db)
        connection = store.connect()
        try:
            transactions = store.list_source_transactions(connection, limit=2, source_id="rocketmoney")
        finally:
            connection.close()

        self.assertEqual(len(transactions), 2)
        self.assertEqual(transactions[0]["sourceId"], "rocketmoney")
        self.assertIn("planningAmountCents", transactions[0])

    def test_source_transactions_can_be_counted_filtered_and_paged(self) -> None:
        db_path = Path("anti-regression/regression_artifacts/test_consolidated_filters.db")
        if db_path.exists():
            db_path.unlink()

        store = ConsolidatedFinanceStore(db_path)
        connection = store.connect()
        try:
            store.ensure_schema(connection)
            store.upsert_source(
                connection,
                source_id="rocketmoney",
                display_name="Rocket Money",
                source_type="transaction_aggregator",
                raw_database_path=None,
                default_amount_unit="cents",
                expense_sign="positive",
                income_sign="negative",
            )
            store.upsert_source_transactions(
                connection,
                "rocketmoney",
                [
                    {"sourceTransactionId": "older", "postedDate": "2026-03-01", "sourceAmountRaw": 1000, "description": "Old Coffee"},
                    {"sourceTransactionId": "middle", "postedDate": "2026-04-10", "sourceAmountRaw": 2000, "description": "Middle Coffee"},
                    {"sourceTransactionId": "newer", "postedDate": "2026-04-11", "sourceAmountRaw": -3000, "description": "New Pay"},
                ],
            )
            connection.commit()

            total = store.count_source_transactions(connection, source_id="rocketmoney", start_date="2026-04-01", end_date="2026-04-30")
            first_page = store.list_source_transactions(
                connection,
                source_id="rocketmoney",
                start_date="2026-04-01",
                end_date="2026-04-30",
                limit=1,
                offset=0,
            )
            second_page = store.list_source_transactions(
                connection,
                source_id="rocketmoney",
                start_date="2026-04-01",
                end_date="2026-04-30",
                limit=1,
                offset=1,
            )
        finally:
            connection.close()

        self.assertEqual(total, 2)
        self.assertEqual([row["sourceTransactionId"] for row in first_page], ["newer"])
        self.assertEqual([row["sourceTransactionId"] for row in second_page], ["middle"])

    def test_source_amount_convention_can_be_positive_expenses(self) -> None:
        db_path = Path("anti-regression/regression_artifacts/test_consolidated_amount_policy.db")
        if db_path.exists():
            db_path.unlink()

        store = ConsolidatedFinanceStore(db_path)
        connection = store.connect()
        try:
            store.ensure_schema(connection)
            store.upsert_source(
                connection,
                source_id="sample-positive-expenses",
                display_name="Sample",
                source_type="csv",
                raw_database_path=None,
                default_amount_unit="dollars",
                expense_sign="positive",
                income_sign="negative",
            )
            store.upsert_source_transactions(
                connection,
                "sample-positive-expenses",
                [
                    {
                        "sourceTransactionId": "expense-1",
                        "sourceAmountRaw": 12.34,
                        "description": "Coffee",
                    },
                    {
                        "sourceTransactionId": "income-1",
                        "sourceAmountRaw": -100.00,
                        "description": "Pay",
                    },
                ],
            )
            connection.commit()
            rows = connection.execute(
                """
                SELECT source_transaction_id, source_amount_cents, planning_amount_cents, planning_type_guess
                FROM finance_source_transactions
                ORDER BY source_transaction_id
                """
            ).fetchall()
        finally:
            connection.close()

        self.assertEqual([tuple(row) for row in rows], [
            ("expense-1", 1234, -1234, "expense"),
            ("income-1", -10000, 10000, "income"),
        ])

    def test_user_classification_rules_capture_planning_intent(self) -> None:
        db_path = Path("anti-regression/regression_artifacts/test_consolidated_rules.db")
        if db_path.exists():
            db_path.unlink()

        store = ConsolidatedFinanceStore(db_path)
        connection = store.connect()
        try:
            store.ensure_schema(connection)
            store.upsert_classification_rule(
                connection,
                {
                    "ruleId": "rule-rent",
                    "sourceId": "rocketmoney",
                    "priority": 10,
                    "matchField": "description",
                    "matchOperator": "contains",
                    "matchValue": "Apartment Rent",
                    "planningLabel": "Rent",
                    "normalizedType": "expense",
                    "cashflowClass": "fixed",
                    "categoryId": "exp-home",
                    "subcategoryId": "exp-home-rent",
                },
            )
            connection.commit()
            row = connection.execute(
                """
                SELECT planning_label, normalized_type, cashflow_class, category_id, subcategory_id
                FROM finance_classification_rules
                WHERE rule_id = 'rule-rent'
                """
            ).fetchone()
        finally:
            connection.close()

        self.assertEqual(tuple(row), ("Rent", "expense", "fixed", "exp-home", "exp-home-rent"))


if __name__ == "__main__":
    unittest.main()
