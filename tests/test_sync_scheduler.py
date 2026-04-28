import unittest
from pathlib import Path

from storage.sync_scheduler_sqlite import SyncSchedulerStore


class SyncSchedulerTests(unittest.TestCase):
    def test_default_policy_exposes_quick_daily_weekly_monthly_lanes(self) -> None:
        db_path = Path("anti-regression/regression_artifacts/test_sync_scheduler.db")
        if db_path.exists():
            db_path.unlink()

        store = SyncSchedulerStore(db_path)
        store.ensure_default_sources()

        lanes = store.due_lanes("rocketmoney")
        lane_names = [lane["lane"] for lane in lanes]

        self.assertIn("quick", lane_names)
        self.assertIn("daily", lane_names)
        self.assertIn("weekly", lane_names)
        self.assertIn("monthly", lane_names)
        daily = next(lane for lane in lanes if lane["lane"] == "daily")
        self.assertEqual(daily["recentDays"], 90)
        self.assertEqual(daily["detailBudget"], 250)

        store.mark_started("rocketmoney", "quick")
        self.assertEqual(store.due_lanes("rocketmoney"), [])
        store.mark_finished("rocketmoney", "quick", "success", {"newTransactionCount": 3})

        snapshot = store.source_snapshot("rocketmoney")
        self.assertEqual(snapshot["state"]["lastStatus"], "success")
        self.assertEqual(snapshot["state"]["lastSummary"]["newTransactionCount"], 3)


if __name__ == "__main__":
    unittest.main()
