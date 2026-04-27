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
- Rocket Money local database sync:

```powershell
python scripts/sync_rocketmoney_database.py --database data/private/rocketmoney.db --snapshot-output data/private/rocketmoney_transactions.json
```

This is the main ingestion path for Rocket Money now. It fetches every available page, writes an optional raw JSON snapshot, and upserts the full source into one SQLite database with sync runs, page metadata, raw payload snapshots, normalized transaction/category/account/service/subscription tables, and per-transaction detail/history tables for split, related, rule, and chart data.
- Rocket Money session refresh:

```powershell
python scripts/refresh_rocketmoney_cookie.py --output data/private/rocketmoney_refreshed_cookies.txt
```

The refresh script reads `ROCKETMONEY_USERNAME` and `ROCKETMONEY_PASSWORD` from `.env`, visits `ROCKETMONEY_LOGIN_START_URL`, follows redirects to the current Auth0 form, posts the credentials, writes the new cookie header, and updates `.env`. MFA, CAPTCHA, or other anti-bot challenges still require a browser.

If you captured a browser login request, put its URL, cookie header, state, and anonymous ID into `ROCKETMONEY_AUTH_LOGIN_URL`, `ROCKETMONEY_AUTH_COOKIE`, `ROCKETMONEY_AUTH_STATE`, and `ROCKETMONEY_ULP_ANONYMOUS_ID`. The refresh script will use those values to replay the current Auth0 login shape more closely.

You can also paste browser-copied cURLs into `data/private/rocketmoney_login_curls.txt`, then import the useful values with:

```powershell
python scripts/import_rocketmoney_curls.py
```

If one of those cURLs is the successful `client-api.rocketmoney.com/graphql` request, the importer can fill `ROCKETMONEY_COOKIE` directly, which is the most reliable path.

The `RefreshAuthToken` GraphQL request proves the browser session is valid and gives the importer active cookie/client headers. For transaction extraction specifically, the best capture is the GraphQL request whose body has `operationName` set to `TransactionsPageTransactionTable`.

For the most automated auth path, use the browser-backed login helper:

```powershell
python main.py --rocketmoney-update
```

`main.py` installs Python dependencies from `requirements.txt`, installs the Playwright browser when needed, opens the browser login helper, then syncs Rocket Money into `data/private/rocketmoney.db` and writes a snapshot to `data/private/rocketmoney_transactions.json`. The browser helper uses a persistent profile under `data/private/`, so after the first successful login it can usually refresh cookies without pasting new cURLs. If Rocket Money shows MFA, CAPTCHA, or a risk challenge, complete it in the opened browser.

For a one-page smoke run:

```powershell
python main.py --rocketmoney-update --max-pages 1 --rocketmoney-output data/private/rocketmoney_transactions_test.json --rocketmoney-database data/private/rocketmoney_test.db
```
- Input normalization and validation for settings and transactions
- Recurring schedule generation for weekly, biweekly, semimonthly, monthly, and yearly items
- Forecast summaries for scheduled totals, daily normalized cashflow, and negative-balance risk
- Sample scenario input in [examples/simple_household.json](./examples/simple_household.json)
- Day-by-day forecast export in [examples/simple_household_forecast.csv](./examples/simple_household_forecast.csv)
- A Vite React web UI for the statement, scenario editor, selected-day detail, and cashflow buckets
- Enforcement artifacts under [anti-regression](./anti-regression)
