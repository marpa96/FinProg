from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finprog_engine import build_forecast, day_to_markdown, timeline_to_csv

EXAMPLES_DIR = ROOT / "examples"
INPUT_PATH = EXAMPLES_DIR / "simple_household.json"
OUTPUT_PATH = EXAMPLES_DIR / "simple_household_forecast.csv"
SAMPLE_DAY = "2026-04-18"
MARKDOWN_PATH = EXAMPLES_DIR / f"simple_household_day_{SAMPLE_DAY}.md"


def main() -> int:
    scenario = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    forecast = build_forecast(scenario["settings"], scenario["transactions"])
    csv = timeline_to_csv(forecast)
    sample_day = next((entry for entry in forecast["timeline"] if entry["date"] == SAMPLE_DAY), None)
    if sample_day is None:
        raise RuntimeError(f"Could not find sample day {SAMPLE_DAY} in forecast timeline.")
    markdown = day_to_markdown(forecast, sample_day)
    OUTPUT_PATH.write_text(csv, encoding="utf-8")
    MARKDOWN_PATH.write_text(markdown, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT).as_posix()}")
    print(f"Wrote {MARKDOWN_PATH.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
