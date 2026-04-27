"""Sync Rocket Money transaction data into the local SQLite database."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from extractors.rocket_money import RocketMoneyTransactionDetailExtractor
from scripts.extract_rocketmoney_transactions import DEFAULT_OUTPUT, build_headers, payload_to_jsonable, run_extraction
from scripts.local_env import load_env_file
from scripts.refresh_rocketmoney_cookie import refresh_cookie
from storage import sync_rocketmoney_payload_to_db


DEFAULT_DATABASE = Path("data/private/rocketmoney.db")


def progress(message: str) -> None:
    print(message, flush=True)


def build_mock_detail_transport():
    def fake_transport(payload: dict[str, object], headers: dict[str, str]) -> dict[str, object]:
        variables = payload.get("variables", {})
        transaction_id = variables.get("id")
        if payload.get("operationName") == "TransactionDetails":
            return {
                "data": {
                    "node": {
                        "id": transaction_id,
                        "shortName": f"Detail {transaction_id}",
                        "transactionRules": {"edges": []},
                        "relatedTransactions": {
                            "edges": [
                                {"node": {"id": transaction_id}},
                            ]
                        },
                        "splitParentTransaction": None,
                    }
                }
            }

        return {
            "data": {
                "node": {
                    "id": transaction_id,
                    "monthlyTransactionsBarChartData": [
                        {"date": "2026-04-01", "amountCents": 1000},
                        {"date": "2026-05-01", "amountCents": 2500},
                    ],
                    "relatedTransactions": {
                        "edges": [
                            {"node": {"id": transaction_id, "amount": 1000}},
                        ]
                    },
                }
            }
        }

    return fake_transport


def should_refresh_after_failure(exc: Exception) -> bool:
    message = str(exc).lower()
    auth_markers = [
        "http 401",
        "http 403",
        "unauthorized",
        "forbidden",
        "session",
        "expired",
        "login",
        "not authenticated",
    ]
    return any(marker in message for marker in auth_markers)


def main() -> int:
    load_env_file(ROOT / ".env")

    parser = argparse.ArgumentParser(description="Extract Rocket Money transactions and sync them into a local SQLite database.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--snapshot-output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-snapshot", action="store_true", help="Do not write the raw JSON snapshot file.")
    parser.add_argument("--skip-details", action="store_true", help="Skip per-transaction detail and history enrichment.")
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--start-cursor", default=None)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--no-refresh", action="store_true")
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        type=lambda value: tuple(part.strip() for part in value.split(":", 1)) if ":" in value else (_ for _ in ()).throw(argparse.ArgumentTypeError("headers must look like 'Header-Name: value'")),
        help="Extra request header, for example 'x-analytics-session: 1776128147754'.",
    )
    args = parser.parse_args()

    if args.page_size <= 0:
        raise SystemExit("--page-size must be greater than zero")
    if args.max_pages is not None and args.max_pages <= 0:
        raise SystemExit("--max-pages must be greater than zero")

    def extraction_progress(event: dict[str, object]) -> None:
        progress(
            "Fetched transaction page "
            f"{event['pageIndex']} with {event['edgeCount']} rows "
            f"(cursor {event['requestCursor']!r} -> {event['endCursor']!r}, "
            f"hasNext={event['hasNextPage']}, total seen {event['transactionCountSoFar']})."
        )

    progress("Starting Rocket Money transaction extraction...")
    try:
        extracted = run_extraction(args, progress_callback=extraction_progress)
    except Exception as exc:
        if args.no_refresh or not should_refresh_after_failure(exc):
            raise
        progress("Rocket Money session looks stale; refreshing cookies and retrying once.")
        refresh_cookie(Path("data/private/rocketmoney_refreshed_cookies.txt"), ROOT / ".env")
        extracted = run_extraction(args, progress_callback=extraction_progress)

    progress(
        f"Finished list extraction: {extracted.metadata.get('transactionCount')} transactions across "
        f"{extracted.metadata.get('pageCount')} pages."
    )

    snapshot_path: Path | None = None
    if not args.no_snapshot:
        snapshot_path = args.snapshot_output
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json.dumps(payload_to_jsonable(extracted), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        progress(f"Wrote raw snapshot to {snapshot_path}")

    details_by_id = None
    if not args.skip_details:
        transaction_ids = [transaction.get("id") for transaction in extracted.payload.get("transactions", []) if transaction.get("id")]
        if transaction_ids:
            progress(f"Fetching transaction details for {len(transaction_ids)} transaction(s)...")
            detail_headers = {"cookie": "mock"} if args.mock else build_headers(args.header, refresh_if_missing=False)
            detail_extractor = RocketMoneyTransactionDetailExtractor(
                headers=detail_headers,
                transport=build_mock_detail_transport() if args.mock else None,
                progress_callback=lambda event: progress(
                    f"Fetched detail bundle {event['current']}/{event['total']} for {event['transactionId']}"
                ),
            )
            details_by_id = detail_extractor.fetch_many(transaction_ids)
            progress(f"Finished detail enrichment for {len(details_by_id)} transaction(s).")
        else:
            progress("No transaction IDs were available for detail enrichment.")
    else:
        progress("Skipping transaction detail enrichment by request.")

    progress(f"Writing sync results into SQLite database at {args.database}...")
    summary = sync_rocketmoney_payload_to_db(
        db_path=args.database,
        extracted=extracted,
        raw_snapshot_path=str(snapshot_path) if snapshot_path else None,
        details_by_id=details_by_id,
    )

    progress(
        f"Synced {summary['transactionCount']} Rocket Money transactions across {summary['pageCount']} pages "
        f"into {args.database}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
