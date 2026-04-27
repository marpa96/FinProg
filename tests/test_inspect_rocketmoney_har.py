import unittest
from pathlib import Path

from scripts.inspect_rocketmoney_har import iter_graphql_requests, load_har, summarize_operations


class InspectRocketMoneyHarTests(unittest.TestCase):
    def test_extracts_graphql_operations_and_counts(self) -> None:
        har_path = Path("tests/fixtures/sample_rocketmoney.har")
        loaded = load_har(har_path)
        graphql_requests = iter_graphql_requests(loaded)
        counts = summarize_operations(graphql_requests)

        self.assertEqual(len(graphql_requests), 2)
        self.assertEqual(counts["RefreshAuthToken"], 1)
        self.assertEqual(counts["TransactionsPageTransactionTable"], 1)
        self.assertEqual(
            graphql_requests[1]["payload"]["extensions"]["persistedQuery"]["sha256Hash"],
            "transactions-hash",
        )


if __name__ == "__main__":
    unittest.main()
