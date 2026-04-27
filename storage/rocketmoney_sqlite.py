from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from extractors import ExtractedPayload


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def amount_fields(raw_amount: Any) -> dict[str, Any]:
    if raw_amount is None:
        return {
            "amount_raw": None,
            "amount_display": None,
            "amount_cents": None,
            "amount_unit": None,
        }

    if isinstance(raw_amount, bool):
        raw_amount = int(raw_amount)

    if isinstance(raw_amount, int):
        return {
            "amount_raw": raw_amount,
            "amount_display": raw_amount / 100.0,
            "amount_cents": raw_amount,
            "amount_unit": "cents",
        }

    numeric = float(raw_amount)
    return {
        "amount_raw": numeric,
        "amount_display": numeric,
        "amount_cents": int(round(numeric * 100)),
        "amount_unit": "dollars",
    }


class RocketMoneySqliteStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def ensure_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS rocketmoney_sync_runs (
                sync_run_id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                source_name TEXT,
                started_at TEXT,
                completed_at TEXT,
                status TEXT NOT NULL,
                page_count INTEGER NOT NULL DEFAULT 0,
                transaction_count INTEGER NOT NULL DEFAULT 0,
                duplicate_count INTEGER NOT NULL DEFAULT 0,
                persisted_query_hash TEXT,
                raw_snapshot_path TEXT,
                error_text TEXT
            );

            CREATE TABLE IF NOT EXISTS rocketmoney_payload_snapshots (
                sync_run_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (sync_run_id) REFERENCES rocketmoney_sync_runs(sync_run_id)
            );

            CREATE TABLE IF NOT EXISTS rocketmoney_sync_pages (
                sync_run_id TEXT NOT NULL,
                page_index INTEGER NOT NULL,
                request_cursor TEXT,
                start_cursor TEXT,
                end_cursor TEXT,
                has_next_page INTEGER NOT NULL,
                edge_count INTEGER NOT NULL,
                PRIMARY KEY (sync_run_id, page_index),
                FOREIGN KEY (sync_run_id) REFERENCES rocketmoney_sync_runs(sync_run_id)
            );

            CREATE TABLE IF NOT EXISTS rocketmoney_categories (
                category_id TEXT PRIMARY KEY,
                label TEXT,
                type TEXT,
                icon_key TEXT,
                include_in_spending INTEGER,
                include_in_earnings INTEGER,
                tax_deductible INTEGER,
                category_type TEXT,
                raw_json TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rocketmoney_accounts (
                account_id TEXT PRIMARY KEY,
                source TEXT,
                is_issued_card INTEGER,
                raw_json TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rocketmoney_services (
                service_id TEXT PRIMARY KEY,
                service_key INTEGER,
                name TEXT,
                slug TEXT,
                square_logo TEXT,
                raw_json TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rocketmoney_subscriptions (
                subscription_id TEXT PRIMARY KEY,
                subscription_key INTEGER,
                custom_name TEXT,
                frequency INTEGER,
                is_income INTEGER,
                active INTEGER,
                start_date TEXT,
                end_date TEXT,
                expected_next_bill_date TEXT,
                next_charge_date TEXT,
                next_charge_amount_raw REAL,
                next_charge_amount_display REAL,
                next_charge_amount_cents INTEGER,
                next_charge_amount_unit TEXT,
                raw_json TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rocketmoney_transactions (
                transaction_id TEXT PRIMARY KEY,
                sync_run_id TEXT NOT NULL,
                cursor TEXT,
                posted_date TEXT,
                pending INTEGER,
                long_name TEXT,
                short_name TEXT,
                note TEXT,
                transaction_status TEXT,
                split_status TEXT,
                ignored_from TEXT,
                tax_deductible INTEGER,
                amount_raw REAL,
                amount_display REAL,
                amount_cents INTEGER,
                amount_unit TEXT,
                category_id TEXT,
                account_id TEXT,
                service_id TEXT,
                subscription_id TEXT,
                transaction_rule_node_ids_json TEXT,
                rewards_json TEXT,
                raw_json TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                FOREIGN KEY (sync_run_id) REFERENCES rocketmoney_sync_runs(sync_run_id),
                FOREIGN KEY (category_id) REFERENCES rocketmoney_categories(category_id),
                FOREIGN KEY (account_id) REFERENCES rocketmoney_accounts(account_id),
                FOREIGN KEY (service_id) REFERENCES rocketmoney_services(service_id),
                FOREIGN KEY (subscription_id) REFERENCES rocketmoney_subscriptions(subscription_id)
            );

            CREATE TABLE IF NOT EXISTS rocketmoney_transaction_details (
                transaction_id TEXT PRIMARY KEY,
                sync_run_id TEXT NOT NULL,
                transaction_details_json TEXT,
                transaction_history_json TEXT,
                split_parent_transaction_id TEXT,
                split_parent_transaction_json TEXT,
                transaction_rules_json TEXT,
                related_transactions_json TEXT,
                monthly_history_json TEXT,
                fetched_at TEXT NOT NULL,
                FOREIGN KEY (sync_run_id) REFERENCES rocketmoney_sync_runs(sync_run_id),
                FOREIGN KEY (transaction_id) REFERENCES rocketmoney_transactions(transaction_id)
            );

            CREATE TABLE IF NOT EXISTS rocketmoney_transaction_related (
                transaction_id TEXT NOT NULL,
                related_transaction_id TEXT NOT NULL,
                source_operation TEXT NOT NULL,
                node_json TEXT NOT NULL,
                PRIMARY KEY (transaction_id, related_transaction_id, source_operation),
                FOREIGN KEY (transaction_id) REFERENCES rocketmoney_transactions(transaction_id)
            );

            CREATE TABLE IF NOT EXISTS rocketmoney_transaction_monthly_history (
                transaction_id TEXT NOT NULL,
                bucket_date TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                PRIMARY KEY (transaction_id, bucket_date),
                FOREIGN KEY (transaction_id) REFERENCES rocketmoney_transactions(transaction_id)
            );
            """
        )

    def start_sync_run(self, connection: sqlite3.Connection, extracted: ExtractedPayload, raw_snapshot_path: str | None) -> str:
        sync_run_id = f"rocketmoney_sync_{uuid.uuid4().hex}"
        metadata = extracted.metadata
        connection.execute(
            """
            INSERT INTO rocketmoney_sync_runs (
                sync_run_id, source_type, source_name, started_at, completed_at, status,
                page_count, transaction_count, duplicate_count, persisted_query_hash, raw_snapshot_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sync_run_id,
                extracted.source_type,
                extracted.source_name,
                metadata.get("startedAt"),
                metadata.get("completedAt"),
                "running",
                int(metadata.get("pageCount") or 0),
                int(metadata.get("transactionCount") or 0),
                int(metadata.get("duplicateCount") or 0),
                metadata.get("persistedQueryHash"),
                raw_snapshot_path,
            ),
        )
        return sync_run_id

    def finalize_sync_run(self, connection: sqlite3.Connection, sync_run_id: str, status: str, error_text: str | None = None) -> None:
        connection.execute(
            """
            UPDATE rocketmoney_sync_runs
            SET status = ?, completed_at = ?, error_text = ?
            WHERE sync_run_id = ?
            """,
            (status, utc_now(), error_text, sync_run_id),
        )

    def upsert_category(self, connection: sqlite3.Connection, category: dict[str, Any], seen_at: str) -> str | None:
        category_id = category.get("id")
        if not category_id:
            return None
        connection.execute(
            """
            INSERT INTO rocketmoney_categories (
                category_id, label, type, icon_key, include_in_spending, include_in_earnings,
                tax_deductible, category_type, raw_json, first_seen_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(category_id) DO UPDATE SET
                label = excluded.label,
                type = excluded.type,
                icon_key = excluded.icon_key,
                include_in_spending = excluded.include_in_spending,
                include_in_earnings = excluded.include_in_earnings,
                tax_deductible = excluded.tax_deductible,
                category_type = excluded.category_type,
                raw_json = excluded.raw_json,
                last_seen_at = excluded.last_seen_at
            """,
            (
                category_id,
                category.get("label"),
                category.get("type"),
                category.get("iconKey"),
                int(bool(category.get("includeInSpending"))) if category.get("includeInSpending") is not None else None,
                int(bool(category.get("includeInEarnings"))) if category.get("includeInEarnings") is not None else None,
                int(bool(category.get("taxDeductible"))) if category.get("taxDeductible") is not None else None,
                category.get("categoryType"),
                json_text(category),
                seen_at,
                seen_at,
            ),
        )
        return category_id

    def upsert_account(self, connection: sqlite3.Connection, account: dict[str, Any], seen_at: str) -> str | None:
        account_id = account.get("id")
        if not account_id:
            return None
        connection.execute(
            """
            INSERT INTO rocketmoney_accounts (
                account_id, source, is_issued_card, raw_json, first_seen_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                source = excluded.source,
                is_issued_card = excluded.is_issued_card,
                raw_json = excluded.raw_json,
                last_seen_at = excluded.last_seen_at
            """,
            (
                account_id,
                account.get("source"),
                int(bool(account.get("isIssuedCard"))) if account.get("isIssuedCard") is not None else None,
                json_text(account),
                seen_at,
                seen_at,
            ),
        )
        return account_id

    def upsert_service(self, connection: sqlite3.Connection, service: dict[str, Any], seen_at: str) -> str | None:
        service_id = service.get("id")
        if not service_id:
            return None
        connection.execute(
            """
            INSERT INTO rocketmoney_services (
                service_id, service_key, name, slug, square_logo, raw_json, first_seen_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(service_id) DO UPDATE SET
                service_key = excluded.service_key,
                name = excluded.name,
                slug = excluded.slug,
                square_logo = excluded.square_logo,
                raw_json = excluded.raw_json,
                last_seen_at = excluded.last_seen_at
            """,
            (
                service_id,
                service.get("_id"),
                service.get("name"),
                service.get("slug"),
                service.get("square_logo"),
                json_text(service),
                seen_at,
                seen_at,
            ),
        )
        return service_id

    def upsert_subscription(self, connection: sqlite3.Connection, subscription: dict[str, Any], seen_at: str) -> str | None:
        subscription_id = subscription.get("id")
        if not subscription_id:
            return None
        next_charge = subscription.get("nextCharge") or {}
        next_charge_amount = amount_fields(next_charge.get("chargeAmount"))
        connection.execute(
            """
            INSERT INTO rocketmoney_subscriptions (
                subscription_id, subscription_key, custom_name, frequency, is_income, active,
                start_date, end_date, expected_next_bill_date, next_charge_date,
                next_charge_amount_raw, next_charge_amount_display, next_charge_amount_cents,
                next_charge_amount_unit, raw_json, first_seen_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(subscription_id) DO UPDATE SET
                subscription_key = excluded.subscription_key,
                custom_name = excluded.custom_name,
                frequency = excluded.frequency,
                is_income = excluded.is_income,
                active = excluded.active,
                start_date = excluded.start_date,
                end_date = excluded.end_date,
                expected_next_bill_date = excluded.expected_next_bill_date,
                next_charge_date = excluded.next_charge_date,
                next_charge_amount_raw = excluded.next_charge_amount_raw,
                next_charge_amount_display = excluded.next_charge_amount_display,
                next_charge_amount_cents = excluded.next_charge_amount_cents,
                next_charge_amount_unit = excluded.next_charge_amount_unit,
                raw_json = excluded.raw_json,
                last_seen_at = excluded.last_seen_at
            """,
            (
                subscription_id,
                subscription.get("_id"),
                subscription.get("custom_name"),
                subscription.get("frequency"),
                int(bool(subscription.get("isIncome"))) if subscription.get("isIncome") is not None else None,
                int(bool(subscription.get("active"))) if subscription.get("active") is not None else None,
                subscription.get("start_date"),
                subscription.get("end_date"),
                subscription.get("expected_next_bill_date"),
                next_charge.get("chargeDate"),
                next_charge_amount["amount_raw"],
                next_charge_amount["amount_display"],
                next_charge_amount["amount_cents"],
                next_charge_amount["amount_unit"],
                json_text(subscription),
                seen_at,
                seen_at,
            ),
        )
        return subscription_id

    def replace_sync_pages(self, connection: sqlite3.Connection, sync_run_id: str, pages: list[dict[str, Any]]) -> None:
        connection.execute("DELETE FROM rocketmoney_sync_pages WHERE sync_run_id = ?", (sync_run_id,))
        for index, page in enumerate(pages):
            connection.execute(
                """
                INSERT INTO rocketmoney_sync_pages (
                    sync_run_id, page_index, request_cursor, start_cursor, end_cursor, has_next_page, edge_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sync_run_id,
                    index,
                    page.get("requestCursor"),
                    page.get("startCursor"),
                    page.get("endCursor"),
                    int(bool(page.get("hasNextPage"))),
                    int(page.get("edgeCount") or 0),
                ),
            )

    def store_payload_snapshot(self, connection: sqlite3.Connection, sync_run_id: str, extracted: ExtractedPayload) -> None:
        connection.execute(
            """
            INSERT OR REPLACE INTO rocketmoney_payload_snapshots (sync_run_id, payload_json, created_at)
            VALUES (?, ?, ?)
            """,
            (sync_run_id, json_text(asdict(extracted)), utc_now()),
        )

    def upsert_transactions(self, connection: sqlite3.Connection, sync_run_id: str, transactions: list[dict[str, Any]]) -> dict[str, int]:
        seen_at = utc_now()
        category_count = 0
        account_count = 0
        service_count = 0
        subscription_count = 0

        for node in transactions:
            if self.upsert_category(connection, node.get("category") or {}, seen_at):
                category_count += 1
            if self.upsert_account(connection, node.get("account") or {}, seen_at):
                account_count += 1
            if self.upsert_service(connection, node.get("service") or {}, seen_at):
                service_count += 1
            subscription = node.get("subscription") or {}
            if subscription:
                if self.upsert_category(connection, subscription.get("transactionCategory") or {}, seen_at):
                    category_count += 1
                if self.upsert_service(connection, subscription.get("service") or {}, seen_at):
                    service_count += 1
                if self.upsert_subscription(connection, subscription, seen_at):
                    subscription_count += 1

            transaction_id = node.get("id") or f"cursor:{node.get('_rocketMoneyCursor')}"
            amount = amount_fields(node.get("amount"))
            connection.execute(
                """
                INSERT INTO rocketmoney_transactions (
                    transaction_id, sync_run_id, cursor, posted_date, pending, long_name, short_name,
                    note, transaction_status, split_status, ignored_from, tax_deductible,
                    amount_raw, amount_display, amount_cents, amount_unit,
                    category_id, account_id, service_id, subscription_id,
                    transaction_rule_node_ids_json, rewards_json, raw_json, first_seen_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(transaction_id) DO UPDATE SET
                    sync_run_id = excluded.sync_run_id,
                    cursor = excluded.cursor,
                    posted_date = excluded.posted_date,
                    pending = excluded.pending,
                    long_name = excluded.long_name,
                    short_name = excluded.short_name,
                    note = excluded.note,
                    transaction_status = excluded.transaction_status,
                    split_status = excluded.split_status,
                    ignored_from = excluded.ignored_from,
                    tax_deductible = excluded.tax_deductible,
                    amount_raw = excluded.amount_raw,
                    amount_display = excluded.amount_display,
                    amount_cents = excluded.amount_cents,
                    amount_unit = excluded.amount_unit,
                    category_id = excluded.category_id,
                    account_id = excluded.account_id,
                    service_id = excluded.service_id,
                    subscription_id = excluded.subscription_id,
                    transaction_rule_node_ids_json = excluded.transaction_rule_node_ids_json,
                    rewards_json = excluded.rewards_json,
                    raw_json = excluded.raw_json,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    transaction_id,
                    sync_run_id,
                    node.get("_rocketMoneyCursor"),
                    node.get("date"),
                    int(bool(node.get("pending"))) if node.get("pending") is not None else None,
                    node.get("longName"),
                    node.get("shortName"),
                    node.get("note"),
                    node.get("transactionStatus"),
                    node.get("splitStatus"),
                    node.get("ignoredFrom"),
                    int(bool(node.get("taxDeductible"))) if node.get("taxDeductible") is not None else None,
                    amount["amount_raw"],
                    amount["amount_display"],
                    amount["amount_cents"],
                    amount["amount_unit"],
                    (node.get("category") or {}).get("id"),
                    (node.get("account") or {}).get("id"),
                    (node.get("service") or {}).get("id"),
                    (node.get("subscription") or {}).get("id"),
                    json_text(node.get("transactionRuleNodeIds") or []),
                    json_text(node.get("rewards") or []),
                    json_text(node),
                    seen_at,
                    seen_at,
                ),
            )

        return {
            "categoriesTouched": category_count,
            "accountsTouched": account_count,
            "servicesTouched": service_count,
            "subscriptionsTouched": subscription_count,
            "transactionsUpserted": len(transactions),
        }

    def upsert_transaction_details(
        self,
        connection: sqlite3.Connection,
        sync_run_id: str,
        details_by_id: dict[str, dict[str, Any]],
    ) -> dict[str, int]:
        detail_rows = 0
        related_rows = 0
        monthly_rows = 0
        fetched_at = utc_now()

        for transaction_id, bundle in details_by_id.items():
            detail_node = bundle.get("transactionDetails") or {}
            history_node = bundle.get("transactionHistory") or {}
            split_parent = detail_node.get("splitParentTransaction") or history_node.get("splitParentTransaction") or {}
            related_detail_edges = (detail_node.get("relatedTransactions") or {}).get("edges") or []
            related_history_edges = (history_node.get("relatedTransactions") or {}).get("edges") or []
            monthly_history = history_node.get("monthlyTransactionsBarChartData") or []
            transaction_rules = (detail_node.get("transactionRules") or {}).get("edges") or []

            connection.execute(
                """
                INSERT INTO rocketmoney_transaction_details (
                    transaction_id, sync_run_id, transaction_details_json, transaction_history_json,
                    split_parent_transaction_id, split_parent_transaction_json, transaction_rules_json,
                    related_transactions_json, monthly_history_json, fetched_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(transaction_id) DO UPDATE SET
                    sync_run_id = excluded.sync_run_id,
                    transaction_details_json = excluded.transaction_details_json,
                    transaction_history_json = excluded.transaction_history_json,
                    split_parent_transaction_id = excluded.split_parent_transaction_id,
                    split_parent_transaction_json = excluded.split_parent_transaction_json,
                    transaction_rules_json = excluded.transaction_rules_json,
                    related_transactions_json = excluded.related_transactions_json,
                    monthly_history_json = excluded.monthly_history_json,
                    fetched_at = excluded.fetched_at
                """,
                (
                    transaction_id,
                    sync_run_id,
                    json_text(detail_node),
                    json_text(history_node),
                    split_parent.get("id"),
                    json_text(split_parent) if split_parent else None,
                    json_text(transaction_rules),
                    json_text(
                        {
                            "fromDetails": related_detail_edges,
                            "fromHistory": related_history_edges,
                        }
                    ),
                    json_text(monthly_history),
                    fetched_at,
                ),
            )
            detail_rows += 1

            connection.execute(
                "DELETE FROM rocketmoney_transaction_related WHERE transaction_id = ?",
                (transaction_id,),
            )
            for source_operation, edges in (
                ("TransactionDetails", related_detail_edges),
                ("TransactionHistoryPage", related_history_edges),
            ):
                for edge in edges:
                    node = edge.get("node") or {}
                    related_id = node.get("id")
                    if not related_id:
                        continue
                    connection.execute(
                        """
                        INSERT INTO rocketmoney_transaction_related (
                            transaction_id, related_transaction_id, source_operation, node_json
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (transaction_id, related_id, source_operation, json_text(node)),
                    )
                    related_rows += 1

            connection.execute(
                "DELETE FROM rocketmoney_transaction_monthly_history WHERE transaction_id = ?",
                (transaction_id,),
            )
            for bucket in monthly_history:
                bucket_date = bucket.get("date")
                amount_cents = bucket.get("amountCents")
                if bucket_date is None or amount_cents is None:
                    continue
                connection.execute(
                    """
                    INSERT INTO rocketmoney_transaction_monthly_history (
                        transaction_id, bucket_date, amount_cents
                    )
                    VALUES (?, ?, ?)
                    """,
                    (transaction_id, bucket_date, int(amount_cents)),
                )
                monthly_rows += 1

        return {
            "detailRowsUpserted": detail_rows,
            "relatedRowsUpserted": related_rows,
            "monthlyHistoryRowsUpserted": monthly_rows,
        }


def sync_rocketmoney_payload_to_db(
    db_path: Path,
    extracted: ExtractedPayload,
    raw_snapshot_path: str | None = None,
    details_by_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    store = RocketMoneySqliteStore(db_path)
    connection = store.connect()
    try:
        store.ensure_schema(connection)
        sync_run_id = store.start_sync_run(connection, extracted, raw_snapshot_path)
        try:
            store.store_payload_snapshot(connection, sync_run_id, extracted)
            pages = extracted.payload.get("pages", [])
            transactions = extracted.payload.get("transactions", [])
            store.replace_sync_pages(connection, sync_run_id, pages)
            counts = store.upsert_transactions(connection, sync_run_id, transactions)
            if details_by_id:
                counts.update(store.upsert_transaction_details(connection, sync_run_id, details_by_id))
            store.finalize_sync_run(connection, sync_run_id, status="success")
            connection.commit()
        except Exception as exc:
            store.finalize_sync_run(connection, sync_run_id, status="failed", error_text=str(exc))
            connection.commit()
            raise

        return {
            "syncRunId": sync_run_id,
            "databasePath": str(db_path),
            "pageCount": extracted.metadata.get("pageCount"),
            "transactionCount": extracted.metadata.get("transactionCount"),
            **counts,
        }
    finally:
        connection.close()
