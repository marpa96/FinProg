"""Sync Rocket Money transaction data into the local SQLite database."""

from __future__ import annotations

import argparse
import json
import random
import time
import sys
from pathlib import Path
from urllib import error

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from extractors.rocket_money import RocketMoneyTransactionDetailExtractor
from scripts.extract_rocketmoney_transactions import DEFAULT_OUTPUT, build_headers, payload_to_jsonable, run_extraction
from scripts.local_env import load_env_file
from scripts.progress_ui import progress_bar
from scripts.refresh_rocketmoney_cookie import refresh_cookie
from storage import (
    existing_rocketmoney_detail_ids,
    existing_rocketmoney_detail_signatures,
    existing_rocketmoney_transaction_ids,
    rocketmoney_transaction_ids_for_deep_scan,
    sync_rocketmoney_details_to_db,
    sync_rocketmoney_payload_to_db,
)
from storage.rocketmoney_sqlite import json_text


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


def fetch_details_with_retries(
    detail_extractor: RocketMoneyTransactionDetailExtractor,
    transaction_ids: list[str],
    retry_count: int,
    throttle_delay_seconds: float,
    request_delay_seconds: float,
    after_bundle=None,
) -> dict[str, dict[str, object]]:
    bundles: dict[str, dict[str, object]] = {}
    total = len(transaction_ids)
    with progress_bar("Fetching detail bundles", total) as bar:
        for index, transaction_id in enumerate(transaction_ids, start=1):
            attempt = 0
            while True:
                try:
                    bundles[transaction_id] = detail_extractor.fetch_transaction_bundle(transaction_id)
                    if after_bundle:
                        after_bundle(transaction_id, bundles[transaction_id])
                    break
                except (TimeoutError, error.URLError) as exc:
                    if attempt >= retry_count:
                        raise
                    wait_seconds = min(2 ** attempt, 10)
                    progress(
                        f"Detail bundle {index}/{total} for {transaction_id} timed out "
                        f"({exc}); retrying in {wait_seconds}s."
                    )
                    time.sleep(wait_seconds)
                    attempt += 1
                except RuntimeError as exc:
                    message = str(exc)
                    should_pause = any(marker in message for marker in ("HTTP 429", "HTTP 403", "HTTP 502", "HTTP 503", "HTTP 504"))
                    if not should_pause:
                        raise
                    jitter = random.uniform(0, min(30.0, throttle_delay_seconds * 0.1))
                    wait_seconds = throttle_delay_seconds + jitter
                    progress(
                        f"Rocket Money pushed back while fetching {transaction_id} ({message}). "
                        f"Pausing for {wait_seconds:.0f}s, then resuming from this transaction."
                    )
                    time.sleep(wait_seconds)
                    attempt = 0
            if request_delay_seconds > 0 and index < total:
                time.sleep(request_delay_seconds)
            bar.update(index, f"Fetched detail bundle {index}/{total}")
            if detail_extractor.progress_callback:
                detail_extractor.progress_callback(
                    {
                        "current": index,
                        "total": total,
                        "transactionId": transaction_id,
                    }
                )
    return bundles


def detail_signature(bundle: dict[str, object]) -> tuple[str | None, str | None]:
    details = bundle.get("transactionDetails")
    history = bundle.get("transactionHistory")
    return (
        json_text(details) if details is not None else None,
        json_text(history) if history is not None else None,
    )


def changed_detail_ids(
    previous_signatures: dict[str, tuple[str | None, str | None]],
    details_by_id: dict[str, dict[str, object]],
) -> list[str]:
    changed_ids = []
    for transaction_id, bundle in details_by_id.items():
        previous = previous_signatures.get(transaction_id)
        if previous is not None and previous != detail_signature(bundle):
            changed_ids.append(transaction_id)
    return changed_ids


def main() -> int:
    load_env_file(ROOT / ".env")

    parser = argparse.ArgumentParser(description="Extract Rocket Money transactions and sync them into a local SQLite database.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--snapshot-output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-snapshot", action="store_true", help="Do not write the raw JSON snapshot file.")
    parser.add_argument("--skip-details", action="store_true", help="Skip per-transaction detail and history enrichment.")
    parser.add_argument(
        "--transaction-mode",
        choices=("quick", "full"),
        default="quick",
        help="quick stops transaction paging at the first known transaction, full pages through all available transactions.",
    )
    parser.add_argument(
        "--detail-mode",
        choices=("quick", "full", "skip"),
        default="quick",
        help="quick fetches only missing detail/history rows, full refetches every detail bundle, skip fetches none.",
    )
    parser.add_argument("--detail-retries", type=int, default=2, help="Retries per detail/history bundle after transient timeouts.")
    parser.add_argument(
        "--detail-throttle-delay",
        type=float,
        default=900.0,
        help="Seconds to pause before resuming when Rocket Money returns 403/429/5xx during detail enrichment.",
    )
    parser.add_argument(
        "--detail-request-delay",
        type=float,
        default=None,
        help="Seconds to wait between detail bundles. Defaults to 0 for quick mode and 0.75 for full mode.",
    )
    parser.add_argument("--detail-limit", type=int, default=None, help="Maximum number of detail bundles to fetch in this run.")
    parser.add_argument("--detail-recent-days", type=int, default=None, help="When refetching full details, restrict to transactions posted in the last N days.")
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
    if args.detail_retries < 0:
        raise SystemExit("--detail-retries cannot be negative")
    if args.detail_throttle_delay < 0:
        raise SystemExit("--detail-throttle-delay cannot be negative")
    if args.detail_request_delay is not None and args.detail_request_delay < 0:
        raise SystemExit("--detail-request-delay cannot be negative")
    if args.detail_limit is not None and args.detail_limit <= 0:
        raise SystemExit("--detail-limit must be greater than zero")
    if args.detail_recent_days is not None and args.detail_recent_days <= 0:
        raise SystemExit("--detail-recent-days must be greater than zero")
    if args.skip_details:
        args.detail_mode = "skip"
    if args.detail_request_delay is None:
        args.detail_request_delay = 0.75 if args.detail_mode == "full" else 0.0

    def extraction_progress(event: dict[str, object]) -> None:
        progress(
            "Fetched transaction page "
            f"{event['pageIndex']} with {event['edgeCount']} rows "
            f"(cursor {event['requestCursor']!r} -> {event['endCursor']!r}, "
            f"hasNext={event['hasNextPage']}, total seen {event['transactionCountSoFar']})."
        )

    known_transaction_ids = set()
    if args.transaction_mode == "quick":
        known_transaction_ids = existing_rocketmoney_transaction_ids(args.database)
        args.known_transaction_ids = known_transaction_ids
        if known_transaction_ids:
            progress(f"Quick transaction mode will stop at the first known transaction ({len(known_transaction_ids)} local transaction(s)).")
    else:
        args.known_transaction_ids = set()

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
    if extracted.metadata.get("stoppedBecauseKnownTransaction"):
        progress(f"Stopped transaction paging at known transaction {extracted.metadata.get('knownBoundaryTransactionId')}.")

    snapshot_path: Path | None = None
    if not args.no_snapshot:
        snapshot_path = args.snapshot_output
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json.dumps(payload_to_jsonable(extracted), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        progress(f"Wrote raw snapshot to {snapshot_path}")

    progress(f"Writing sync results into SQLite database at {args.database}...")
    summary = sync_rocketmoney_payload_to_db(
        db_path=args.database,
        extracted=extracted,
        raw_snapshot_path=str(snapshot_path) if snapshot_path else None,
    )
    progress(
        f"Synced transaction list: {summary['transactionCount']} Rocket Money transactions across "
        f"{summary['pageCount']} pages into {args.database}"
    )

    new_transaction_ids = [transaction.get("id") for transaction in extracted.payload.get("transactions", []) if transaction.get("id")]
    if args.transaction_mode == "quick":
        progress(f"Hey! I found {len(new_transaction_ids)} new Rocket Money transaction(s).")

    transaction_ids = new_transaction_ids
    if args.detail_mode == "full":
        transaction_ids = rocketmoney_transaction_ids_for_deep_scan(
            args.database,
            recent_days=args.detail_recent_days,
            limit=args.detail_limit,
        )
        if args.detail_recent_days is not None:
            progress(f"Deep detail mode is limited to the last {args.detail_recent_days} day(s).")
        if args.detail_limit is not None:
            progress(f"Deep detail mode budget is {args.detail_limit} bundle(s) for this run.")
    if args.detail_mode == "skip":
        progress("Skipping transaction detail enrichment by request.")
    elif transaction_ids:
        detail_transaction_ids = transaction_ids
        previous_detail_signatures = existing_rocketmoney_detail_signatures(args.database, detail_transaction_ids)
        if args.detail_mode == "quick":
            existing_detail_ids = existing_rocketmoney_detail_ids(args.database, transaction_ids)
            detail_transaction_ids = [transaction_id for transaction_id in transaction_ids if transaction_id not in existing_detail_ids]
            progress(
                f"Quick detail mode found {len(existing_detail_ids)} existing detail row(s); "
                f"{len(detail_transaction_ids)} missing bundle(s) need fetching."
            )
        else:
            progress(f"Deep detail mode will refetch {len(detail_transaction_ids)} transaction detail bundle(s) and report changed old records.")

        if detail_transaction_ids:
            progress(f"Fetching transaction details for {len(detail_transaction_ids)} transaction(s)...")
            detail_headers = {"cookie": "mock"} if args.mock else build_headers(args.header, refresh_if_missing=False)
            detail_extractor = RocketMoneyTransactionDetailExtractor(
                headers=detail_headers,
                transport=build_mock_detail_transport() if args.mock else None,
            )
            changed_ids = []
            detail_counts = {
                "detailRowsUpserted": 0,
                "relatedRowsUpserted": 0,
                "monthlyHistoryRowsUpserted": 0,
            }

            def persist_detail_bundle(transaction_id: str, bundle: dict[str, object]) -> None:
                if transaction_id in previous_detail_signatures and previous_detail_signatures[transaction_id] != detail_signature(bundle):
                    changed_ids.append(transaction_id)
                counts = sync_rocketmoney_details_to_db(args.database, summary["syncRunId"], {transaction_id: bundle})
                for key, value in counts.items():
                    detail_counts[key] = detail_counts.get(key, 0) + value

            details_by_id = fetch_details_with_retries(
                detail_extractor,
                detail_transaction_ids,
                args.detail_retries,
                args.detail_throttle_delay,
                args.detail_request_delay,
                after_bundle=persist_detail_bundle,
            )
            summary.update(detail_counts)
            progress(f"Finished detail enrichment for {len(details_by_id)} transaction(s).")
            if args.detail_mode == "full":
                if changed_ids:
                    progress(f"Hey, {len(changed_ids)} existing transaction detail bundle(s) changed on Rocket Money:")
                    for transaction_id in changed_ids[:10]:
                        progress(f"- {transaction_id}")
                    if len(changed_ids) > 10:
                        progress(f"- ...and {len(changed_ids) - 10} more.")
                else:
                    progress("Deep detail check found no changes in existing transaction detail bundles.")
        else:
            progress("No missing detail bundles to fetch.")
    else:
        progress("No transaction IDs were available for detail enrichment.")

    progress(
        f"Synced {summary['transactionCount']} Rocket Money transactions across {summary['pageCount']} pages "
        f"into {args.database}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
