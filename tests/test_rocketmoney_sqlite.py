import sqlite3
import unittest
from pathlib import Path

from extractors.rocket_money import RocketMoneyGraphqlExtractor, RocketMoneyTransactionDetailExtractor
from scripts.extract_rocketmoney_transactions import build_mock_transport
from scripts.sync_rocketmoney_database import build_mock_detail_transport
from storage import sync_rocketmoney_payload_to_db


class RocketMoneySqliteTests(unittest.TestCase):
    def test_mock_payload_syncs_into_sqlite(self) -> None:
        db_path = Path("anti-regression/regression_artifacts/test_rocketmoney_sqlite.db")
        if db_path.exists():
            db_path.unlink()

        page_events = []
        extractor = RocketMoneyGraphqlExtractor(
            headers={"cookie": "mock"},
            transport=build_mock_transport(),
            progress_callback=page_events.append,
        )
        extracted = extractor.extract()
        detail_events = []
        detail_extractor = RocketMoneyTransactionDetailExtractor(
            headers={"cookie": "mock"},
            transport=build_mock_detail_transport(),
            progress_callback=detail_events.append,
        )
        details_by_id = detail_extractor.fetch_many(
            [transaction["id"] for transaction in extracted.payload["transactions"]]
        )
        summary = sync_rocketmoney_payload_to_db(
            db_path,
            extracted,
            raw_snapshot_path="mock.json",
            details_by_id=details_by_id,
        )

        self.assertEqual(summary["transactionCount"], 3)
        self.assertEqual(summary["pageCount"], 2)
        self.assertEqual(summary["transactionsUpserted"], 3)
        self.assertEqual(len(page_events), 2)
        self.assertEqual(len(detail_events), 3)
        self.assertEqual(detail_events[-1]["current"], 3)

        connection = sqlite3.connect(db_path)
        try:
            tx_count = connection.execute("SELECT COUNT(*) FROM rocketmoney_transactions").fetchone()[0]
            page_count = connection.execute("SELECT COUNT(*) FROM rocketmoney_sync_pages").fetchone()[0]
            run_status = connection.execute("SELECT status FROM rocketmoney_sync_runs").fetchone()[0]
            payload_count = connection.execute("SELECT COUNT(*) FROM rocketmoney_payload_snapshots").fetchone()[0]
            amount_unit = connection.execute(
                "SELECT amount_unit FROM rocketmoney_transactions WHERE transaction_id = 'rocket_mock_0'"
            ).fetchone()[0]
            detail_count = connection.execute("SELECT COUNT(*) FROM rocketmoney_transaction_details").fetchone()[0]
            related_count = connection.execute("SELECT COUNT(*) FROM rocketmoney_transaction_related").fetchone()[0]
            monthly_count = connection.execute("SELECT COUNT(*) FROM rocketmoney_transaction_monthly_history").fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(tx_count, 3)
        self.assertEqual(page_count, 2)
        self.assertEqual(payload_count, 1)
        self.assertEqual(run_status, "success")
        self.assertEqual(amount_unit, "cents")
        self.assertEqual(detail_count, 3)
        self.assertEqual(related_count, 6)
        self.assertEqual(monthly_count, 6)


if __name__ == "__main__":
    unittest.main()
