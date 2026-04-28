from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_SCHEDULER_DATABASE = Path("data/private/sync_scheduler.db")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


DEFAULT_ROCKETMONEY_POLICY = {
    "sourceId": "rocketmoney",
    "enabled": True,
    "quickIntervalMinutes": 60,
    "dailyRecentDays": 90,
    "dailyDetailBudget": 250,
    "weeklyDetailBudget": 750,
    "monthlyDetailBudget": 1500,
    "deepRequestDelaySeconds": 3.0,
    "pressureBackoffMinutes": 60,
}


class SyncSchedulerStore:
    def __init__(self, db_path: Path = DEFAULT_SCHEDULER_DATABASE) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def ensure_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sync_source_policies (
                source_id TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL,
                quick_interval_minutes INTEGER NOT NULL,
                daily_recent_days INTEGER NOT NULL,
                daily_detail_budget INTEGER NOT NULL,
                weekly_detail_budget INTEGER NOT NULL,
                monthly_detail_budget INTEGER NOT NULL,
                deep_request_delay_seconds REAL NOT NULL,
                pressure_backoff_minutes INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sync_source_state (
                source_id TEXT PRIMARY KEY,
                last_quick_sync_at TEXT,
                last_daily_deep_sync_at TEXT,
                last_weekly_deep_sync_at TEXT,
                last_monthly_deep_sync_at TEXT,
                backoff_until TEXT,
                running_lane TEXT,
                last_status TEXT,
                last_summary_json TEXT,
                updated_at TEXT NOT NULL
            );
            """
        )

    def ensure_default_sources(self) -> None:
        connection = self.connect()
        try:
            self.ensure_schema(connection)
            self.upsert_policy(connection, DEFAULT_ROCKETMONEY_POLICY)
            connection.commit()
        finally:
            connection.close()

    def upsert_policy(self, connection: sqlite3.Connection, policy: dict[str, Any]) -> None:
        connection.execute(
            """
            INSERT INTO sync_source_policies (
                source_id, enabled, quick_interval_minutes, daily_recent_days,
                daily_detail_budget, weekly_detail_budget, monthly_detail_budget,
                deep_request_delay_seconds, pressure_backoff_minutes, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO NOTHING
            """,
            (
                policy["sourceId"],
                int(bool(policy["enabled"])),
                int(policy["quickIntervalMinutes"]),
                int(policy["dailyRecentDays"]),
                int(policy["dailyDetailBudget"]),
                int(policy["weeklyDetailBudget"]),
                int(policy["monthlyDetailBudget"]),
                float(policy["deepRequestDelaySeconds"]),
                int(policy["pressureBackoffMinutes"]),
                iso_now(),
            ),
        )
        connection.execute(
            """
            INSERT INTO sync_source_state (source_id, last_status, last_summary_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source_id) DO NOTHING
            """,
            (policy["sourceId"], "idle", "{}", iso_now()),
        )

    def source_snapshot(self, source_id: str) -> dict[str, Any]:
        connection = self.connect()
        try:
            self.ensure_schema(connection)
            policy = connection.execute(
                "SELECT * FROM sync_source_policies WHERE source_id = ?",
                (source_id,),
            ).fetchone()
            state = connection.execute(
                "SELECT * FROM sync_source_state WHERE source_id = ?",
                (source_id,),
            ).fetchone()
            if policy is None:
                return {"sourceId": source_id, "enabled": False, "lastStatus": "missing"}
            return self._snapshot_from_rows(policy, state)
        finally:
            connection.close()

    def due_lanes(self, source_id: str) -> list[dict[str, Any]]:
        connection = self.connect()
        try:
            self.ensure_schema(connection)
            policy = connection.execute(
                "SELECT * FROM sync_source_policies WHERE source_id = ?",
                (source_id,),
            ).fetchone()
            state = connection.execute(
                "SELECT * FROM sync_source_state WHERE source_id = ?",
                (source_id,),
            ).fetchone()
            if policy is None or not policy["enabled"]:
                return []

            now = utc_now()
            if state and parse_iso(state["backoff_until"]) and parse_iso(state["backoff_until"]) > now:
                return []
            if state and state["running_lane"]:
                return []

            due = []
            if self._older_than(state["last_quick_sync_at"] if state else None, minutes=policy["quick_interval_minutes"]):
                due.append({"lane": "quick", "sourceId": source_id})
            if self._older_than(state["last_daily_deep_sync_at"] if state else None, hours=24):
                due.append({
                    "lane": "daily",
                    "sourceId": source_id,
                    "recentDays": policy["daily_recent_days"],
                    "detailBudget": policy["daily_detail_budget"],
                    "deepRequestDelaySeconds": policy["deep_request_delay_seconds"],
                    "pressureBackoffMinutes": policy["pressure_backoff_minutes"],
                })
            if self._older_than(state["last_weekly_deep_sync_at"] if state else None, days=7):
                due.append({
                    "lane": "weekly",
                    "sourceId": source_id,
                    "detailBudget": policy["weekly_detail_budget"],
                    "deepRequestDelaySeconds": policy["deep_request_delay_seconds"],
                    "pressureBackoffMinutes": policy["pressure_backoff_minutes"],
                })
            if self._older_than(state["last_monthly_deep_sync_at"] if state else None, days=30):
                due.append({
                    "lane": "monthly",
                    "sourceId": source_id,
                    "detailBudget": policy["monthly_detail_budget"],
                    "deepRequestDelaySeconds": policy["deep_request_delay_seconds"],
                    "pressureBackoffMinutes": policy["pressure_backoff_minutes"],
                })
            return due
        finally:
            connection.close()

    def mark_started(self, source_id: str, lane: str) -> None:
        self._update_state(source_id, {"running_lane": lane, "last_status": "running"})

    def mark_finished(self, source_id: str, lane: str, status: str, summary: dict[str, Any]) -> None:
        updates: dict[str, Any] = {
            "running_lane": None,
            "last_status": status,
            "last_summary_json": json.dumps(summary, sort_keys=True),
        }
        if lane == "quick":
            updates["last_quick_sync_at"] = iso_now()
        elif lane == "daily":
            updates["last_daily_deep_sync_at"] = iso_now()
        elif lane == "weekly":
            updates["last_weekly_deep_sync_at"] = iso_now()
        elif lane == "monthly":
            updates["last_monthly_deep_sync_at"] = iso_now()
        self._update_state(source_id, updates)

    def set_backoff(self, source_id: str, minutes: int, reason: str) -> None:
        backoff_until = (utc_now() + timedelta(minutes=minutes)).isoformat()
        self._update_state(
            source_id,
            {
                "running_lane": None,
                "last_status": "backoff",
                "backoff_until": backoff_until,
                "last_summary_json": json.dumps({"reason": reason, "backoffUntil": backoff_until}, sort_keys=True),
            },
        )

    def _update_state(self, source_id: str, updates: dict[str, Any]) -> None:
        connection = self.connect()
        try:
            self.ensure_schema(connection)
            assignments = [f"{key} = ?" for key in updates]
            values = list(updates.values())
            assignments.append("updated_at = ?")
            values.append(iso_now())
            values.append(source_id)
            connection.execute(
                f"UPDATE sync_source_state SET {', '.join(assignments)} WHERE source_id = ?",
                values,
            )
            connection.commit()
        finally:
            connection.close()

    def _snapshot_from_rows(self, policy: sqlite3.Row, state: sqlite3.Row | None) -> dict[str, Any]:
        summary = {}
        if state and state["last_summary_json"]:
            try:
                summary = json.loads(state["last_summary_json"])
            except json.JSONDecodeError:
                summary = {}
        return {
            "sourceId": policy["source_id"],
            "enabled": bool(policy["enabled"]),
            "policy": {
                "quickIntervalMinutes": policy["quick_interval_minutes"],
                "dailyRecentDays": policy["daily_recent_days"],
                "dailyDetailBudget": policy["daily_detail_budget"],
                "weeklyDetailBudget": policy["weekly_detail_budget"],
                "monthlyDetailBudget": policy["monthly_detail_budget"],
                "deepRequestDelaySeconds": policy["deep_request_delay_seconds"],
                "pressureBackoffMinutes": policy["pressure_backoff_minutes"],
            },
            "state": {
                "lastQuickSyncAt": state["last_quick_sync_at"] if state else None,
                "lastDailyDeepSyncAt": state["last_daily_deep_sync_at"] if state else None,
                "lastWeeklyDeepSyncAt": state["last_weekly_deep_sync_at"] if state else None,
                "lastMonthlyDeepSyncAt": state["last_monthly_deep_sync_at"] if state else None,
                "backoffUntil": state["backoff_until"] if state else None,
                "runningLane": state["running_lane"] if state else None,
                "lastStatus": state["last_status"] if state else "idle",
                "lastSummary": summary,
            },
        }

    def _older_than(self, value: str | None, *, minutes: int = 0, hours: int = 0, days: int = 0) -> bool:
        parsed = parse_iso(value)
        if parsed is None:
            return True
        return parsed + timedelta(minutes=minutes, hours=hours, days=days) <= utc_now()
