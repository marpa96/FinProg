from __future__ import annotations

from copy import deepcopy
from typing import Any

from .date_utils import add_days, add_months_clamped, add_years_clamped, build_date, is_within_range, parse_iso_date, to_iso_date

AVERAGE_DAYS_PER_YEAR = 365.2425
TRANSACTION_TYPES = {"income", "expense", "savings"}
TRANSACTION_KINDS = {"recurring", "one_time"}
CASHFLOW_CLASSES = {"fixed", "variable"}
RECURRING_FREQUENCIES = {"weekly", "biweekly", "semimonthly", "monthly", "yearly"}


def clamp_amount(value: Any) -> float:
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return 0.0


def clamp_percent(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(100.0, number))


def sanitize_semimonthly_days(input_days: Any) -> list[int]:
    source = input_days if isinstance(input_days, list) else [1, 15]
    days = sorted(max(1, min(31, int(value or 1))) for value in source[:2])
    if not days:
        return [1, 15]
    if len(days) == 1:
        days.append(days[0])
    return days


def get_statement_bucket_for_transaction(transaction: dict[str, Any]) -> str:
    tx_type = transaction.get("type")
    cashflow_class = transaction.get("cashflowClass")
    if tx_type == "income":
        return "fixedIncome" if cashflow_class == "fixed" else "variableIncome"
    if tx_type == "expense":
        return "fixedExpenses" if cashflow_class == "fixed" else "variableExpenses"
    if tx_type == "savings":
        return "fixedSavings" if cashflow_class == "fixed" else "variableSavings"
    return "unknown"


def normalize_transaction(input_tx: dict[str, Any]) -> dict[str, Any]:
    transaction = deepcopy(input_tx)
    kind = "one_time" if transaction.get("kind") == "one_time" else "recurring"
    frequency = "" if kind == "one_time" else str(transaction.get("frequency") or "monthly")
    cashflow_class = transaction.get("cashflowClass") if transaction.get("cashflowClass") in CASHFLOW_CLASSES else "fixed"
    schedule = {"semimonthlyDays": sanitize_semimonthly_days(transaction.get("schedule", {}).get("semimonthlyDays"))} if frequency == "semimonthly" else {}
    return {
        **transaction,
        "name": str(transaction.get("name") or "").strip(),
        "type": str(transaction.get("type") or ""),
        "kind": kind,
        "cashflowClass": cashflow_class,
        "amount": clamp_amount(transaction.get("amount", 0)),
        "active": transaction.get("active") is not False,
        "frequency": frequency,
        "startDate": str(transaction.get("startDate") or ""),
        "endDate": str(transaction.get("endDate") or ""),
        "savingsRulePercent": clamp_percent(transaction.get("savingsRulePercent", 0)),
        "categoryId": str(transaction.get("categoryId") or ""),
        "subcategoryId": str(transaction.get("subcategoryId") or ""),
        "schedule": schedule,
    }


def get_cash_impact(transaction: dict[str, Any], amount: float) -> float:
    return -abs(amount) if transaction.get("type") in {"expense", "savings"} else abs(amount)


def get_savings_impact(transaction: dict[str, Any], amount: float) -> float:
    return abs(amount) if transaction.get("type") == "savings" else 0.0


def validate_settings(settings: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not settings.get("forecastStartDate") or not parse_iso_date(settings.get("forecastStartDate")):
        issues.append("Forecast start date is required.")
    try:
        float(settings.get("startingBalance"))
    except (TypeError, ValueError):
        issues.append("Starting balance must be a valid number.")
    try:
        float(settings.get("startingSavingsBalance", 0))
    except (TypeError, ValueError):
        issues.append("Starting savings balance must be a valid number.")
    try:
        forecast_days = int(settings.get("forecastDays", 0))
    except (TypeError, ValueError):
        forecast_days = 0
    if forecast_days < 1:
        issues.append("Forecast days must be a whole number greater than 0.")
    return issues


def validate_transaction(transaction_input: dict[str, Any]) -> list[str]:
    transaction = normalize_transaction(transaction_input)
    issues: list[str] = []
    if not transaction["name"]:
        issues.append("Name is required.")
    if transaction["type"] not in TRANSACTION_TYPES:
        issues.append("Type must be income, expense, or savings.")
    if transaction["kind"] not in TRANSACTION_KINDS:
        issues.append("Kind must be recurring or one_time.")
    if transaction["cashflowClass"] not in CASHFLOW_CLASSES:
        issues.append("Cashflow class must be fixed or variable.")
    if not transaction["startDate"] or not parse_iso_date(transaction["startDate"]):
        issues.append("Start date is required.")
    if transaction["amount"] < 0:
        issues.append("Amount must be zero or greater.")
    if transaction["endDate"]:
        start_date = parse_iso_date(transaction["startDate"])
        end_date = parse_iso_date(transaction["endDate"])
        if not end_date:
            issues.append("End date must be a valid date.")
        elif start_date and end_date < start_date:
            issues.append("End date cannot be earlier than start date.")
    if transaction["kind"] == "recurring" and transaction["frequency"] not in RECURRING_FREQUENCIES:
        issues.append("Recurring frequency is invalid.")
    if transaction["kind"] == "recurring" and transaction["frequency"] == "semimonthly" and len(transaction["schedule"].get("semimonthlyDays", [])) != 2:
        issues.append("Semimonthly transactions need two calendar days.")
    if transaction["type"] != "income" and transaction["savingsRulePercent"] > 0:
        issues.append("Savings rules can only be applied to income.")
    return issues


def is_transaction_usable(transaction: dict[str, Any]) -> bool:
    return not validate_transaction(transaction)


def get_daily_rate(transaction: dict[str, Any]) -> float:
    if transaction.get("kind") != "recurring" or not transaction.get("active"):
        return 0.0
    amount = get_cash_impact(transaction, transaction.get("amount", 0))
    frequency = transaction.get("frequency")
    if frequency == "weekly":
        return amount / 7
    if frequency == "biweekly":
        return amount / 14
    if frequency == "semimonthly":
        return (amount * 24) / AVERAGE_DAYS_PER_YEAR
    if frequency == "monthly":
        return (amount * 12) / AVERAGE_DAYS_PER_YEAR
    if frequency == "yearly":
        return amount / AVERAGE_DAYS_PER_YEAR
    return 0.0


def get_daily_savings_rate(transaction: dict[str, Any]) -> float:
    if transaction.get("kind") != "recurring" or not transaction.get("active") or transaction.get("type") != "savings":
        return 0.0
    amount = transaction.get("amount", 0)
    frequency = transaction.get("frequency")
    if frequency == "weekly":
        return amount / 7
    if frequency == "biweekly":
        return amount / 14
    if frequency == "semimonthly":
        return (amount * 24) / AVERAGE_DAYS_PER_YEAR
    if frequency == "monthly":
        return (amount * 12) / AVERAGE_DAYS_PER_YEAR
    if frequency == "yearly":
        return amount / AVERAGE_DAYS_PER_YEAR
    return 0.0


def is_transaction_active_on_date(transaction: dict[str, Any], target_date) -> bool:
    start_date = parse_iso_date(transaction.get("startDate"))
    end_date = parse_iso_date(transaction.get("endDate")) if transaction.get("endDate") else None
    return bool(start_date and target_date >= start_date and (not end_date or target_date <= end_date) and transaction.get("active") and is_transaction_usable(transaction))


def build_daily_allocation(transaction: dict[str, Any], occurrence_date: str) -> dict[str, Any]:
    cash_amount = get_daily_rate(transaction)
    savings_amount = get_daily_savings_rate(transaction)
    return {
        "id": f"{transaction['id']}:daily:{occurrence_date}",
        "transactionId": transaction["id"],
        "name": transaction["name"],
        "type": transaction["type"],
        "cashflowClass": transaction["cashflowClass"],
        "amount": cash_amount,
        "cashAmount": cash_amount,
        "savingsAmount": savings_amount,
        "date": occurrence_date,
        "source": transaction,
        "entryKind": "recurring_daily",
        "statementBucket": get_statement_bucket_for_transaction(transaction),
    }


def build_event(transaction: dict[str, Any], occurrence_date: str, amount: float | None = None, entry_kind: str | None = None) -> dict[str, Any]:
    event_amount = transaction["amount"] if amount is None else amount
    cash_amount = get_cash_impact(transaction, event_amount)
    savings_amount = get_savings_impact(transaction, event_amount)
    return {
        "id": f"{transaction['id']}:{occurrence_date}",
        "transactionId": transaction["id"],
        "name": transaction["name"],
        "type": transaction["type"],
        "cashflowClass": transaction["cashflowClass"],
        "amount": cash_amount,
        "cashAmount": cash_amount,
        "savingsAmount": savings_amount,
        "date": occurrence_date,
        "source": transaction,
        "entryKind": entry_kind or ("one_time" if transaction["kind"] == "one_time" else "scheduled_event"),
        "statementBucket": get_statement_bucket_for_transaction(transaction),
    }


def build_income_split_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    source = entry.get("source") or entry
    percent = clamp_percent(source.get("savingsRulePercent", 0))
    if source.get("type") != "income" or percent <= 0 or entry.get("cashAmount", 0) <= 0:
        return None
    split_amount = entry["cashAmount"] * (percent / 100)
    return {
        "id": f"{entry['id']}:split",
        "transactionId": source["id"],
        "name": f"{source['name']} Savings Split",
        "type": "savings",
        "cashflowClass": source["cashflowClass"],
        "amount": -split_amount,
        "cashAmount": -split_amount,
        "savingsAmount": split_amount,
        "date": entry["date"],
        "source": source,
        "entryKind": "income_split",
        "statementBucket": "incomeSplits",
    }


def get_entry_statement_bucket(entry: dict[str, Any]) -> str:
    return "incomeSplits" if entry.get("entryKind") == "income_split" else entry.get("statementBucket") or get_statement_bucket_for_transaction(entry.get("source", entry))


def build_statement_buckets(entries: list[dict[str, Any]]) -> dict[str, float]:
    buckets = {
        "fixedIncome": 0.0,
        "variableIncome": 0.0,
        "fixedExpenses": 0.0,
        "variableExpenses": 0.0,
        "fixedSavings": 0.0,
        "variableSavings": 0.0,
        "incomeSplits": 0.0,
    }
    for entry in entries:
        bucket = get_entry_statement_bucket(entry)
        if bucket in buckets:
            buckets[bucket] += abs(entry.get("savingsAmount") if bucket == "incomeSplits" else entry.get("amount", 0))
    return buckets


def generate_interval_events(transaction, range_start, range_end, days_per_interval):
    events = []
    cursor = parse_iso_date(transaction["startDate"])
    end_date = parse_iso_date(transaction["endDate"]) if transaction.get("endDate") else None
    while cursor < range_start:
        cursor = add_days(cursor, days_per_interval)
    while cursor <= range_end:
        if (not end_date or cursor <= end_date) and is_within_range(cursor, range_start, range_end):
            events.append(build_event(transaction, to_iso_date(cursor)))
        cursor = add_days(cursor, days_per_interval)
    return events


def generate_monthly_events(transaction, range_start, range_end, step_months):
    events = []
    cursor = parse_iso_date(transaction["startDate"])
    end_date = parse_iso_date(transaction["endDate"]) if transaction.get("endDate") else None
    while cursor < range_start:
        cursor = add_months_clamped(cursor, step_months)
    while cursor <= range_end:
        if (not end_date or cursor <= end_date) and is_within_range(cursor, range_start, range_end):
            events.append(build_event(transaction, to_iso_date(cursor)))
        cursor = add_months_clamped(cursor, step_months)
    return events


def generate_yearly_events(transaction, range_start, range_end):
    events = []
    cursor = parse_iso_date(transaction["startDate"])
    end_date = parse_iso_date(transaction["endDate"]) if transaction.get("endDate") else None
    while cursor < range_start:
        cursor = add_years_clamped(cursor, 1)
    while cursor <= range_end:
        if (not end_date or cursor <= end_date) and is_within_range(cursor, range_start, range_end):
            events.append(build_event(transaction, to_iso_date(cursor)))
        cursor = add_years_clamped(cursor, 1)
    return events


def generate_semimonthly_events(transaction, range_start, range_end):
    events = []
    start_date = parse_iso_date(transaction["startDate"])
    end_date = parse_iso_date(transaction["endDate"]) if transaction.get("endDate") else None
    day_one, day_two = sanitize_semimonthly_days(transaction.get("schedule", {}).get("semimonthlyDays"))
    seen_dates: set[str] = set()
    cursor_month = build_date(range_start.year, range_start.month, 1)
    first_month = build_date(start_date.year, start_date.month, 1)
    if cursor_month < first_month:
        cursor_month = first_month
    while cursor_month <= range_end:
        month_dates = [
            build_date(cursor_month.year, cursor_month.month, day_one),
            build_date(cursor_month.year, cursor_month.month, day_two),
        ]
        for month_date in month_dates:
            if month_date >= start_date and (not end_date or month_date <= end_date) and is_within_range(month_date, range_start, range_end):
                iso_date = to_iso_date(month_date)
                if iso_date not in seen_dates:
                    seen_dates.add(iso_date)
                    events.append(build_event(transaction, iso_date))
        cursor_month = add_months_clamped(cursor_month, 1)
    return sorted(events, key=lambda item: item["date"])


def generate_distributed_range_events(transaction, range_start, range_end):
    start_date = parse_iso_date(transaction["startDate"])
    end_date = parse_iso_date(transaction["endDate"])
    if not start_date or not end_date or end_date <= start_date:
        return [build_event(transaction, transaction["startDate"])] if is_within_range(start_date, range_start, range_end) else []

    total_days = (end_date - start_date).days + 1
    daily_amount = transaction["amount"] / total_days
    cursor = max(start_date, range_start)
    last_date = min(end_date, range_end)
    events = []
    while cursor <= last_date:
        events.append(build_event(transaction, to_iso_date(cursor), daily_amount, "distributed_range"))
        cursor = add_days(cursor, 1)
    return events


def generate_transaction_events(transaction_input: dict[str, Any], forecast_start_date: str, forecast_days: int) -> list[dict[str, Any]]:
    transaction = normalize_transaction(transaction_input)
    range_start = parse_iso_date(forecast_start_date)
    range_end = add_days(range_start, max(0, forecast_days - 1))
    if not transaction["active"] or not is_transaction_usable(transaction):
        return []
    if transaction["kind"] == "one_time":
        if transaction.get("endDate"):
            return generate_distributed_range_events(transaction, range_start, range_end)
        event_date = parse_iso_date(transaction["startDate"])
        return [build_event(transaction, transaction["startDate"])] if is_within_range(event_date, range_start, range_end) else []
    frequency = transaction["frequency"]
    if frequency == "weekly":
        return generate_interval_events(transaction, range_start, range_end, 7)
    if frequency == "biweekly":
        return generate_interval_events(transaction, range_start, range_end, 14)
    if frequency == "semimonthly":
        return generate_semimonthly_events(transaction, range_start, range_end)
    if frequency == "monthly":
        return generate_monthly_events(transaction, range_start, range_end, 1)
    if frequency == "yearly":
        return generate_yearly_events(transaction, range_start, range_end)
    return []


def describe_schedule(transaction: dict[str, Any]) -> str:
    if transaction.get("kind") == "one_time":
        if transaction.get("endDate"):
            return f"Distributed from {transaction.get('startDate')} to {transaction.get('endDate')}"
        return f"One-time on {transaction.get('startDate')}"
    if transaction.get("frequency") == "semimonthly":
        day_one, day_two = transaction.get("schedule", {}).get("semimonthlyDays", [1, 15])
        return f"Semimonthly on days {day_one} and {day_two}"
    return f"{transaction.get('frequency')} starting {transaction.get('startDate')}"


def get_next_occurrence(transaction: dict[str, Any], settings: dict[str, Any]) -> str | None:
    events = generate_transaction_events(transaction, settings["forecastStartDate"], int(settings["forecastDays"]))
    return events[0]["date"] if events else None


def build_forecast(settings: dict[str, Any], transaction_inputs: list[dict[str, Any]]) -> dict[str, Any]:
    forecast_days = max(1, int(settings.get("forecastDays", 90)))
    range_start = parse_iso_date(settings["forecastStartDate"])
    range_end = add_days(range_start, forecast_days - 1)
    starting_balance = float(settings.get("startingBalance", 0))
    starting_savings_balance = float(settings.get("startingSavingsBalance", 0))
    transactions = [normalize_transaction(item) for item in transaction_inputs]
    validation_issues = (
        [{"scope": "settings", "message": message} for message in validate_settings(settings)]
        + [
            {"scope": transaction.get("id") or transaction.get("name") or "transaction", "message": message}
            for transaction in transactions
            for message in validate_transaction(transaction)
        ]
    )
    events = sorted(
        [event for transaction in transactions for event in generate_transaction_events(transaction, settings["forecastStartDate"], forecast_days)],
        key=lambda item: (item["date"], item["name"]),
    )
    events_by_date: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        events_by_date.setdefault(event["date"], []).append(event)

    timeline = []
    running_balance = starting_balance
    running_savings_balance = starting_savings_balance
    transaction_summaries = []
    for transaction in transactions:
        transaction_summaries.append({
            "id": transaction["id"],
            "scheduleDescription": describe_schedule(transaction),
            "dailyRate": get_daily_rate(transaction),
            "dailySavingsRate": get_daily_savings_rate(transaction),
            "nextOccurrence": get_next_occurrence(transaction, settings),
            "normalizedTransaction": transaction,
        })

    for offset in range(forecast_days):
        date_obj = add_days(range_start, offset)
        date_iso = to_iso_date(date_obj)
        day_events = events_by_date.get(date_iso, [])
        recurring_allocations = [
            build_daily_allocation(transaction, date_iso)
            for transaction in transactions
            if transaction["kind"] == "recurring" and is_transaction_active_on_date(transaction, date_obj)
        ]
        one_time_entries = [event for event in day_events if event["entryKind"] in {"one_time", "distributed_range"}]
        base_entries = recurring_allocations + one_time_entries
        split_entries = [entry for entry in (build_income_split_entry(item) for item in base_entries) if entry]
        detail_entries = base_entries + split_entries
        statement = build_statement_buckets(detail_entries)
        inflow = sum(max(0.0, entry["cashAmount"]) for entry in detail_entries if get_entry_statement_bucket(entry) in {"fixedIncome", "variableIncome"})
        outflow = sum(abs(entry["cashAmount"]) for entry in detail_entries if entry["cashAmount"] < 0)
        net = sum(entry["cashAmount"] for entry in detail_entries)
        savings_net = sum(entry.get("savingsAmount", 0.0) for entry in detail_entries)
        recurring_inflow = sum(entry["cashAmount"] for entry in recurring_allocations if entry["cashAmount"] > 0)
        recurring_outflow = abs(sum(entry["cashAmount"] for entry in recurring_allocations if entry["cashAmount"] < 0))
        one_time_inflow = sum(entry["cashAmount"] for entry in one_time_entries if entry["cashAmount"] > 0)
        one_time_outflow = abs(sum(entry["cashAmount"] for entry in one_time_entries if entry["cashAmount"] < 0))
        running_balance += net
        running_savings_balance += savings_net
        timeline.append({
            "date": date_iso,
            "statement": statement,
            "recurringInflow": recurring_inflow,
            "recurringOutflow": recurring_outflow,
            "oneTimeInflow": one_time_inflow,
            "oneTimeOutflow": one_time_outflow,
            "inflow": inflow,
            "outflow": outflow,
            "net": net,
            "savingsNet": savings_net,
            "balance": running_balance,
            "savingsBalance": running_savings_balance,
            "events": one_time_entries,
            "recurringAllocations": recurring_allocations,
            "splitEntries": split_entries,
            "detailEntries": detail_entries,
        })

    projected_end_balance = timeline[-1]["balance"] if timeline else starting_balance
    projected_end_savings_balance = timeline[-1]["savingsBalance"] if timeline else starting_savings_balance
    statement_totals = {
        "fixedIncome": sum(day["statement"]["fixedIncome"] for day in timeline),
        "variableIncome": sum(day["statement"]["variableIncome"] for day in timeline),
        "fixedExpenses": sum(day["statement"]["fixedExpenses"] for day in timeline),
        "variableExpenses": sum(day["statement"]["variableExpenses"] for day in timeline),
        "fixedSavings": sum(day["statement"]["fixedSavings"] for day in timeline),
        "variableSavings": sum(day["statement"]["variableSavings"] for day in timeline),
        "incomeSplits": sum(day["statement"]["incomeSplits"] for day in timeline),
    }
    recurring_income_daily = sum(abs(get_daily_rate(transaction)) for transaction in transactions if transaction["kind"] == "recurring" and transaction["type"] == "income" and transaction["active"])
    recurring_expense_daily = sum(abs(get_daily_rate(transaction)) for transaction in transactions if transaction["kind"] == "recurring" and transaction["type"] == "expense" and transaction["active"])
    recurring_savings_daily = sum(abs(get_daily_savings_rate(transaction)) for transaction in transactions if transaction["kind"] == "recurring" and transaction["type"] == "savings" and transaction["active"])
    negative_balance_days = [day for day in timeline if day["balance"] < 0]
    return {
        "rangeStart": to_iso_date(range_start),
        "rangeEnd": to_iso_date(range_end),
        "startingBalance": starting_balance,
        "startingSavingsBalance": starting_savings_balance,
        "projectedEndBalance": projected_end_balance,
        "projectedEndSavingsBalance": projected_end_savings_balance,
        "recurringDailyNet": sum(get_daily_rate(transaction) for transaction in transactions),
        "lowestBalance": min([starting_balance] + [day["balance"] for day in timeline]),
        "validationIssues": validation_issues,
        "totals": {
            "recurringIncomeDaily": recurring_income_daily,
            "recurringExpenseDaily": recurring_expense_daily,
            "recurringSavingsDaily": recurring_savings_daily,
            "scheduledIncome": sum(max(0.0, event["cashAmount"]) for event in events if event["type"] == "income"),
            "scheduledExpenses": abs(sum(min(0.0, event["cashAmount"]) for event in events if event["type"] == "expense")),
            "scheduledSavings": sum(abs(event.get("savingsAmount", 0.0)) for event in events if event["type"] == "savings"),
            "scheduledNet": sum(max(0.0, event["cashAmount"]) for event in events if event["type"] == "income")
            - abs(sum(min(0.0, event["cashAmount"]) for event in events if event["type"] == "expense"))
            - sum(abs(event.get("savingsAmount", 0.0)) for event in events if event["type"] == "savings"),
            "statement": {
                **statement_totals,
                "net": statement_totals["fixedIncome"] + statement_totals["variableIncome"] - statement_totals["fixedExpenses"] - statement_totals["variableExpenses"] - statement_totals["fixedSavings"] - statement_totals["variableSavings"] - statement_totals["incomeSplits"],
            },
            "savingsNet": statement_totals["fixedSavings"] + statement_totals["variableSavings"] + statement_totals["incomeSplits"],
            "incomeSplitTotal": statement_totals["incomeSplits"],
        },
        "risk": {
            "negativeBalanceDayCount": len(negative_balance_days),
            "firstNegativeBalanceDate": negative_balance_days[0]["date"] if negative_balance_days else None,
        },
        "events": events,
        "upcomingEvents": events[:12],
        "timeline": timeline,
        "transactionSummaries": transaction_summaries,
    }
