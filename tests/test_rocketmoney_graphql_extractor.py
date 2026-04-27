import unittest

from extractors.rocket_money import RocketMoneyGraphqlExtractor
from extractors.rocket_money.graphql import TRANSACTIONS_PERSISTED_QUERY_HASH


def page_response(start_cursor, end_cursor, has_next_page, edges):
    return {
        "data": {
            "viewer": {
                "transactions": {
                    "pageInfo": {
                        "startCursor": start_cursor,
                        "endCursor": end_cursor,
                        "hasNextPage": has_next_page,
                    },
                    "edges": edges,
                },
            },
        },
    }


class RocketMoneyGraphqlExtractorTests(unittest.TestCase):
    def test_uses_current_transactions_persisted_query_hash(self) -> None:
        extractor = RocketMoneyGraphqlExtractor(headers={"cookie": "private"})
        payload = extractor.build_payload(cursor=None)

        self.assertEqual(
            payload["extensions"]["persistedQuery"]["sha256Hash"],
            "62dace281f8028f3e883ba36f7400005f396f305dcdb7fe6faeba4f9877f9c06",
        )
        self.assertEqual(
            payload["extensions"]["persistedQuery"]["sha256Hash"],
            TRANSACTIONS_PERSISTED_QUERY_HASH,
        )

    def test_pages_by_end_cursor_until_done_and_deduplicates_nodes(self) -> None:
        request_cursors = []
        progress_events = []

        def fake_transport(payload, headers):
            request_cursors.append(payload["variables"]["cursor"])
            self.assertEqual(payload["variables"]["pageSize"], 2)
            self.assertIn("cookie", headers)

            if payload["variables"]["cursor"] is None:
                return page_response(
                    "0",
                    "1",
                    True,
                    [
                        {"cursor": "0", "node": {"id": "txn_0", "date": "2026-01-02", "amount": 100}},
                        {"cursor": "1", "node": {"id": "txn_1", "date": "2026-01-01", "amount": 200}},
                    ],
                )

            return page_response(
                "2",
                "3",
                False,
                [
                    {"cursor": "2", "node": {"id": "txn_1", "date": "2026-01-01", "amount": 200}},
                    {"cursor": "3", "node": {"id": "txn_3", "date": "2025-12-31", "amount": 300}},
                ],
            )

        extractor = RocketMoneyGraphqlExtractor(
            headers={"cookie": "private"},
            page_size=2,
            transport=fake_transport,
            progress_callback=progress_events.append,
        )

        extracted = extractor.extract()

        self.assertEqual(request_cursors, [None, "1"])
        self.assertEqual(len(progress_events), 2)
        self.assertEqual(progress_events[0]["pageIndex"], 1)
        self.assertEqual(progress_events[1]["pageIndex"], 2)
        self.assertEqual(extracted.metadata["pageCount"], 2)
        self.assertEqual(extracted.metadata["transactionCount"], 3)
        self.assertEqual(extracted.metadata["duplicateCount"], 1)
        self.assertEqual(extracted.payload["pages"][0]["endCursor"], "1")
        self.assertEqual(extracted.payload["transactions"][0]["_rocketMoneyCursor"], "0")

    def test_raises_graphql_errors(self) -> None:
        def fake_transport(payload, headers):
            return {"errors": [{"message": "session expired"}]}

        extractor = RocketMoneyGraphqlExtractor(headers={"cookie": "private"}, transport=fake_transport)

        with self.assertRaisesRegex(RuntimeError, "session expired"):
            extractor.extract()


if __name__ == "__main__":
    unittest.main()
