from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONSOLIDATED_DATABASE = Path("data/private/finprog_consolidated.db")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def normalize_amount_to_cents(amount_raw: Any, amount_unit: str | None) -> int | None:
    if amount_raw is None:
        return None
    if amount_unit == "cents":
        return int(round(float(amount_raw)))
    if amount_unit == "dollars":
        return int(round(float(amount_raw) * 100))
    return int(round(float(amount_raw)))


def amount_sign(amount_cents: int | None) -> str:
    if amount_cents is None or amount_cents == 0:
        return "zero"
    return "negative" if amount_cents < 0 else "positive"


def planning_type_from_source_sign(source_sign: str, expense_sign: str, income_sign: str) -> str | None:
    if source_sign == "zero":
        return None
    if source_sign == expense_sign:
        return "expense"
    if source_sign == income_sign:
        return "income"
    return None


class ConsolidatedFinanceStore:
    def __init__(self, db_path: Path = DEFAULT_CONSOLIDATED_DATABASE) -> None:
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
            CREATE TABLE IF NOT EXISTS finance_sources (
                source_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                raw_database_path TEXT,
                default_amount_unit TEXT NOT NULL DEFAULT 'cents',
                expense_sign TEXT NOT NULL DEFAULT 'negative',
                income_sign TEXT NOT NULL DEFAULT 'positive',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS finance_source_transactions (
                source_id TEXT NOT NULL,
                source_transaction_id TEXT NOT NULL,
                posted_date TEXT,
                description TEXT,
                source_note TEXT,
                source_amount_raw REAL,
                source_amount_unit TEXT,
                source_amount_cents INTEGER,
                source_amount_sign TEXT NOT NULL,
                normalized_magnitude_cents INTEGER,
                planning_amount_cents INTEGER,
                planning_direction TEXT,
                planning_type_guess TEXT,
                source_category_id TEXT,
                source_category_name TEXT,
                source_account_id TEXT,
                source_service_id TEXT,
                source_subscription_id TEXT,
                pending INTEGER,
                source_status TEXT,
                raw_json TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY (source_id, source_transaction_id),
                FOREIGN KEY (source_id) REFERENCES finance_sources(source_id)
            );

            CREATE TABLE IF NOT EXISTS finance_classification_rules (
                rule_id TEXT PRIMARY KEY,
                source_id TEXT,
                priority INTEGER NOT NULL DEFAULT 100,
                match_field TEXT NOT NULL,
                match_operator TEXT NOT NULL,
                match_value TEXT NOT NULL,
                planning_label TEXT,
                normalized_type TEXT,
                cashflow_class TEXT,
                category_id TEXT,
                subcategory_id TEXT,
                income_rule_key TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS finance_transaction_classifications (
                source_id TEXT NOT NULL,
                source_transaction_id TEXT NOT NULL,
                rule_id TEXT,
                planning_label TEXT,
                normalized_type TEXT,
                cashflow_class TEXT,
                category_id TEXT,
                subcategory_id TEXT,
                income_rule_key TEXT,
                confidence TEXT NOT NULL,
                reviewed INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (source_id, source_transaction_id),
                FOREIGN KEY (source_id, source_transaction_id)
                    REFERENCES finance_source_transactions(source_id, source_transaction_id),
                FOREIGN KEY (rule_id) REFERENCES finance_classification_rules(rule_id)
            );
            """
        )
        self._ensure_column(connection, "finance_sources", "default_amount_unit", "TEXT NOT NULL DEFAULT 'cents'")
        self._ensure_column(connection, "finance_sources", "expense_sign", "TEXT NOT NULL DEFAULT 'negative'")
        self._ensure_column(connection, "finance_sources", "income_sign", "TEXT NOT NULL DEFAULT 'positive'")
        self._ensure_column(connection, "finance_source_transactions", "planning_amount_cents", "INTEGER")
        self._ensure_column(connection, "finance_source_transactions", "planning_direction", "TEXT")
        self._ensure_column(connection, "finance_source_transactions", "planning_type_guess", "TEXT")
        self._ensure_column(connection, "finance_source_transactions", "source_note", "TEXT")

    def _ensure_column(self, connection: sqlite3.Connection, table_name: str, column_name: str, column_definition: str) -> None:
        columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}
        if column_name not in columns:
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")

    def upsert_source(
        self,
        connection: sqlite3.Connection,
        source_id: str,
        display_name: str,
        source_type: str,
        raw_database_path: str | None,
        default_amount_unit: str = "cents",
        expense_sign: str = "negative",
        income_sign: str = "positive",
    ) -> None:
        now = utc_now()
        connection.execute(
            """
            INSERT INTO finance_sources (
                source_id, display_name, source_type, raw_database_path,
                default_amount_unit, expense_sign, income_sign, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                display_name = excluded.display_name,
                source_type = excluded.source_type,
                raw_database_path = excluded.raw_database_path,
                default_amount_unit = excluded.default_amount_unit,
                expense_sign = excluded.expense_sign,
                income_sign = excluded.income_sign,
                updated_at = excluded.updated_at
            """,
            (source_id, display_name, source_type, raw_database_path, default_amount_unit, expense_sign, income_sign, now, now),
        )

    def upsert_source_transactions(self, connection: sqlite3.Connection, source_id: str, rows: list[dict[str, Any]]) -> int:
        now = utc_now()
        source = connection.execute(
            "SELECT default_amount_unit, expense_sign, income_sign FROM finance_sources WHERE source_id = ?",
            (source_id,),
        ).fetchone()
        default_unit = source["default_amount_unit"] if source else "cents"
        expense_sign = source["expense_sign"] if source else "negative"
        income_sign = source["income_sign"] if source else "positive"
        for row in rows:
            source_amount_unit = row.get("sourceAmountUnit") or default_unit
            amount_cents = normalize_amount_to_cents(row.get("sourceAmountRaw"), source_amount_unit)
            source_sign = amount_sign(amount_cents)
            type_guess = planning_type_from_source_sign(source_sign, expense_sign, income_sign)
            planning_amount_cents = None
            if amount_cents is not None and type_guess:
                planning_amount_cents = -abs(amount_cents) if type_guess == "expense" else abs(amount_cents)
            connection.execute(
                """
                INSERT INTO finance_source_transactions (
                    source_id, source_transaction_id, posted_date, description,
                    source_note, source_amount_raw, source_amount_unit, source_amount_cents,
                    source_amount_sign, normalized_magnitude_cents,
                    planning_amount_cents, planning_direction, planning_type_guess,
                    source_category_id, source_category_name, source_account_id,
                    source_service_id, source_subscription_id, pending, source_status,
                    raw_json, first_seen_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, source_transaction_id) DO UPDATE SET
                    posted_date = excluded.posted_date,
                    description = excluded.description,
                    source_note = excluded.source_note,
                    source_amount_raw = excluded.source_amount_raw,
                    source_amount_unit = excluded.source_amount_unit,
                    source_amount_cents = excluded.source_amount_cents,
                    source_amount_sign = excluded.source_amount_sign,
                    normalized_magnitude_cents = excluded.normalized_magnitude_cents,
                    planning_amount_cents = excluded.planning_amount_cents,
                    planning_direction = excluded.planning_direction,
                    planning_type_guess = excluded.planning_type_guess,
                    source_category_id = excluded.source_category_id,
                    source_category_name = excluded.source_category_name,
                    source_account_id = excluded.source_account_id,
                    source_service_id = excluded.source_service_id,
                    source_subscription_id = excluded.source_subscription_id,
                    pending = excluded.pending,
                    source_status = excluded.source_status,
                    raw_json = excluded.raw_json,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    source_id,
                    row["sourceTransactionId"],
                    row.get("postedDate"),
                    row.get("description"),
                    row.get("sourceNote"),
                    row.get("sourceAmountRaw"),
                    source_amount_unit,
                    amount_cents,
                    source_sign,
                    abs(amount_cents) if amount_cents is not None else None,
                    planning_amount_cents,
                    amount_sign(planning_amount_cents),
                    type_guess,
                    row.get("sourceCategoryId"),
                    row.get("sourceCategoryName"),
                    row.get("sourceAccountId"),
                    row.get("sourceServiceId"),
                    row.get("sourceSubscriptionId"),
                    int(bool(row.get("pending"))) if row.get("pending") is not None else None,
                    row.get("sourceStatus"),
                    json_text(row.get("raw") or {}),
                    now,
                    now,
                ),
            )
        return len(rows)

    def upsert_classification_rule(self, connection: sqlite3.Connection, rule: dict[str, Any]) -> None:
        now = utc_now()
        connection.execute(
            """
            INSERT INTO finance_classification_rules (
                rule_id, source_id, priority, match_field, match_operator, match_value,
                planning_label, normalized_type, cashflow_class, category_id, subcategory_id,
                income_rule_key, active, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rule_id) DO UPDATE SET
                source_id = excluded.source_id,
                priority = excluded.priority,
                match_field = excluded.match_field,
                match_operator = excluded.match_operator,
                match_value = excluded.match_value,
                planning_label = excluded.planning_label,
                normalized_type = excluded.normalized_type,
                cashflow_class = excluded.cashflow_class,
                category_id = excluded.category_id,
                subcategory_id = excluded.subcategory_id,
                income_rule_key = excluded.income_rule_key,
                active = excluded.active,
                updated_at = excluded.updated_at
            """,
            (
                rule["ruleId"],
                rule.get("sourceId"),
                int(rule.get("priority", 100)),
                rule["matchField"],
                rule.get("matchOperator", "contains"),
                rule["matchValue"],
                rule.get("planningLabel"),
                rule.get("normalizedType"),
                rule.get("cashflowClass"),
                rule.get("categoryId"),
                rule.get("subcategoryId"),
                rule.get("incomeRuleKey"),
                int(rule.get("active", True) is not False),
                now,
                now,
            ),
        )

    def list_source_transactions(
        self,
        connection: sqlite3.Connection,
        limit: int = 200,
        source_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        parameters: list[Any] = []
        where_clauses = []
        if source_id:
            where_clauses.append("tx.source_id = ?")
            parameters.append(source_id)
        if start_date:
            where_clauses.append("tx.posted_date >= ?")
            parameters.append(start_date)
        if end_date:
            where_clauses.append("tx.posted_date <= ?")
            parameters.append(end_date)
        where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        parameters.extend([limit, offset])
        rows = connection.execute(
            f"""
            SELECT
                tx.source_id,
                src.display_name AS source_name,
                tx.source_transaction_id,
                tx.posted_date,
                tx.description,
                tx.source_note,
                tx.source_amount_cents,
                tx.source_amount_unit,
                tx.source_amount_sign,
                tx.normalized_magnitude_cents,
                tx.planning_amount_cents,
                tx.planning_direction,
                tx.planning_type_guess,
                tx.source_category_name,
                tx.source_account_id,
                tx.source_service_id,
                tx.source_subscription_id,
                tx.pending,
                tx.source_status,
                tx.raw_json,
                cls.planning_label,
                cls.normalized_type,
                cls.cashflow_class,
                cls.category_id,
                cls.subcategory_id,
                cls.reviewed
            FROM finance_source_transactions tx
            JOIN finance_sources src ON src.source_id = tx.source_id
            LEFT JOIN finance_transaction_classifications cls
                ON cls.source_id = tx.source_id
                AND cls.source_transaction_id = tx.source_transaction_id
            {where_clause}
            ORDER BY COALESCE(tx.posted_date, '') DESC, tx.source_transaction_id
            LIMIT ? OFFSET ?
            """,
            parameters,
        ).fetchall()
        transactions = []
        for row in rows:
            raw = {}
            if row["raw_json"]:
                try:
                    raw = json.loads(row["raw_json"])
                except json.JSONDecodeError:
                    raw = {}
            transactions.append(
                {
                    "sourceId": row["source_id"],
                    "sourceName": row["source_name"],
                    "sourceTransactionId": row["source_transaction_id"],
                    "postedDate": row["posted_date"],
                    "description": row["description"],
                    "sourceNote": row["source_note"],
                    "sourceAmountCents": row["source_amount_cents"],
                    "sourceAmountUnit": row["source_amount_unit"],
                    "sourceAmountSign": row["source_amount_sign"],
                    "normalizedMagnitudeCents": row["normalized_magnitude_cents"],
                    "planningAmountCents": row["planning_amount_cents"],
                    "planningDirection": row["planning_direction"],
                    "planningTypeGuess": row["planning_type_guess"],
                    "sourceCategoryName": row["source_category_name"],
                    "sourceAccountId": row["source_account_id"],
                    "sourceServiceId": row["source_service_id"],
                    "sourceSubscriptionId": row["source_subscription_id"],
                    "pending": bool(row["pending"]) if row["pending"] is not None else None,
                    "sourceStatus": row["source_status"],
                    "planningLabel": row["planning_label"],
                    "normalizedType": row["normalized_type"],
                    "cashflowClass": row["cashflow_class"],
                    "categoryId": row["category_id"],
                    "subcategoryId": row["subcategory_id"],
                    "reviewed": bool(row["reviewed"]) if row["reviewed"] is not None else False,
                    "raw": raw,
                }
            )
        return transactions

    def count_source_transactions(
        self,
        connection: sqlite3.Connection,
        source_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        parameters: list[Any] = []
        where_clauses = []
        if source_id:
            where_clauses.append("source_id = ?")
            parameters.append(source_id)
        if start_date:
            where_clauses.append("posted_date >= ?")
            parameters.append(start_date)
        if end_date:
            where_clauses.append("posted_date <= ?")
            parameters.append(end_date)
        where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        row = connection.execute(
            f"SELECT COUNT(*) AS transaction_count FROM finance_source_transactions {where_clause}",
            parameters,
        ).fetchone()
        return int(row["transaction_count"] if row else 0)


def rocketmoney_rows_for_consolidation(rocketmoney_db_path: Path) -> list[dict[str, Any]]:
    connection = sqlite3.connect(rocketmoney_db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT
                tx.transaction_id,
                tx.posted_date,
                COALESCE(tx.short_name, tx.long_name) AS description,
                tx.note,
                tx.amount_raw,
                tx.amount_unit,
                tx.category_id,
                cat.label AS category_name,
                tx.account_id,
                tx.service_id,
                tx.subscription_id,
                tx.pending,
                tx.transaction_status,
                tx.raw_json
            FROM rocketmoney_transactions tx
            LEFT JOIN rocketmoney_categories cat ON cat.category_id = tx.category_id
            ORDER BY tx.posted_date DESC, tx.transaction_id
            """
        ).fetchall()
        return [
            {
                "sourceTransactionId": row["transaction_id"],
                "postedDate": row["posted_date"],
                "description": row["description"],
                "sourceNote": row["note"],
                "sourceAmountRaw": row["amount_raw"],
                "sourceAmountUnit": row["amount_unit"],
                "sourceCategoryId": row["category_id"],
                "sourceCategoryName": row["category_name"],
                "sourceAccountId": row["account_id"],
                "sourceServiceId": row["service_id"],
                "sourceSubscriptionId": row["subscription_id"],
                "pending": row["pending"],
                "sourceStatus": row["transaction_status"],
                "raw": json.loads(row["raw_json"]) if row["raw_json"] else {},
            }
            for row in rows
        ]
    finally:
        connection.close()


def sync_rocketmoney_to_consolidated(
    rocketmoney_db_path: Path,
    consolidated_db_path: Path = DEFAULT_CONSOLIDATED_DATABASE,
) -> dict[str, Any]:
    store = ConsolidatedFinanceStore(consolidated_db_path)
    connection = store.connect()
    try:
        store.ensure_schema(connection)
        store.upsert_source(
            connection,
            source_id="rocketmoney",
            display_name="Rocket Money",
            source_type="transaction_aggregator",
            raw_database_path=str(rocketmoney_db_path),
            default_amount_unit="cents",
            expense_sign="positive",
            income_sign="negative",
        )
        rows = rocketmoney_rows_for_consolidation(rocketmoney_db_path)
        count = store.upsert_source_transactions(connection, "rocketmoney", rows)
        connection.commit()
        return {
            "sourceId": "rocketmoney",
            "consolidatedDatabasePath": str(consolidated_db_path),
            "sourceTransactionCount": count,
        }
    finally:
        connection.close()
