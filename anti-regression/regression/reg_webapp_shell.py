from __future__ import annotations

import subprocess
from pathlib import Path

from common import PROJECT_ROOT, display_path, print_failures, print_pass, print_prereq_fail, write_artifact


SCRIPT_NAME = "reg_webapp_shell"
LEDGER_IDS = ["WEB-001", "WEB-002", "WEB-003", "WEB-004", "WEB-005", "WEB-006", "WEB-007", "WEB-008", "WEB-009"]
EXPECTED = (
    "The project builds as a Vite React app, the main UI source contains the expected cashflow studio sections, "
    "the Python helper exposes the common setup workflows and starts the web app by default, and the React app uses the Python engine through an API."
)


def main() -> int:
    app_path = PROJECT_ROOT / "src" / "App.jsx"
    main_path = PROJECT_ROOT / "src" / "main.jsx"
    vite_config_path = PROJECT_ROOT / "vite.config.js"
    helper_path = PROJECT_ROOT / "main.py"
    api_path = PROJECT_ROOT / "app.py"
    python_engine_path = PROJECT_ROOT / "finprog_engine" / "engine.py"

    missing = [path for path in [app_path, main_path, vite_config_path, helper_path, api_path, python_engine_path] if not path.exists()]
    if missing:
      artifact = write_artifact(SCRIPT_NAME, "missing_webapp_files.txt", "\n".join(path.as_posix() for path in missing))
      return print_prereq_fail(
          SCRIPT_NAME,
          LEDGER_IDS,
          EXPECTED,
          f"Missing required webapp file(s): {[display_path(path) for path in missing]}",
          artifact,
      )

    node_script = """
import { build } from "vite";
import react from "@vitejs/plugin-react";

try {
  await build({
    configFile: false,
    plugins: [react()],
    build: {
      outDir: "anti-regression/regression_artifacts/vite-dist",
      emptyOutDir: true,
    },
  });
  console.log("vite-build-ok");
} catch (error) {
  console.error(error);
  process.exit(1);
}
"""
    build = subprocess.run(
        ["node", "--input-type=module", "-e", node_script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    build_artifact = write_artifact(
        SCRIPT_NAME,
        "vite_build.txt",
        f"STDOUT:\n{build.stdout}\n\nSTDERR:\n{build.stderr}\n\nCODE:{build.returncode}",
    )

    app_source = app_path.read_text(encoding="utf-8")
    helper_source = helper_path.read_text(encoding="utf-8")
    failures = []

    if build.returncode != 0:
        failures.append(
            {
                "ledger_id": "WEB-001",
                "expected": "The project completes a Vite production build.",
                "observed": f"`npm run build` exited with code {build.returncode}.",
                "artifact": display_path(build_artifact),
            }
        )

    required_markers = [
        "Current balance",
        "transaction-type-toggle",
        "Daily buckets",
        "handleSelectedDayChange",
        "Detailed forecast",
        "Day Net",
        "Settings",
        "Workspace settings",
        "Savings Balance",
        "Income Splits",
        "Savings",
    ]
    missing_markers = [marker for marker in required_markers if marker not in app_source]
    if missing_markers:
        source_artifact = write_artifact(SCRIPT_NAME, "app_source_snapshot.txt", app_source)
        failures.append(
            {
                "ledger_id": "WEB-002",
                "expected": "The React app exposes the simple home page, dedicated buckets page with unrestricted day selection, and planner view.",
                "observed": f"Missing UI markers: {missing_markers}.",
                "artifact": display_path(source_artifact),
            }
        )

    if "max={forecast.rangeEnd}" in app_source:
        source_artifact = write_artifact(SCRIPT_NAME, "bucket_day_picker_source_snapshot.txt", app_source)
        failures.append(
            {
                "ledger_id": "WEB-002",
                "expected": "The bucket day picker is not capped at the current forecast range end.",
                "observed": "The bucket date input is still capped by forecast.rangeEnd.",
                "artifact": display_path(source_artifact),
            }
        )

    helper_markers = ["--dev", "--build", "--test", "--regression", "--api", "npm", "install", "--open", "Starting the web app...", "app.py"]
    missing_helper_markers = [marker for marker in helper_markers if marker not in helper_source]
    if missing_helper_markers:
        helper_artifact = write_artifact(SCRIPT_NAME, "helper_source_snapshot.txt", helper_source)
        failures.append(
            {
                "ledger_id": "WEB-003",
                "expected": "The Python helper exposes install, dev, build, test, and regression flows for running from the venv and starts the app when run with no flags.",
                "observed": f"Missing helper markers: {missing_helper_markers}.",
                "artifact": display_path(helper_artifact),
            }
        )

    if (
        "home-balance-hero" not in app_source
        or "transaction-type-toggle" not in app_source
        or "expense-class-toggle" not in app_source
        or 'useState("variable")' not in app_source
        or 'useState("expense")' not in app_source
        or "Today ${todayExpenseClass" not in app_source
        or "Distribution start" not in app_source
        or "Distribution end" not in app_source
        or "rememberedExpenseSuggestions" not in app_source
        or "expense-suggestion-list" not in app_source
        or "todayFixedFrequency" not in app_source
        or "fixed-frequency-field" not in app_source
        or 'kind: todayExpenseClass === "fixed" ? "recurring" : "one_time"' not in app_source
        or "home-balance-hero" not in app_source
        or "handleEditTodayLine(entry)" not in app_source
        or "today-edit-modal" not in app_source
        or "handleSaveTodayEdit" not in app_source
        or "modal-backdrop" not in app_source
        or "buildDetailedRangeCsv" not in app_source
        or "Export CSV" not in app_source
        or "Import CSV" not in app_source
        or "export-csv-modal" not in app_source
        or "import-csv-modal" not in app_source
        or "extractTransactionsFromCsv" not in app_source
        or "extractTransactionsFromBudgetCsv" not in app_source
        or "transactionsToImportCsv" not in app_source
        or "Download Converted CSV" not in app_source
        or "importedCategory" not in app_source
        or "nullableCsvValue" not in app_source
        or "mergeImportedTransactions" not in app_source
        or "day_summary" not in app_source
        or "detail_line" not in app_source
        or "source_amount" not in app_source
        or "handleDeleteTransaction(entry.transactionId)" not in app_source
    ):
        source_artifact = write_artifact(SCRIPT_NAME, "current_day_source_snapshot.txt", app_source)
        failures.append(
            {
                "ledger_id": "WEB-004",
                "expected": "The app labels the daily net as Day Net, uses a large current forecast day balance for the current balance view, supports remembered fixed or variable quick-add for expenses, income, or savings with expense and variable selected by default, exports and imports full date-range CSV from popups, and lets today's lines be edited in a popup or deleted.",
                "observed": "The app source is missing the expected current-day balance, transaction-type toggle, expense-class toggle, default expense/variable state, remembered suggestions, fixed frequency controls, range fields, CSV export/import popups, popup edit/delete actions, or today's line markers.",
                "artifact": display_path(source_artifact),
            }
        )

    if 'dataset.theme' not in app_source or "themeMode" not in app_source or "auto by time of day" not in app_source:
        source_artifact = write_artifact(SCRIPT_NAME, "theme_source_snapshot.txt", app_source)
        failures.append(
            {
                "ledger_id": "WEB-005",
                "expected": "The app supports time-based dark mode by default and exposes theme control in settings.",
                "observed": "The app source is missing the expected dark-mode or theme-settings markers.",
                "artifact": display_path(source_artifact),
            }
        )

    category_markers = [
        "Expense Categories",
        "Income Categories",
        "Savings Categories",
        "Choose a setting on the left and configure it on the right.",
        "Add Category",
        "Add Subcategory",
        "Choose category",
        "Choose subcategory",
        "Default Savings %",
    ]
    missing_category_markers = [marker for marker in category_markers if marker not in app_source]
    if missing_category_markers:
        source_artifact = write_artifact(SCRIPT_NAME, "category_source_snapshot.txt", app_source)
        failures.append(
            {
                "ledger_id": "WEB-006",
                "expected": "The app has a settings page with editable categories, subcategories, icons, and category selection for today's variable expenses.",
                "observed": f"Missing category/settings markers: {missing_category_markers}.",
                "artifact": display_path(source_artifact),
            }
        )

    savings_markers = [
        "Starting Savings Balance",
        "Fixed Savings",
        "Variable Savings",
        "Income Splits",
        "Savings Rule %",
    ]
    missing_savings_markers = [marker for marker in savings_markers if marker not in app_source]
    if missing_savings_markers:
        source_artifact = write_artifact(SCRIPT_NAME, "savings_source_snapshot.txt", app_source)
        failures.append(
            {
                "ledger_id": "WEB-007",
                "expected": "The app shows a separate savings balance plus savings and income split buckets across the workflow.",
                "observed": f"Missing savings markers: {missing_savings_markers}.",
                "artifact": display_path(source_artifact),
            }
        )

    dedicated_savings_markers = [
        'setActivePage("savings")',
        "Savings snapshot",
        "Daily savings buckets for",
        "Savings balance",
    ]
    missing_dedicated_savings_markers = [marker for marker in dedicated_savings_markers if marker not in app_source]
    if missing_dedicated_savings_markers:
        source_artifact = write_artifact(SCRIPT_NAME, "dedicated_savings_source_snapshot.txt", app_source)
        failures.append(
            {
                "ledger_id": "WEB-008",
                "expected": "The app includes a dedicated Savings page whose header shows savings balance and whose content focuses on savings buckets and income splits.",
                "observed": f"Missing dedicated savings markers: {missing_dedicated_savings_markers}.",
                "artifact": display_path(source_artifact),
            }
        )

    vite_source = vite_config_path.read_text(encoding="utf-8")
    api_source = api_path.read_text(encoding="utf-8")
    if "/api/forecast" not in app_source or "/api/health" not in api_source or "build_forecast" not in api_source or "/api" not in vite_source:
        source_artifact = write_artifact(
            SCRIPT_NAME,
            "python_api_source_snapshot.txt",
            "\n\n=== App.jsx ===\n"
            + app_source
            + "\n\n=== app.py ===\n"
            + api_source
            + "\n\n=== vite.config.js ===\n"
            + vite_source,
        )
        failures.append(
            {
                "ledger_id": "WEB-009",
                "expected": "The Python engine is the source of truth and the React app fetches forecast data through the Python API.",
                "observed": "The app source, API server, or Vite proxy markers for the Python forecast flow were missing.",
                "artifact": display_path(source_artifact),
            }
        )

    source_transaction_markers = [
        "Source transactions",
        "fetchConsolidatedTransactions",
        "/api/consolidated/transactions",
        "/api/consolidated/sync/rocketmoney",
        "sourceTransactions",
        "sourceNote",
        "planningAmountCents",
        "sourceTransactionStartDate",
        "sourceTransactionEndDate",
        "sourceTransactionsMeta",
        "URLSearchParams",
        "startDate",
        "endDate",
        "offset",
        "transactionDetail",
        "sourceDetailDraft",
        "selectedSourceBatchIds",
        "Apply To Planner",
        "Similar loaded transactions",
        "clickable-transaction-card",
        "transaction-screen",
        "details-panel-premium",
        "Source Transaction",
        "today-edit-modal",
        "modal-backdrop",
        "Today",
        "This Month",
        "Last Month",
        "All History",
        "Load More",
    ]
    missing_source_transaction_markers = [
        marker for marker in source_transaction_markers
        if marker not in app_source and marker not in api_source
    ]
    if missing_source_transaction_markers:
        source_artifact = write_artifact(
            SCRIPT_NAME,
            "source_transaction_viewer_snapshot.txt",
            "\n\n=== App.jsx ===\n" + app_source + "\n\n=== app.py ===\n" + api_source,
        )
        failures.append(
            {
                "ledger_id": "WEB-009",
                "expected": "The web app loads consolidated Rocket Money source transactions through the Python API and displays names, dates, notes, amounts, date range browsing, month shortcuts, paginated loading, a Today shortcut, a detail modal, and planning metadata.",
                "observed": f"Missing consolidated transaction viewer markers: {missing_source_transaction_markers}.",
                "artifact": display_path(source_artifact),
            }
        )

    if failures:
        return print_failures(SCRIPT_NAME, LEDGER_IDS, EXPECTED, failures)

    return print_pass(
        SCRIPT_NAME,
        LEDGER_IDS,
        EXPECTED,
        "The Vite build passed and the React app contains the expected cashflow studio sections.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
    build_out_dir = PROJECT_ROOT / "anti-regression" / "regression_artifacts" / "vite-dist"
