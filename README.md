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
- Extraction pipeline packages:
  - [extractors](./extractors): one module per source/type; pull raw information and preserve source context
  - [transformers](./transformers): one module per conversion; normalize extracted data into FinProg-useful structures, leaving unknown values as `None`
  - [exporters](./exporters): one module per target output; serialize normalized data without mutating app state
- Rocket Money transaction extraction:

```powershell
Copy .env.example to .env, fill ROCKETMONEY_USERNAME and ROCKETMONEY_PASSWORD, then run:
python scripts/extract_rocketmoney_transactions.py --output data/private/rocketmoney_transactions.json
```

The extractor follows Rocket Money's transaction cursor until `hasNextPage` is false. If `ROCKETMONEY_COOKIE` is missing or appears expired, it starts a fresh Rocket Money/Auth0 login flow, updates `ROCKETMONEY_COOKIE` in `.env`, and retries once. `data/private/` is ignored by git.
- Rocket Money session refresh:

```powershell
python scripts/refresh_rocketmoney_cookie.py --output data/private/rocketmoney_refreshed_cookies.txt
```

The refresh script reads `ROCKETMONEY_USERNAME` and `ROCKETMONEY_PASSWORD` from `.env`, visits `ROCKETMONEY_LOGIN_START_URL`, follows redirects to the current Auth0 form, posts the credentials, writes the new cookie header, and updates `.env`. MFA, CAPTCHA, or other anti-bot challenges still require a browser.
- Input normalization and validation for settings and transactions
- Recurring schedule generation for weekly, biweekly, semimonthly, monthly, and yearly items
- Forecast summaries for scheduled totals, daily normalized cashflow, and negative-balance risk
- Sample scenario input in [examples/simple_household.json](./examples/simple_household.json)
- Day-by-day forecast export in [examples/simple_household_forecast.csv](./examples/simple_household_forecast.csv)
- A Vite React web UI for the statement, scenario editor, selected-day detail, and cashflow buckets
- Enforcement artifacts under [anti-regression](./anti-regression)
