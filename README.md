# FinProg Cashflow Planner

This project is now a Vite + React cashflow studio built on top of a regression-tested Python forecast engine.

## Environment

Create and use the local virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

The financial calculation source of truth lives in Python, and the React app reads forecast data through the local Python API.

## Run

Start the app from the venv:

```powershell
python main.py
```

That starts the Python API plus the Vite app together.

Create a production build:

```powershell
npm run build
```

## Test

Run the logic suite:

```powershell
npm test
```

Generate the simple household sample JSON-to-CSV forecast:

```powershell
npm run export:sample
```

Run the anti-regression harness:

```powershell
npm run regression
```

## Current focus

- Pure forecast engine in [finprog_engine/engine.py](./finprog_engine/engine.py)
- Export helpers in [finprog_engine/forecast_io.py](./finprog_engine/forecast_io.py)
- Python API in [app.py](./app.py)
- React app shell in [src/App.jsx](./src/App.jsx)
- Input normalization and validation for settings and transactions
- Recurring schedule generation for weekly, biweekly, semimonthly, monthly, and yearly items
- Forecast summaries for scheduled totals, daily normalized cashflow, and negative-balance risk
- Sample scenario input in [examples/simple_household.json](./examples/simple_household.json)
- Day-by-day forecast export in [examples/simple_household_forecast.csv](./examples/simple_household_forecast.csv)
- A Vite React web UI for the statement, scenario editor, selected-day detail, and cashflow buckets
- Enforcement artifacts under [anti-regression](./anti-regression)
