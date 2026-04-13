from __future__ import annotations

from .engine import get_entry_statement_bucket


def escape_csv_cell(value):
    text = str(value or "")
    if any(char in text for char in [",", '"', "\n"]):
        return f'"{text.replace("\"", "\"\"")}"'
    return text


def format_signed_amount(value: float) -> str:
    return f"{'+' if value >= 0 else '-'}${abs(value):.2f}"


def format_amount(value: float) -> str:
    return f"${value:.2f}"


def format_entry_label(entry: dict) -> str:
    if entry.get("entryKind") == "one_time":
        return f"{entry['name']} (one-time)"
    if entry.get("entryKind") == "distributed_range":
        return f"{entry['name']} (distributed)"
    return entry["name"]


def filter_statement_entries(day: dict, bucket_key: str) -> list[dict]:
    if bucket_key == "incomeSplits":
        return [entry for entry in day["detailEntries"] if entry.get("entryKind") == "income_split"]
    return [entry for entry in day["detailEntries"] if get_entry_statement_bucket(entry) == bucket_key]


def format_entry_value(entry: dict) -> str:
    if entry.get("entryKind") == "income_split":
        return f"{entry.get('savingsAmount', 0):.2f}"
    if entry.get("type") == "savings":
        return f"{abs(entry.get('savingsAmount') or entry.get('amount', 0)):.2f}"
    return f"{entry.get('amount', 0):.2f}"


def format_entry_list(entries: list[dict]) -> str:
    return "; ".join(f"{format_entry_label(entry)}: {format_entry_value(entry)}" for entry in entries) if entries else ""


def timeline_to_csv(forecast: dict) -> str:
    rows = [[
        "date", "fixed_income", "variable_income", "fixed_expenses", "variable_expenses", "fixed_savings", "variable_savings", "income_splits",
        "total_inflow", "total_outflow", "net", "balance", "savings_balance",
        "fixed_income_details", "variable_income_details", "fixed_expense_details", "variable_expense_details",
        "fixed_savings_details", "variable_savings_details", "income_split_details",
    ]]
    for day in forecast["timeline"]:
        rows.append([
            day["date"],
            f"{day['statement']['fixedIncome']:.2f}",
            f"{day['statement']['variableIncome']:.2f}",
            f"{day['statement']['fixedExpenses']:.2f}",
            f"{day['statement']['variableExpenses']:.2f}",
            f"{day['statement']['fixedSavings']:.2f}",
            f"{day['statement']['variableSavings']:.2f}",
            f"{day['statement']['incomeSplits']:.2f}",
            f"{day['inflow']:.2f}",
            f"{day['outflow']:.2f}",
            f"{day['net']:.2f}",
            f"{day['balance']:.2f}",
            f"{day['savingsBalance']:.2f}",
            format_entry_list(filter_statement_entries(day, "fixedIncome")),
            format_entry_list(filter_statement_entries(day, "variableIncome")),
            format_entry_list(filter_statement_entries(day, "fixedExpenses")),
            format_entry_list(filter_statement_entries(day, "variableExpenses")),
            format_entry_list(filter_statement_entries(day, "fixedSavings")),
            format_entry_list(filter_statement_entries(day, "variableSavings")),
            format_entry_list(filter_statement_entries(day, "incomeSplits")),
        ])
    return "\n".join(",".join(escape_csv_cell(value) for value in row) for row in rows) + "\n"


def day_to_markdown(forecast: dict, day: dict) -> str:
    index = forecast["timeline"].index(day)
    previous_day = forecast["timeline"][index - 1] if index > 0 else None
    opening_balance = previous_day["balance"] if previous_day else forecast["startingBalance"]
    opening_savings_balance = previous_day["savingsBalance"] if previous_day else forecast["startingSavingsBalance"]

    def entry_lines(entries: list[dict], entry_type: str = "cash") -> str:
        if not entries:
            return "- None"
        lines = []
        for entry in entries:
            if entry_type == "savings":
                lines.append(f"- {format_entry_label(entry)}: +{format_amount(entry.get('savingsAmount') or abs(entry.get('amount', 0)))}")
            else:
                lines.append(f"- {format_entry_label(entry)}: {format_signed_amount(entry.get('amount', 0))}")
        return "\n".join(lines)

    return "\n".join([
        f"# Daily Breakdown: {day['date']}",
        "",
        "## Cashflow Statement",
        f"- Opening balance: {format_amount(opening_balance)}",
        f"- Opening savings balance: {format_amount(opening_savings_balance)}",
        f"- Fixed income: {format_amount(day['statement']['fixedIncome'])}",
        f"- Variable income: {format_amount(day['statement']['variableIncome'])}",
        f"- Fixed expenses: {format_amount(day['statement']['fixedExpenses'])}",
        f"- Variable expenses: {format_amount(day['statement']['variableExpenses'])}",
        f"- Fixed savings: {format_amount(day['statement']['fixedSavings'])}",
        f"- Variable savings: {format_amount(day['statement']['variableSavings'])}",
        f"- Income splits to savings: {format_amount(day['statement']['incomeSplits'])}",
        f"- Total inflow: {format_amount(day['inflow'])}",
        f"- Total outflow: {format_amount(day['outflow'])}",
        f"- Day Net: {format_signed_amount(day['net'])}",
        f"- Savings net for the day: {format_amount(day['savingsNet'])}",
        f"- Closing balance: {format_amount(day['balance'])}",
        f"- Closing savings balance: {format_amount(day['savingsBalance'])}",
        "",
        "## Fixed Income",
        entry_lines(filter_statement_entries(day, "fixedIncome")),
        "",
        "## Variable Income",
        entry_lines(filter_statement_entries(day, "variableIncome")),
        "",
        "## Fixed Expenses",
        entry_lines(filter_statement_entries(day, "fixedExpenses")),
        "",
        "## Variable Expenses",
        entry_lines(filter_statement_entries(day, "variableExpenses")),
        "",
        "## Fixed Savings",
        entry_lines(filter_statement_entries(day, "fixedSavings"), "savings"),
        "",
        "## Variable Savings",
        entry_lines(filter_statement_entries(day, "variableSavings"), "savings"),
        "",
        "## Income Splits",
        entry_lines(filter_statement_entries(day, "incomeSplits"), "savings"),
        "",
        "## Balance Flow",
        f"Previous day closing balance rolls into {day['date']}, then the day's net of {format_signed_amount(day['net'])} produces a closing balance of {format_amount(day['balance'])} while savings move by {format_amount(day['savingsNet'])} to {format_amount(day['savingsBalance'])}.",
        "",
    ])
