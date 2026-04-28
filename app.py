from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from finprog_engine import build_forecast, day_to_markdown, timeline_to_csv
from storage import ConsolidatedFinanceStore, SyncSchedulerStore, sync_rocketmoney_to_consolidated
from storage.consolidated_finance_sqlite import DEFAULT_CONSOLIDATED_DATABASE


ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8001
SYNC_NEW_COUNT_PATTERN = re.compile(r"Hey! I found (\d+) new Rocket Money transaction")
SOURCE_ID_ROCKETMONEY = "rocketmoney"
ROCKETMONEY_DATABASE = ROOT / "data/private/rocketmoney.db"
CONSOLIDATED_DATABASE = ROOT / DEFAULT_CONSOLIDATED_DATABASE


class RocketMoneySyncJob:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.scheduler = SyncSchedulerStore()
        self.scheduler.ensure_default_sources()
        self.status = {
            "running": False,
            "status": "idle",
            "lane": None,
            "startedAt": None,
            "finishedAt": None,
            "exitCode": None,
            "newTransactionCount": None,
            "message": "Rocket Money quick sync has not run yet.",
            "log": [],
        }

    def snapshot(self) -> dict:
        with self._lock:
            return {
                **self.status,
                "schedule": self.scheduler.source_snapshot(SOURCE_ID_ROCKETMONEY),
                "log": list(self.status["log"]),
            }

    def start_quick_sync(self, reason: str) -> dict:
        return self.start_lane("quick", reason)

    def start_lane(self, lane: str, reason: str, lane_config: dict | None = None) -> dict:
        with self._lock:
            if self.status["running"]:
                return {
                    **self.status,
                    "log": list(self.status["log"]),
                    "accepted": False,
                    "message": "Rocket Money quick sync is already running.",
                }

            self.status.update({
                "running": True,
                "status": "running",
                "lane": lane,
                "startedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "finishedAt": None,
                "exitCode": None,
                "newTransactionCount": None,
                "message": f"Rocket Money {lane} sync started ({reason}).",
                "log": [],
            })

        self.scheduler.mark_started(SOURCE_ID_ROCKETMONEY, lane)
        thread = threading.Thread(target=self._run_sync_lane, args=(lane, lane_config or {}), daemon=True)
        thread.start()
        snapshot = self.snapshot()
        snapshot["accepted"] = True
        return snapshot

    def _append_log(self, line: str) -> None:
        with self._lock:
            log = [*self.status["log"], line][-80:]
            self.status["log"] = log
            match = SYNC_NEW_COUNT_PATTERN.search(line)
            if match:
                count = int(match.group(1))
                self.status["newTransactionCount"] = count
                self.status["message"] = f"Hey! I found {count} new Rocket Money transaction(s)."
            elif line:
                self.status["message"] = line

    def start_due_background_lane(self) -> dict | None:
        due_lanes = self.scheduler.due_lanes(SOURCE_ID_ROCKETMONEY)
        if not due_lanes:
            return None
        quick_lane = next((lane for lane in due_lanes if lane["lane"] == "quick"), None)
        lane = quick_lane or next((candidate for candidate in due_lanes if candidate["lane"] in {"daily", "weekly", "monthly"}), None)
        if not lane:
            return None
        return self.start_lane(lane["lane"], "schedule", lane)

    def _command_for_lane(self, lane: str, lane_config: dict) -> list[str]:
        command = [
            sys.executable,
            "scripts/sync_rocketmoney_database.py",
            "--no-refresh",
            "--transaction-mode",
            "quick",
        ]
        if lane == "quick":
            return [*command, "--detail-mode", "quick"]
        if lane == "daily":
            return [
                *command,
                "--detail-mode",
                "full",
                "--detail-recent-days",
                str(lane_config.get("recentDays", 90)),
                "--detail-limit",
                str(lane_config.get("detailBudget", 250)),
                "--detail-request-delay",
                str(lane_config.get("deepRequestDelaySeconds", 3.0)),
                "--detail-throttle-delay",
                str(float(lane_config.get("pressureBackoffMinutes", 60)) * 60),
            ]
        return [
            *command,
            "--detail-mode",
            "full",
            "--detail-limit",
            str(lane_config.get("detailBudget", 750 if lane == "weekly" else 1500)),
            "--detail-request-delay",
            str(lane_config.get("deepRequestDelaySeconds", 3.0)),
            "--detail-throttle-delay",
            str(float(lane_config.get("pressureBackoffMinutes", 60)) * 60),
        ]

    def _run_sync_lane(self, lane: str, lane_config: dict) -> None:
        command = self._command_for_lane(lane, lane_config)
        exit_code = None
        try:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            assert process.stdout is not None
            for line in process.stdout:
                self._append_log(line.rstrip())
            exit_code = process.wait()
            consolidated_summary = None
            if exit_code == 0 and ROCKETMONEY_DATABASE.exists():
                consolidated_summary = sync_rocketmoney_to_consolidated(ROCKETMONEY_DATABASE, CONSOLIDATED_DATABASE)
                self._append_log(
                    "Consolidated "
                    f"{consolidated_summary['sourceTransactionCount']} Rocket Money transaction(s)."
                )
            with self._lock:
                summary = {
                    "lane": lane,
                    "exitCode": exit_code,
                    "newTransactionCount": self.status["newTransactionCount"],
                    "message": self.status["message"],
                    "consolidated": consolidated_summary,
                }
                self.status.update({
                    "running": False,
                    "status": "success" if exit_code == 0 else "failed",
                    "lane": None,
                    "finishedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "exitCode": exit_code,
                })
                if exit_code == 0 and self.status["newTransactionCount"] is None:
                    self.status["newTransactionCount"] = 0
                    self.status["message"] = "Hey! I found 0 new Rocket Money transaction(s)."
                    summary["newTransactionCount"] = 0
                    summary["message"] = self.status["message"]
                elif exit_code != 0:
                    self.status["message"] = f"Rocket Money {lane} sync failed. Check the sync log."
                    summary["message"] = self.status["message"]
                self.scheduler.mark_finished(
                    SOURCE_ID_ROCKETMONEY,
                    lane,
                    "success" if exit_code == 0 else "failed",
                    summary,
                )
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self.status.update({
                    "running": False,
                    "status": "failed",
                    "lane": None,
                    "finishedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "exitCode": None,
                    "message": str(exc),
                })
                self.scheduler.mark_finished(
                    SOURCE_ID_ROCKETMONEY,
                    lane,
                    "failed",
                    {"lane": lane, "exitCode": exit_code, "message": str(exc)},
                )


class SyncSchedulerThread:
    def __init__(self, rocketmoney_job: RocketMoneySyncJob, interval_seconds: int = 300) -> None:
        self.rocketmoney_job = rocketmoney_job
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.rocketmoney_job.start_due_background_lane()


rocketmoney_sync_job = RocketMoneySyncJob()
sync_scheduler_thread = SyncSchedulerThread(rocketmoney_sync_job)


def consolidated_transactions_payload(
    limit: int = 200,
    source_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    offset: int = 0,
) -> dict:
    store = ConsolidatedFinanceStore(CONSOLIDATED_DATABASE)
    connection = store.connect()
    try:
        store.ensure_schema(connection)
        transactions = store.list_source_transactions(
            connection,
            limit=limit,
            source_id=source_id,
            start_date=start_date,
            end_date=end_date,
            offset=offset,
        )
        total = store.count_source_transactions(
            connection,
            source_id=source_id,
            start_date=start_date,
            end_date=end_date,
        )
        return {
            "databasePath": str(CONSOLIDATED_DATABASE),
            "transactions": transactions,
            "count": len(transactions),
            "total": total,
            "limit": limit,
            "offset": offset,
            "hasMore": offset + len(transactions) < total,
            "startDate": start_date,
            "endDate": end_date,
        }
    finally:
        connection.close()


def sync_rocketmoney_consolidated_payload() -> dict:
    if not ROCKETMONEY_DATABASE.exists():
        return {
            "ok": False,
            "error": f"Rocket Money database does not exist at {ROCKETMONEY_DATABASE}",
        }
    summary = sync_rocketmoney_to_consolidated(ROCKETMONEY_DATABASE, CONSOLIDATED_DATABASE)
    return {"ok": True, **summary}


class FinProgHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json({"ok": True})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send_json({"ok": True, "engine": "python"})
            return
        if parsed.path == "/api/rocketmoney/sync":
            self._send_json(rocketmoney_sync_job.snapshot())
            return
        if parsed.path == "/api/sync/sources":
            self._send_json({"sources": [rocketmoney_sync_job.scheduler.source_snapshot(SOURCE_ID_ROCKETMONEY)]})
            return
        if parsed.path == "/api/consolidated/transactions":
            query = parse_qs(parsed.query)
            limit = max(1, min(int(query.get("limit", ["100"])[0]), 500))
            offset = max(0, int(query.get("offset", ["0"])[0]))
            source_id = query.get("sourceId", [None])[0]
            start_date = query.get("startDate", [None])[0]
            end_date = query.get("endDate", [None])[0]
            self._send_json(consolidated_transactions_payload(
                limit=limit,
                source_id=source_id,
                start_date=start_date,
                end_date=end_date,
                offset=offset,
            ))
            return
        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/rocketmoney/sync":
            self._send_json(rocketmoney_sync_job.start_quick_sync("manual"))
            return
        if parsed.path == "/api/consolidated/sync/rocketmoney":
            payload = sync_rocketmoney_consolidated_payload()
            self._send_json(payload, HTTPStatus.OK if payload.get("ok") else HTTPStatus.BAD_REQUEST)
            return

        if parsed.path != "/api/forecast":
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            settings = payload.get("settings", {})
            transactions = payload.get("transactions", [])
            forecast = build_forecast(settings, transactions)
            csv = timeline_to_csv(forecast)
            markdown_by_date = {day["date"]: day_to_markdown(forecast, day) for day in forecast["timeline"]}
            self._send_json({
                "forecast": forecast,
                "csv": csv,
                "markdownByDate": markdown_by_date,
            })
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)


def serve(host: str = HOST, port: int = PORT) -> None:
    server = ThreadingHTTPServer((host, port), FinProgHandler)
    print(f"FinProg Python API running at http://{host}:{port}")
    if os.environ.get("FINPROG_SKIP_STARTUP_ROCKETMONEY_SYNC") != "1":
        rocketmoney_sync_job.start_quick_sync("startup")
        sync_scheduler_thread.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        sync_scheduler_thread.stop()
        server.server_close()


if __name__ == "__main__":
    serve()
