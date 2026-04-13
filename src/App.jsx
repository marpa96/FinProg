import { useEffect, useMemo, useRef, useState } from "react";

import sampleScenario from "../examples/simple_household.json";
import { clearState, loadState, saveState } from "./storage.js";

const EMPTY_TRANSACTION = {
  id: "",
  name: "",
  type: "expense",
  kind: "recurring",
  cashflowClass: "fixed",
  amount: "",
  frequency: "monthly",
  startDate: "",
  endDate: "",
  active: true,
  categoryId: "",
  subcategoryId: "",
  schedule: {
    semimonthlyDays: [1, 15],
  },
};

const frequencyOptions = ["weekly", "biweekly", "semimonthly", "monthly", "yearly"];

function formatFrequencyOption(option) {
  return option.charAt(0).toUpperCase() + option.slice(1);
}

function createDefaultCategories() {
  return {
    expense: [
      {
        id: "exp-home",
        name: "Home",
        icon: "🏠",
        subcategories: [
          { id: "exp-home-rent", name: "Rent", icon: "🧾" },
          { id: "exp-home-utilities", name: "Utilities", icon: "💡" },
          { id: "exp-home-internet", name: "Internet", icon: "📶" },
        ],
      },
      {
        id: "exp-food",
        name: "Food",
        icon: "🍽️",
        subcategories: [
          { id: "exp-food-groceries", name: "Groceries", icon: "🛒" },
          { id: "exp-food-dining", name: "Dining Out", icon: "🍜" },
          { id: "exp-food-coffee", name: "Coffee", icon: "☕" },
        ],
      },
    ],
    income: [
      {
        id: "inc-work",
        name: "Work",
        icon: "💼",
        defaultSavingsRulePercent: 10,
        subcategories: [
          { id: "inc-work-paycheck", name: "Paycheck", icon: "💵", defaultSavingsRulePercent: 10 },
          { id: "inc-work-overtime", name: "Overtime", icon: "🕒", defaultSavingsRulePercent: 5 },
        ],
      },
      {
        id: "inc-other",
        name: "Other",
        icon: "✨",
        defaultSavingsRulePercent: null,
        subcategories: [
          { id: "inc-other-refund", name: "Refund", icon: "🔁", defaultSavingsRulePercent: null },
          { id: "inc-other-gift", name: "Gift", icon: "🎁", defaultSavingsRulePercent: null },
        ],
      },
    ],
    savings: [
      {
        id: "sav-emergency",
        name: "Emergency Fund",
        icon: "🛟",
        subcategories: [
          { id: "sav-emergency-core", name: "Core Reserve", icon: "🏦" },
          { id: "sav-emergency-buffer", name: "Buffer", icon: "🧱" },
        ],
      },
      {
        id: "sav-goals",
        name: "Goals",
        icon: "🎯",
        subcategories: [
          { id: "sav-goals-vacation", name: "Vacation", icon: "✈️" },
          { id: "sav-goals-project", name: "Project Fund", icon: "🛠️" },
        ],
      },
    ],
  };
}

function getTodayIso() {
  return new Date().toISOString().slice(0, 10);
}

function getInclusiveDayCount(startIso, endIso) {
  const start = new Date(`${startIso}T00:00:00Z`);
  const end = new Date(`${endIso}T00:00:00Z`);
  const dayMs = 24 * 60 * 60 * 1000;

  if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime())) {
    return 1;
  }

  return Math.max(1, Math.round((end - start) / dayMs) + 1);
}

function parseOptionalPercent(value) {
  if (value === "" || value === null || value === undefined) {
    return null;
  }

  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return null;
  }

  return Math.max(0, Math.min(100, numericValue));
}

function getAutoTheme() {
  const hour = new Date().getHours();
  return hour >= 19 || hour < 7 ? "dark" : "light";
}

function resolveTheme(themeMode) {
  return themeMode === "auto" ? getAutoTheme() : themeMode;
}

function normalizeCategoryCollection(collection, fallbackType) {
  if (!Array.isArray(collection)) {
    return [];
  }

  return collection.map((category, index) => ({
    id: category.id || `${fallbackType}-${index}`,
    name: category.name || `${fallbackType} category ${index + 1}`,
    icon: category.icon || (fallbackType === "expense" ? "📁" : fallbackType === "savings" ? "🪙" : "💼"),
    defaultSavingsRulePercent: fallbackType === "income" ? parseOptionalPercent(category.defaultSavingsRulePercent) : null,
    subcategories: Array.isArray(category.subcategories)
      ? category.subcategories.map((subcategory, subIndex) => ({
        id: subcategory.id || `${fallbackType}-${index}-${subIndex}`,
        name: subcategory.name || `Subcategory ${subIndex + 1}`,
        icon: subcategory.icon || "•",
        defaultSavingsRulePercent: fallbackType === "income" ? parseOptionalPercent(subcategory.defaultSavingsRulePercent) : null,
      }))
      : [],
  }));
}

function enrichStateShape(input) {
  const base = input?.transactions?.length ? input : structuredClone(sampleScenario);
  const defaults = createDefaultCategories();

  return {
    ...base,
    settings: {
      startingBalance: Number(base.settings?.startingBalance ?? 0),
      forecastStartDate: String(base.settings?.forecastStartDate ?? getTodayIso()),
      forecastDays: Number(base.settings?.forecastDays ?? 90),
      startingSavingsBalance: Number(base.settings?.startingSavingsBalance ?? 0),
      themeMode: base.settings?.themeMode ?? "auto",
      categories: {
        expense: normalizeCategoryCollection(base.settings?.categories?.expense ?? defaults.expense, "expense"),
        income: normalizeCategoryCollection(base.settings?.categories?.income ?? defaults.income, "income"),
        savings: normalizeCategoryCollection(base.settings?.categories?.savings ?? defaults.savings, "savings"),
      },
    },
    transactions: Array.isArray(base.transactions) ? base.transactions : [],
  };
}

function getDefaultState() {
  return enrichStateShape(loadState());
}

function getEmptyWorkspace() {
  const today = getTodayIso();
  return {
    settings: {
      startingBalance: 0,
      startingSavingsBalance: 0,
      forecastStartDate: today,
      forecastDays: 90,
      themeMode: "auto",
      categories: structuredClone(createDefaultCategories()),
    },
    transactions: [],
  };
}

function getCurrentTimelineDay(timeline, today) {
  if (!timeline.length) {
    return null;
  }

  const exact = timeline.find((entry) => entry.date === today);
  if (exact) {
    return exact;
  }

  const earlierDays = timeline.filter((entry) => entry.date < today);
  if (earlierDays.length) {
    return earlierDays.at(-1);
  }

  return timeline[0];
}

function getCategoryOptions(categories, type) {
  return categories?.[type] ?? [];
}

function getSubcategoryOptions(categories, type, categoryId) {
  const category = getCategoryOptions(categories, type).find((item) => item.id === categoryId);
  return category?.subcategories ?? [];
}

function getCategoryLabel(categories, type, categoryId, subcategoryId) {
  if (!categoryId) {
    return "Uncategorized";
  }

  const category = getCategoryOptions(categories, type).find((item) => item.id === categoryId);
  if (!category) {
    return "Uncategorized";
  }

  const base = `${category.icon} ${category.name}`;
  if (!subcategoryId) {
    return base;
  }

  const subcategory = category.subcategories.find((item) => item.id === subcategoryId);
  return subcategory ? `${base} / ${subcategory.icon} ${subcategory.name}` : base;
}

function getIncomeSavingsRuleDefaults(categories, categoryId, subcategoryId) {
  const category = getCategoryOptions(categories, "income").find((item) => item.id === categoryId);
  if (!category) {
    return null;
  }

  if (subcategoryId) {
    const subcategory = category.subcategories.find((item) => item.id === subcategoryId);
    if (subcategory && subcategory.defaultSavingsRulePercent !== null) {
      return subcategory.defaultSavingsRulePercent;
    }
  }

  return category.defaultSavingsRulePercent;
}

function getExpenseSuggestionScore(expenseName, query) {
  const normalizedName = expenseName.toLowerCase();
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) {
    return 0;
  }

  if (normalizedName === normalizedQuery) {
    return 100;
  }

  if (normalizedName.startsWith(normalizedQuery)) {
    return 80;
  }

  if (normalizedName.includes(normalizedQuery)) {
    return 60;
  }

  const queryParts = normalizedQuery.split(/\s+/).filter(Boolean);
  if (queryParts.every((part) => normalizedName.includes(part))) {
    return 40;
  }

  return 0;
}

function getTransactionTypeTitle(type) {
  if (type === "income") {
    return "Income";
  }
  if (type === "savings") {
    return "Savings";
  }
  return "Expense";
}

function getTransactionTypePlural(type) {
  if (type === "income") {
    return "income";
  }
  if (type === "savings") {
    return "savings";
  }
  return "expenses";
}

function createDraftFromTransaction(transaction) {
  return {
    ...EMPTY_TRANSACTION,
    ...transaction,
    amount: transaction.amount,
    categoryId: transaction.categoryId || "",
    subcategoryId: transaction.subcategoryId || "",
    schedule: {
      semimonthlyDays: transaction.schedule?.semimonthlyDays ?? [1, 15],
    },
  };
}

function buildDraftTransaction(draft) {
  return {
    ...draft,
    amount: Number(draft.amount || 0),
    savingsRulePercent: draft.type === "income" ? Number(draft.savingsRulePercent || 0) : 0,
    schedule: draft.kind === "recurring" && draft.frequency === "semimonthly"
      ? { semimonthlyDays: draft.schedule.semimonthlyDays.map(Number) }
      : {},
  };
}

function formatCurrency(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value || 0);
}

function formatSignedCurrency(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    signDisplay: "always",
    maximumFractionDigits: 2,
  }).format(value || 0);
}

function formatCurrencyCode(value) {
  return `$ ${new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value || 0)} USD`;
}

function escapeCsvCell(value) {
  const text = String(value ?? "");
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function formatCsvNumber(value) {
  return Number(value || 0).toFixed(2);
}

function getStatementBucketLabel(entry) {
  if (entry.entryKind === "income_split") {
    return "income_splits";
  }

  const bucket = entry.statementBucket || "";
  return bucket.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
}

function buildDetailedRangeCsv(forecast, categories, startDate, endDate) {
  const headers = [
    "date", "row_type", "statement_bucket", "name", "type", "cashflow_class", "kind", "entry_kind",
    "amount", "source_amount", "cash_amount", "savings_amount", "category", "subcategory", "category_id", "subcategory_id", "transaction_id",
    "frequency", "start_date", "end_date", "active", "savings_rule_percent", "semimonthly_days",
    "day_fixed_income", "day_variable_income", "day_fixed_expenses", "day_variable_expenses",
    "day_fixed_savings", "day_variable_savings", "day_income_splits",
    "day_total_inflow", "day_total_outflow", "day_net", "day_balance", "day_savings_balance",
  ];

  const rows = [headers];
  const days = forecast.timeline.filter((day) => day.date >= startDate && day.date <= endDate);

  for (const day of days) {
    const statementValues = [
      formatCsvNumber(day.statement.fixedIncome),
      formatCsvNumber(day.statement.variableIncome),
      formatCsvNumber(day.statement.fixedExpenses),
      formatCsvNumber(day.statement.variableExpenses),
      formatCsvNumber(day.statement.fixedSavings),
      formatCsvNumber(day.statement.variableSavings),
      formatCsvNumber(day.statement.incomeSplits),
      formatCsvNumber(day.inflow),
      formatCsvNumber(day.outflow),
      formatCsvNumber(day.net),
      formatCsvNumber(day.balance),
      formatCsvNumber(day.savingsBalance),
    ];

    rows.push([
      day.date, "day_summary", "", "Daily Summary", "", "", "", "",
      "", "", "", "", "", "", "", "", "", "", "", "", "", "", "",
      ...statementValues,
    ]);

    for (const entry of day.detailEntries) {
      const source = entry.source ?? {};
      const categoryLabel = getCategoryLabel(categories, entry.type, source.categoryId, source.subcategoryId);
      const [category = "", subcategory = ""] = categoryLabel.split(" / ");

      rows.push([
        day.date,
        "detail_line",
        getStatementBucketLabel(entry),
        entry.name,
        entry.type,
        entry.cashflowClass,
        source.kind ?? "",
        entry.entryKind,
        formatCsvNumber(entry.amount),
        formatCsvNumber(source.amount),
        formatCsvNumber(entry.cashAmount),
        formatCsvNumber(entry.savingsAmount),
        category,
        subcategory,
        source.categoryId ?? "",
        source.subcategoryId ?? "",
        entry.transactionId ?? source.id ?? "",
        source.frequency ?? "",
        source.startDate ?? "",
        source.endDate ?? "",
        source.active ?? "",
        source.savingsRulePercent ?? "",
        source.schedule?.semimonthlyDays?.join("|") ?? "",
        ...statementValues,
      ]);
    }
  }

  return rows.map((row) => row.map(escapeCsvCell).join(",")).join("\n") + "\n";
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let insideQuotes = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const nextChar = text[index + 1];

    if (char === '"' && insideQuotes && nextChar === '"') {
      cell += '"';
      index += 1;
    } else if (char === '"') {
      insideQuotes = !insideQuotes;
    } else if (char === "," && !insideQuotes) {
      row.push(cell);
      cell = "";
    } else if ((char === "\n" || char === "\r") && !insideQuotes) {
      if (char === "\r" && nextChar === "\n") {
        index += 1;
      }
      row.push(cell);
      if (row.some((value) => value !== "")) {
        rows.push(row);
      }
      row = [];
      cell = "";
    } else {
      cell += char;
    }
  }

  row.push(cell);
  if (row.some((value) => value !== "")) {
    rows.push(row);
  }

  return rows;
}

function normalizeHeader(value) {
  return value.trim().toLowerCase().replaceAll(" ", "_");
}

function csvRowsToObjects(text) {
  const [headerRow, ...dataRows] = parseCsv(text);
  if (!headerRow?.length) {
    return [];
  }

  const headers = headerRow.map(normalizeHeader);
  return dataRows.map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index] ?? ""])));
}

function parseCsvAmount(value) {
  const numeric = Number(String(value ?? "").replace(/[$,\s]/g, ""));
  return Number.isFinite(numeric) ? Math.abs(numeric) : 0;
}

function parseCsvBoolean(value) {
  const normalized = String(value ?? "").trim().toLowerCase();
  return !["false", "0", "no", "inactive"].includes(normalized);
}

function makeTransactionSignature(transaction) {
  return [
    String(transaction.name ?? "").trim().toLowerCase(),
    transaction.type,
    transaction.cashflowClass,
    transaction.kind,
    transaction.frequency,
    transaction.startDate,
    transaction.endDate,
  ].join("|");
}

function makeStableImportId(parts) {
  const source = parts.map((part) => String(part ?? "")).join("|");
  let hash = 0;
  for (let index = 0; index < source.length; index += 1) {
    hash = ((hash << 5) - hash + source.charCodeAt(index)) | 0;
  }
  return `import-${Math.abs(hash)}`;
}

function parseBudgetDate(value) {
  const text = String(value ?? "").trim();
  if (!text || text.toLowerCase() === "open end" || text.toLowerCase() === "null") {
    return null;
  }

  const parts = text.split("/");
  if (parts.length === 3) {
    const [month, day, year] = parts.map((part) => Number(part));
    if (Number.isFinite(month) && Number.isFinite(day) && Number.isFinite(year)) {
      return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    }
  }

  return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : null;
}

function mapBudgetRepeat(value) {
  const repeat = String(value ?? "").trim().toLowerCase();
  if (!repeat) {
    return { kind: "one_time", frequency: null, supported: true };
  }
  if (repeat === "weekly") {
    return { kind: "recurring", frequency: "weekly", supported: true };
  }
  if (repeat === "monthly") {
    return { kind: "recurring", frequency: "monthly", supported: true };
  }
  if (repeat === "yearly" || repeat === "annually" || repeat === "annual") {
    return { kind: "recurring", frequency: "yearly", supported: true };
  }
  if (repeat === "biweekly" || repeat === "every two weeks") {
    return { kind: "recurring", frequency: "biweekly", supported: true };
  }
  if (repeat === "semimonthly" || repeat === "twice monthly") {
    return { kind: "recurring", frequency: "semimonthly", supported: true };
  }
  return { kind: "recurring", frequency: null, supported: false };
}

function getBudgetType(category, amount) {
  const normalizedCategory = String(category ?? "").toLowerCase();
  if (normalizedCategory.includes("saving") && amount < 0) {
    return "savings";
  }
  return amount >= 0 ? "income" : "expense";
}

function transactionFromBudgetCsvRow(row, rowIndex) {
  const amount = Number(String(row.amount ?? "").replace(/[$,\s]/g, ""));
  const startDate = parseBudgetDate(row.start_date);
  if (!Number.isFinite(amount) || !startDate) {
    return null;
  }

  const repeat = mapBudgetRepeat(row.repeats);
  const type = getBudgetType(row.category, amount);

  return {
    id: makeStableImportId(["budget", rowIndex, row.category, row.memo, row.amount, row.repeats, row.start_date, row.end_date]),
    name: row.memo || null,
    type,
    kind: repeat.kind,
    cashflowClass: repeat.kind === "recurring" ? "fixed" : "variable",
    amount: Math.abs(amount),
    frequency: repeat.frequency,
    startDate,
    endDate: parseBudgetDate(row.end_date),
    active: repeat.supported,
    categoryId: null,
    subcategoryId: null,
    savingsRulePercent: null,
    schedule: null,
    importedCategory: row.category || null,
    importedRepeat: row.repeats || null,
  };
}

function isBudgetCsvFormat(rows) {
  const first = rows[0] ?? {};
  return "category" in first && "memo" in first && "amount" in first && "repeats" in first && "start_date" in first && "end_date" in first;
}

function extractTransactionsFromBudgetCsv(rows) {
  return rows
    .map((row, index) => transactionFromBudgetCsvRow(row, index))
    .filter(Boolean);
}

function nullableCsvValue(value) {
  return value === null || value === undefined || value === "" ? "null" : value;
}

function transactionsToImportCsv(transactions) {
  const headers = [
    "transaction_id", "name", "type", "kind", "cashflow_class", "amount", "frequency", "start_date", "end_date",
    "active", "category_id", "subcategory_id", "savings_rule_percent", "semimonthly_days", "imported_category", "imported_repeat",
  ];
  const rows = [headers];

  for (const transaction of transactions) {
    rows.push([
      transaction.id,
      transaction.name,
      transaction.type,
      transaction.kind,
      transaction.cashflowClass,
      transaction.amount,
      transaction.frequency,
      transaction.startDate,
      transaction.endDate,
      transaction.active,
      transaction.categoryId,
      transaction.subcategoryId,
      transaction.savingsRulePercent,
      transaction.schedule?.semimonthlyDays?.join("|") ?? null,
      transaction.importedCategory,
      transaction.importedRepeat,
    ]);
  }

  return rows.map((row) => row.map((value) => escapeCsvCell(nullableCsvValue(value))).join(",")).join("\n") + "\n";
}

function categoryNameFromLabel(label) {
  return String(label ?? "").replace(/[^\p{L}\p{N}\s&/-]/gu, "").trim().toLowerCase();
}

function findCategoryIdByName(categories, type, label) {
  const normalized = categoryNameFromLabel(label);
  const category = getCategoryOptions(categories, type).find((item) => categoryNameFromLabel(item.name) === normalized || categoryNameFromLabel(`${item.icon} ${item.name}`) === normalized);
  return category?.id ?? "";
}

function findSubcategoryIdByName(categories, type, categoryId, label) {
  const normalized = categoryNameFromLabel(label);
  const subcategory = getSubcategoryOptions(categories, type, categoryId).find((item) => categoryNameFromLabel(item.name) === normalized || categoryNameFromLabel(`${item.icon} ${item.name}`) === normalized);
  return subcategory?.id ?? "";
}

function transactionFromCsvRow(row, categories) {
  if (row.transaction_id && !row.row_type) {
    const semimonthlyDays = String(row.semimonthly_days || "")
      .split("|")
      .map((value) => Number(value))
      .filter((value) => Number.isFinite(value) && value >= 1 && value <= 31);

    return {
      id: row.transaction_id,
      name: row.name === "null" ? null : row.name,
      type: row.type === "null" ? null : row.type,
      kind: row.kind === "null" ? null : row.kind,
      cashflowClass: row.cashflow_class === "null" ? null : row.cashflow_class,
      amount: parseCsvAmount(row.amount),
      frequency: row.frequency === "null" ? null : row.frequency,
      startDate: row.start_date === "null" ? null : row.start_date,
      endDate: row.end_date === "null" ? null : row.end_date,
      active: parseCsvBoolean(row.active),
      categoryId: row.category_id === "null" ? null : row.category_id,
      subcategoryId: row.subcategory_id === "null" ? null : row.subcategory_id,
      savingsRulePercent: row.savings_rule_percent === "null" ? null : Number(row.savings_rule_percent || 0),
      schedule: semimonthlyDays.length === 2 ? { semimonthlyDays } : null,
      importedCategory: row.imported_category === "null" ? null : row.imported_category,
      importedRepeat: row.imported_repeat === "null" ? null : row.imported_repeat,
    };
  }

  if ((row.row_type || "").toLowerCase() !== "detail_line") {
    return null;
  }
  if ((row.entry_kind || "").toLowerCase() === "income_split") {
    return null;
  }

  const type = row.type || (row.statement_bucket?.includes("income") ? "income" : row.statement_bucket?.includes("savings") ? "savings" : "expense");
  if (!["income", "expense", "savings"].includes(type)) {
    return null;
  }

  const categoryId = row.category_id || findCategoryIdByName(categories, type, row.category);
  const subcategoryId = row.subcategory_id || findSubcategoryIdByName(categories, type, categoryId, row.subcategory);
  const semimonthlyDays = String(row.semimonthly_days || "")
    .split("|")
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value) && value >= 1 && value <= 31);

  return buildDraftTransaction({
    id: row.transaction_id || crypto.randomUUID(),
    name: row.name || "Imported transaction",
    type,
    kind: row.kind || "one_time",
    cashflowClass: row.cashflow_class || "variable",
    amount: parseCsvAmount(row.source_amount || row.amount),
    frequency: row.frequency || "monthly",
    startDate: row.start_date || row.date || getTodayIso(),
    endDate: row.end_date || "",
    active: parseCsvBoolean(row.active),
    categoryId,
    subcategoryId,
    savingsRulePercent: row.savings_rule_percent === "" ? 0 : Number(row.savings_rule_percent || 0),
    schedule: {
      semimonthlyDays: semimonthlyDays.length === 2 ? semimonthlyDays : [1, 15],
    },
  });
}

function extractTransactionsFromCsv(text, categories) {
  const rows = csvRowsToObjects(text);
  if (isBudgetCsvFormat(rows)) {
    return extractTransactionsFromBudgetCsv(rows);
  }

  const seen = new Set();
  const transactions = [];

  for (const row of rows) {
    const transaction = transactionFromCsvRow(row, categories);
    if (!transaction) {
      continue;
    }

    const key = transaction.id || makeTransactionSignature(transaction);
    if (seen.has(key)) {
      continue;
    }

    seen.add(key);
    transactions.push(transaction);
  }

  return transactions;
}

function getPageHeader(activePage, currentTimelineDay, selectedTimelineDay, forecast) {
  if (activePage === "buckets") {
    return {
      title: selectedTimelineDay?.date ?? forecast.rangeStart,
      subtitle: "Selected date",
      titleClassName: "page-hero",
    };
  }

  if (activePage === "planner") {
    return {
      title: "Detailed forecast",
      subtitle: `${forecast.rangeStart} to ${forecast.rangeEnd}`,
      titleClassName: "page-hero",
    };
  }

  if (activePage === "savings") {
    return {
      title: formatCurrencyCode(currentTimelineDay?.savingsBalance ?? forecast.startingSavingsBalance),
      subtitle: "Savings balance",
      titleClassName: "balance-hero",
    };
  }

  if (activePage === "settings") {
    return {
      title: "Settings",
      subtitle: "Workspace settings",
      titleClassName: "page-hero",
    };
  }

  return {
    title: formatCurrencyCode(currentTimelineDay?.balance ?? forecast.startingBalance),
    subtitle: "Current balance",
    titleClassName: "balance-hero home-balance-hero",
  };
}

function makeChartPath(points, width, height, padding) {
  if (!points.length) {
    return { line: "", area: "", min: 0, max: 0 };
  }

  const balances = points.map((point) => point.balance);
  const min = Math.min(...balances);
  const max = Math.max(...balances);
  const span = max - min || 1;
  const mapped = points.map((point, index) => {
    const x = padding + (index / Math.max(1, points.length - 1)) * (width - padding * 2);
    const y = height - padding - ((point.balance - min) / span) * (height - padding * 2);
    return { x, y };
  });

  return {
    min,
    max,
    line: mapped.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" "),
    area: [
      `M ${padding} ${height - padding}`,
      ...mapped.map((point) => `L ${point.x} ${point.y}`),
      `L ${width - padding} ${height - padding}`,
      "Z",
    ].join(" "),
  };
}

function getEmptyForecast(settings = {}) {
  return {
    rangeStart: settings.forecastStartDate ?? getTodayIso(),
    rangeEnd: settings.forecastStartDate ?? getTodayIso(),
    startingBalance: Number(settings.startingBalance ?? 0),
    startingSavingsBalance: Number(settings.startingSavingsBalance ?? 0),
    projectedEndBalance: Number(settings.startingBalance ?? 0),
    projectedEndSavingsBalance: Number(settings.startingSavingsBalance ?? 0),
    validationIssues: [],
    totals: {
      recurringIncomeDaily: 0,
      recurringExpenseDaily: 0,
      recurringSavingsDaily: 0,
      scheduledIncome: 0,
      scheduledExpenses: 0,
      scheduledSavings: 0,
      scheduledNet: 0,
      statement: {
        fixedIncome: 0,
        variableIncome: 0,
        fixedExpenses: 0,
        variableExpenses: 0,
        fixedSavings: 0,
        variableSavings: 0,
        incomeSplits: 0,
        net: 0,
      },
      savingsNet: 0,
      incomeSplitTotal: 0,
    },
    risk: {
      negativeBalanceDayCount: 0,
      firstNegativeBalanceDate: null,
    },
    events: [],
    upcomingEvents: [],
    timeline: [],
    transactionSummaries: [],
  };
}

async function fetchForecastPayload(state) {
  const response = await fetch("/api/forecast", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      settings: state.settings,
      transactions: state.transactions,
    }),
  });

  if (!response.ok) {
    throw new Error(`Forecast request failed with status ${response.status}`);
  }

  return response.json();
}

export default function App() {
  const today = getTodayIso();
  const [state, setState] = useState(getDefaultState);
  const [forecastData, setForecastData] = useState(() => ({ forecast: getEmptyForecast(getDefaultState().settings), csv: "", markdownByDate: {} }));
  const [forecastError, setForecastError] = useState("");
  const [activePage, setActivePage] = useState("home");
  const [settingsSection, setSettingsSection] = useState("categories");
  const [categoryType, setCategoryType] = useState("expense");
  const [draft, setDraft] = useState(() => ({
    ...EMPTY_TRANSACTION,
    startDate: sampleScenario.settings.forecastStartDate,
  }));
  const [selectedDay, setSelectedDay] = useState("");
  const [todayExpenseDraft, setTodayExpenseDraft] = useState({
    name: "",
    amount: "",
    startDate: today,
    endDate: "",
    categoryId: "",
    subcategoryId: "",
  });
  const [todayExpenseClass, setTodayExpenseClass] = useState("variable");
  const [todayTransactionType, setTodayTransactionType] = useState("expense");
  const [todayFixedFrequency, setTodayFixedFrequency] = useState("monthly");
  const [todayExpenseDistributed, setTodayExpenseDistributed] = useState(false);
  const [todayExpenseNameFocused, setTodayExpenseNameFocused] = useState(false);
  const [todayEditDraft, setTodayEditDraft] = useState(null);
  const [csvExportDraft, setCsvExportDraft] = useState(null);
  const [csvImportDraft, setCsvImportDraft] = useState(null);
  const todayStartDateRef = useRef(null);
  const todayEndDateRef = useRef(null);

  useEffect(() => {
    saveState(state);
  }, [state]);

  useEffect(() => {
    let cancelled = false;

    async function loadForecast() {
      try {
        const payload = await fetchForecastPayload(state);
        if (!cancelled) {
          setForecastData(payload);
          setForecastError("");
        }
      } catch (error) {
        if (!cancelled) {
          setForecastData({ forecast: getEmptyForecast(state.settings), csv: "", markdownByDate: {} });
          setForecastError(error instanceof Error ? error.message : "Could not load forecast from Python engine.");
        }
      }
    }

    loadForecast();

    return () => {
      cancelled = true;
    };
  }, [state]);

  const resolvedTheme = resolveTheme(state.settings.themeMode);

  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme;
  }, [resolvedTheme]);

  const forecast = forecastData.forecast;
  const chart = useMemo(() => makeChartPath(forecast.timeline, 840, 260, 22), [forecast.timeline]);
  const currentTimelineDay = useMemo(() => getCurrentTimelineDay(forecast.timeline, today), [forecast.timeline, today]);

  useEffect(() => {
    if (!forecast.timeline.length) {
      setSelectedDay("");
      return;
    }

    if (!selectedDay) {
      setSelectedDay(currentTimelineDay?.date ?? forecast.timeline[0]?.date ?? "");
      return;
    }

    const selectedDayIsInsideRange = selectedDay >= forecast.rangeStart && selectedDay <= forecast.rangeEnd;
    if (!forecast.timeline.some((entry) => entry.date === selectedDay) && selectedDayIsInsideRange) {
      setSelectedDay(currentTimelineDay?.date ?? forecast.timeline[0]?.date ?? "");
    }
  }, [currentTimelineDay, forecast.timeline, selectedDay]);

  const selectedTimelineDay = forecast.timeline.find((entry) => entry.date === selectedDay) ?? currentTimelineDay ?? forecast.timeline[0];
  const visibleSelectedDate = selectedDay || selectedTimelineDay?.date || forecast.rangeStart;
  const selectedMarkdown = selectedTimelineDay ? (forecastData.markdownByDate?.[selectedTimelineDay.date] ?? "") : "";
  const pageHeader = getPageHeader(activePage, currentTimelineDay, selectedTimelineDay, forecast);
  const transactionSummaryMap = useMemo(
    () => Object.fromEntries((forecast.transactionSummaries ?? []).map((summary) => [summary.id, summary])),
    [forecast.transactionSummaries],
  );
  const categoryOptions = getCategoryOptions(state.settings.categories, categoryType);
  const todayExpenseSubcategories = getSubcategoryOptions(state.settings.categories, todayTransactionType, todayExpenseDraft.categoryId);
  const draftSubcategories = getSubcategoryOptions(state.settings.categories, draft.type, draft.categoryId);
  const todayEditSubcategories = todayEditDraft ? getSubcategoryOptions(state.settings.categories, "expense", todayEditDraft.categoryId) : [];
  const rememberedExpenseSuggestions = useMemo(() => {
    const seenNames = new Set();
    return state.transactions
      .filter((transaction) => transaction.type === todayTransactionType && transaction.name)
      .slice()
      .reverse()
      .map((transaction) => ({
        transaction,
        score: getExpenseSuggestionScore(transaction.name, todayExpenseDraft.name),
      }))
      .filter(({ transaction, score }) => {
        const nameKey = transaction.name.trim().toLowerCase();
        if (!score || seenNames.has(nameKey)) {
          return false;
        }
        seenNames.add(nameKey);
        return true;
      })
      .sort((left, right) => right.score - left.score || left.transaction.name.localeCompare(right.transaction.name))
      .slice(0, 5)
      .map(({ transaction }) => transaction);
  }, [state.transactions, todayExpenseDraft.name, todayTransactionType]);

  const groupedTransactions = {
    fixedIncome: state.transactions.filter((item) => item.type === "income" && item.cashflowClass === "fixed"),
    variableIncome: state.transactions.filter((item) => item.type === "income" && item.cashflowClass === "variable"),
    fixedExpenses: state.transactions.filter((item) => item.type === "expense" && item.cashflowClass === "fixed"),
    variableExpenses: state.transactions.filter((item) => item.type === "expense" && item.cashflowClass === "variable"),
    fixedSavings: state.transactions.filter((item) => item.type === "savings" && item.cashflowClass === "fixed"),
    variableSavings: state.transactions.filter((item) => item.type === "savings" && item.cashflowClass === "variable"),
  };

  const selectedDayBuckets = {
    fixedIncome: (selectedTimelineDay?.detailEntries ?? []).filter((entry) => entry.type === "income" && entry.cashflowClass === "fixed"),
    variableIncome: (selectedTimelineDay?.detailEntries ?? []).filter((entry) => entry.type === "income" && entry.cashflowClass === "variable"),
    fixedExpenses: (selectedTimelineDay?.detailEntries ?? []).filter((entry) => entry.type === "expense" && entry.cashflowClass === "fixed"),
    variableExpenses: (selectedTimelineDay?.detailEntries ?? []).filter((entry) => entry.type === "expense" && entry.cashflowClass === "variable"),
    fixedSavings: (selectedTimelineDay?.detailEntries ?? []).filter((entry) => entry.type === "savings" && entry.cashflowClass === "fixed" && entry.entryKind !== "income_split"),
    variableSavings: (selectedTimelineDay?.detailEntries ?? []).filter((entry) => entry.type === "savings" && entry.cashflowClass === "variable" && entry.entryKind !== "income_split"),
    incomeSplits: (selectedTimelineDay?.detailEntries ?? []).filter((entry) => entry.entryKind === "income_split"),
  };

  function updateSettings(key, value) {
    setState((current) => ({
      ...current,
      settings: {
        ...current.settings,
        [key]: value,
      },
    }));
  }

  function updateCategories(updater) {
    setState((current) => ({
      ...current,
      settings: {
        ...current.settings,
        categories: updater(current.settings.categories),
      },
    }));
  }

  function addCategory(type) {
    updateCategories((currentCategories) => ({
      ...currentCategories,
      [type]: [
        ...getCategoryOptions(currentCategories, type),
        {
          id: `${type}-${crypto.randomUUID()}`,
          name: type === "expense" ? "New Expense Category" : type === "income" ? "New Income Category" : "New Savings Category",
          icon: type === "expense" ? "🧩" : type === "income" ? "✨" : "🪙",
          subcategories: [],
        },
      ],
    }));
  }

  function updateCategory(type, categoryId, key, value) {
    updateCategories((currentCategories) => ({
      ...currentCategories,
      [type]: getCategoryOptions(currentCategories, type).map((category) => (
        category.id === categoryId ? { ...category, [key]: key === "defaultSavingsRulePercent" ? parseOptionalPercent(value) : value } : category
      )),
    }));
  }

  function deleteCategory(type, categoryId) {
    updateCategories((currentCategories) => ({
      ...currentCategories,
      [type]: getCategoryOptions(currentCategories, type).filter((category) => category.id !== categoryId),
    }));
  }

  function addSubcategory(type, categoryId) {
    updateCategories((currentCategories) => ({
      ...currentCategories,
      [type]: getCategoryOptions(currentCategories, type).map((category) => (
        category.id === categoryId
          ? {
            ...category,
            subcategories: [
              ...category.subcategories,
              { id: `${type}-sub-${crypto.randomUUID()}`, name: "New Subcategory", icon: "•" },
            ],
          }
          : category
      )),
    }));
  }

  function updateSubcategory(type, categoryId, subcategoryId, key, value) {
    updateCategories((currentCategories) => ({
      ...currentCategories,
      [type]: getCategoryOptions(currentCategories, type).map((category) => (
        category.id === categoryId
          ? {
            ...category,
            subcategories: category.subcategories.map((subcategory) => (
              subcategory.id === subcategoryId ? { ...subcategory, [key]: key === "defaultSavingsRulePercent" ? parseOptionalPercent(value) : value } : subcategory
            )),
          }
          : category
      )),
    }));
  }

  function deleteSubcategory(type, categoryId, subcategoryId) {
    updateCategories((currentCategories) => ({
      ...currentCategories,
      [type]: getCategoryOptions(currentCategories, type).map((category) => (
        category.id === categoryId
          ? {
            ...category,
            subcategories: category.subcategories.filter((subcategory) => subcategory.id !== subcategoryId),
          }
          : category
      )),
    }));
  }

  function handleDraftChange(key, value) {
    setDraft((current) => {
      const next = {
        ...current,
        [key]: value,
      };

      if (key === "type" || key === "categoryId") {
        next.subcategoryId = "";
      }
      if (key === "type") {
        next.categoryId = "";
        next.savingsRulePercent = key === "type" && value === "income" ? next.savingsRulePercent || 0 : 0;
      }

      if (next.type === "income" && key === "categoryId") {
        const inheritedPercent = getIncomeSavingsRuleDefaults(state.settings.categories, value, "");
        next.savingsRulePercent = inheritedPercent ?? "";
      }

      if (next.type === "income" && key === "subcategoryId") {
        const inheritedPercent = getIncomeSavingsRuleDefaults(state.settings.categories, next.categoryId, value);
        next.savingsRulePercent = inheritedPercent ?? "";
      }

      return next;
    });
  }

  function handleSemimonthlyDayChange(index, value) {
    setDraft((current) => {
      const days = [...(current.schedule?.semimonthlyDays ?? [1, 15])];
      days[index] = Number(value);
      return {
        ...current,
        schedule: {
          semimonthlyDays: days,
        },
      };
    });
  }

  function handleTodayEditChange(key, value) {
    setTodayEditDraft((current) => {
      if (!current) {
        return current;
      }

      const next = {
        ...current,
        [key]: value,
      };

      if (key === "categoryId") {
        next.subcategoryId = "";
      }

      return next;
    });
  }

  function handleTodayEditSemimonthlyDayChange(index, value) {
    setTodayEditDraft((current) => {
      if (!current) {
        return current;
      }

      const days = [...(current.schedule?.semimonthlyDays ?? [1, 15])];
      days[index] = Number(value);
      return {
        ...current,
        schedule: {
          semimonthlyDays: days,
        },
      };
    });
  }

  function resetDraft(startDate = state.settings.forecastStartDate) {
    setDraft({
      ...EMPTY_TRANSACTION,
      startDate,
    });
  }

  function handleSaveTransaction(event) {
    event.preventDefault();
    const transaction = buildDraftTransaction({
      ...draft,
      id: draft.id || crypto.randomUUID(),
    });

    setState((current) => {
      const index = current.transactions.findIndex((entry) => entry.id === transaction.id);
      const transactions = [...current.transactions];
      if (index >= 0) {
        transactions[index] = transaction;
      } else {
        transactions.push(transaction);
      }
      return { ...current, transactions };
    });

    resetDraft();
  }

  function handleAddTodayExpense(event) {
    event.preventDefault();
    const amount = Number(todayExpenseDraft.amount || 0);
    if (!amount) {
      return;
    }
    const startDate = todayExpenseDistributed ? todayExpenseDraft.startDate || today : today;
    const endDate = todayExpenseDistributed && todayExpenseDraft.endDate && todayExpenseDraft.endDate >= startDate ? todayExpenseDraft.endDate : "";

    const transaction = buildDraftTransaction({
      id: crypto.randomUUID(),
      name: todayExpenseDraft.name.trim() || `Today ${todayExpenseClass === "fixed" ? "Fixed" : "Variable"} ${getTransactionTypeTitle(todayTransactionType)}`,
      type: todayTransactionType,
      kind: todayExpenseClass === "fixed" ? "recurring" : "one_time",
      cashflowClass: todayExpenseClass,
      amount,
      frequency: todayExpenseClass === "fixed" ? todayFixedFrequency : "",
      startDate,
      endDate,
      schedule: {},
      active: true,
      categoryId: todayExpenseDraft.categoryId,
      subcategoryId: todayExpenseDraft.subcategoryId,
    });

    setState((current) => ({
      ...current,
      transactions: [...current.transactions, transaction],
    }));

    setTodayExpenseDraft({
      name: "",
      amount: "",
      startDate: today,
      endDate: "",
      categoryId: "",
      subcategoryId: "",
    });
    setTodayExpenseDistributed(false);
  }

  function selectRememberedExpense(transaction) {
    setTodayExpenseDraft((current) => ({
      ...current,
      name: transaction.name,
      categoryId: transaction.categoryId || "",
      subcategoryId: transaction.subcategoryId || "",
    }));
    setTodayTransactionType(transaction.type === "income" || transaction.type === "savings" ? transaction.type : "expense");
    setTodayExpenseClass(transaction.cashflowClass === "fixed" ? "fixed" : "variable");
    if (transaction.cashflowClass === "fixed" && transaction.frequency) {
      setTodayFixedFrequency(transaction.frequency);
    }
    setTodayExpenseNameFocused(false);
  }

  function toggleTodayExpenseDistribution() {
    setTodayExpenseDistributed((current) => {
      const next = !current;
      setTodayExpenseDraft((draftCurrent) => ({
        ...draftCurrent,
        startDate: draftCurrent.startDate || today,
        endDate: next ? draftCurrent.endDate : "",
      }));
      return next;
    });
  }

  function openDatePicker(inputRef) {
    const input = inputRef.current;
    if (!input) {
      return;
    }
    if (typeof input.showPicker === "function") {
      input.showPicker();
    } else {
      input.focus();
    }
  }

  function handleSelectedDayChange(date) {
    if (!date) {
      return;
    }

    setSelectedDay(date);

    setState((current) => {
      const rangeStart = forecast.rangeStart || current.settings.forecastStartDate || date;
      const rangeEnd = forecast.rangeEnd || rangeStart;

      if (date < rangeStart) {
        return {
          ...current,
          settings: {
            ...current.settings,
            forecastStartDate: date,
            forecastDays: getInclusiveDayCount(date, rangeEnd),
          },
        };
      }

      if (date > rangeEnd) {
        return {
          ...current,
          settings: {
            ...current.settings,
            forecastDays: getInclusiveDayCount(rangeStart, date),
          },
        };
      }

      return current;
    });
  }

  function expandForecastRangeForDates(startDate, endDate) {
    if (!startDate || !endDate) {
      return;
    }

    setState((current) => {
      const rangeStart = forecast.rangeStart || current.settings.forecastStartDate || startDate;
      const rangeEnd = forecast.rangeEnd || rangeStart;
      const nextStart = startDate < rangeStart ? startDate : rangeStart;
      const nextEnd = endDate > rangeEnd ? endDate : rangeEnd;

      if (nextStart === rangeStart && nextEnd === rangeEnd) {
        return current;
      }

      return {
        ...current,
        settings: {
          ...current.settings,
          forecastStartDate: nextStart,
          forecastDays: getInclusiveDayCount(nextStart, nextEnd),
        },
      };
    });
  }

  function openCsvExportModal() {
    const startDate = currentTimelineDay?.date ?? forecast.rangeStart;
    const endDate = forecast.rangeEnd;
    setCsvExportDraft({ startDate, endDate });
    expandForecastRangeForDates(startDate, endDate);
  }

  function handleCsvExportDateChange(key, value) {
    const next = {
      ...(csvExportDraft ?? { startDate: currentTimelineDay?.date ?? forecast.rangeStart, endDate: forecast.rangeEnd }),
      [key]: value,
    };

    if (next.startDate && next.endDate && next.endDate < next.startDate) {
      next.endDate = next.startDate;
    }

    setCsvExportDraft(next);
    expandForecastRangeForDates(next.startDate, next.endDate);
  }

  function downloadCsv(csv, startDate, endDate) {
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `finprog_full_export_${startDate}_to_${endDate}.csv`;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function getDetailedCsvForRange(startDate, endDate) {
    return buildDetailedRangeCsv(forecast, state.settings.categories, startDate, endDate);
  }

  function handleCsvExport(event) {
    event.preventDefault();
    if (!csvExportDraft?.startDate || !csvExportDraft?.endDate) {
      return;
    }

    const csv = getDetailedCsvForRange(csvExportDraft.startDate, csvExportDraft.endDate);
    downloadCsv(csv, csvExportDraft.startDate, csvExportDraft.endDate);
    setCsvExportDraft(null);
  }

  function openCsvImportModal() {
    setCsvImportDraft({
      text: "",
      fileName: "",
      message: "",
    });
  }

  function handleCsvImportText(text, fileName = "") {
    setCsvImportDraft((current) => ({
      ...(current ?? { text: "", fileName: "", message: "" }),
      text,
      fileName,
      message: "",
    }));
  }

  function handleCsvImportFile(file) {
    if (!file) {
      return;
    }

    const reader = new FileReader();
    reader.onload = () => handleCsvImportText(String(reader.result ?? ""), file.name);
    reader.readAsText(file);
  }

  function mergeImportedTransactions(importedTransactions) {
    let added = 0;
    let updated = 0;
    let skipped = 0;
    const transactions = [...state.transactions];
    const indexById = new Map(transactions.map((transaction, index) => [transaction.id, index]));
    const indexBySignature = new Map(transactions.map((transaction, index) => [makeTransactionSignature(transaction), index]));

    for (const transaction of importedTransactions) {
      const signature = makeTransactionSignature(transaction);
      const existingIndex = indexById.has(transaction.id) ? indexById.get(transaction.id) : indexBySignature.get(signature);

      if (existingIndex === undefined) {
        transactions.push(transaction);
        indexById.set(transaction.id, transactions.length - 1);
        indexBySignature.set(signature, transactions.length - 1);
        added += 1;
      } else if (JSON.stringify(transactions[existingIndex]) !== JSON.stringify(transaction)) {
        transactions[existingIndex] = {
          ...transactions[existingIndex],
          ...transaction,
          id: transactions[existingIndex].id,
        };
        updated += 1;
      } else {
        skipped += 1;
      }
    }

    setState((current) => ({ ...current, transactions }));

    return { added, updated, skipped };
  }

  function handleCsvImport(event) {
    event.preventDefault();
    const text = csvImportDraft?.text?.trim() ?? "";
    if (!text) {
      setCsvImportDraft((current) => ({ ...(current ?? { text: "", fileName: "", message: "" }), message: "Choose or paste a CSV first." }));
      return;
    }

    try {
      const importedTransactions = extractTransactionsFromCsv(text, state.settings.categories);
      if (!importedTransactions.length) {
        setCsvImportDraft((current) => ({ ...(current ?? { text: "", fileName: "", message: "" }), message: "No transaction detail lines were found in that CSV." }));
        return;
      }

      const result = mergeImportedTransactions(importedTransactions);
      setCsvImportDraft((current) => ({
        ...(current ?? { text: "", fileName: "", message: "" }),
        message: `Merged ${importedTransactions.length} transactions: ${result.added} added, ${result.updated} updated, ${result.skipped} unchanged.`,
      }));
    } catch (error) {
      setCsvImportDraft((current) => ({
        ...(current ?? { text: "", fileName: "", message: "" }),
        message: error instanceof Error ? error.message : "Could not import that CSV.",
      }));
    }
  }

  function handleCsvConvertDownload() {
    const text = csvImportDraft?.text?.trim() ?? "";
    if (!text) {
      setCsvImportDraft((current) => ({ ...(current ?? { text: "", fileName: "", message: "" }), message: "Choose or paste a CSV first." }));
      return;
    }

    const rows = csvRowsToObjects(text);
    if (!isBudgetCsvFormat(rows)) {
      setCsvImportDraft((current) => ({ ...(current ?? { text: "", fileName: "", message: "" }), message: "That CSV is already in a FinProg-style format or uses unknown headers." }));
      return;
    }

    const convertedTransactions = extractTransactionsFromBudgetCsv(rows);
    const csv = transactionsToImportCsv(convertedTransactions);
    downloadCsv(csv, "converted", "budget");
    setCsvImportDraft((current) => ({
      ...(current ?? { text: "", fileName: "", message: "" }),
      message: `Converted ${convertedTransactions.length} rows into FinProg import CSV format.`,
    }));
  }

  function handleEditTransaction(transaction) {
    setDraft(createDraftFromTransaction(transaction));
  }

  function handleEditTodayLine(entry) {
    const transaction = state.transactions.find((item) => item.id === entry.transactionId);
    if (!transaction) {
      return;
    }

    setTodayEditDraft(createDraftFromTransaction(transaction));
  }

  function handleSaveTodayEdit(event) {
    event.preventDefault();
    if (!todayEditDraft) {
      return;
    }

    const transaction = buildDraftTransaction({
      ...todayEditDraft,
    });

    setState((current) => ({
      ...current,
      transactions: current.transactions.map((item) => (item.id === transaction.id ? transaction : item)),
    }));
    setTodayEditDraft(null);
  }

  function handleDeleteTransaction(id) {
    setState((current) => ({
      ...current,
      transactions: current.transactions.filter((entry) => entry.id !== id),
    }));

    if (draft.id === id) {
      resetDraft();
    }
  }

  function loadSample() {
    setState(enrichStateShape(sampleScenario));
    resetDraft(sampleScenario.settings.forecastStartDate);
  }

  function resetWorkspace() {
    clearState();
    const empty = getEmptyWorkspace();
    setState(empty);
    resetDraft(empty.settings.forecastStartDate);
  }

  const todayExpenseEntries = (currentTimelineDay?.detailEntries ?? []).filter(
    (entry) => entry.type === todayTransactionType && entry.cashflowClass === todayExpenseClass && entry.entryKind !== "income_split",
  );
  const todayExpenseClassLabel = todayExpenseClass === "fixed" ? "fixed" : "variable";
  const todayExpenseClassTitle = todayExpenseClass === "fixed" ? "Fixed" : "Variable";
  const todayTransactionTypeTitle = getTransactionTypeTitle(todayTransactionType);
  const todayTransactionTypePlural = getTransactionTypePlural(todayTransactionType);
  const csvExportRangeReady = csvExportDraft
    ? csvExportDraft.startDate >= forecast.rangeStart && csvExportDraft.endDate <= forecast.rangeEnd
    : true;
  const csvExportDayCount = csvExportDraft
    ? forecast.timeline.filter((day) => day.date >= csvExportDraft.startDate && day.date <= csvExportDraft.endDate).length
    : 0;

  return (
    <div className="studio-shell">
      <div className="ambient ambient-left" />
      <div className="ambient ambient-right" />

      <header className="simple-topbar">
        <div>
          <div className="eyebrow">FinProg</div>
          <h1 className={pageHeader.titleClassName}>{pageHeader.title}</h1>
          <p>{pageHeader.subtitle}</p>
        </div>
        <div className="topbar-actions">
          <nav className="page-nav" aria-label="Pages">
            <button className={activePage === "home" ? "nav-pill is-active" : "nav-pill"} onClick={() => setActivePage("home")} type="button">Home</button>
            <button className={activePage === "buckets" ? "nav-pill is-active" : "nav-pill"} onClick={() => setActivePage("buckets")} type="button">Buckets</button>
            <button className={activePage === "savings" ? "nav-pill is-active" : "nav-pill"} onClick={() => setActivePage("savings")} type="button">Savings</button>
            <button className={activePage === "planner" ? "nav-pill is-active" : "nav-pill"} onClick={() => setActivePage("planner")} type="button">Planner</button>
            <button className={activePage === "settings" ? "nav-pill is-active" : "nav-pill"} onClick={() => setActivePage("settings")} type="button">Settings</button>
          </nav>
          <div className="hero-actions">
            <button onClick={loadSample} type="button">Load Sample</button>
            <button className="ghost" onClick={resetWorkspace} type="button">Reset Workspace</button>
          </div>
        </div>
      </header>
      <main className="app-stack">
        {activePage === "home" ? (
          <section className="panel today-panel">
            <div className="metric-grid today-metric-grid">
              <MetricCard label="Day Net" value={formatSignedCurrency(currentTimelineDay?.net ?? 0)} tone={(currentTimelineDay?.net ?? 0) >= 0 ? "income" : "expense"} />
              <MetricCard label="Savings Added Today" value={formatCurrency(currentTimelineDay?.savingsNet ?? 0)} tone="income" />
              <MetricCard label="Variable Expenses Today" value={formatCurrency(currentTimelineDay?.statement.variableExpenses ?? 0)} tone="expense" />
              <article className="metric-card action-card tone-neutral">
                <span>Actions</span>
                <div className="action-card-buttons">
                  <button type="button" onClick={openCsvExportModal}>Export CSV</button>
                  <button className="ghost" type="button" onClick={openCsvImportModal}>Import CSV</button>
                </div>
              </article>
            </div>

            <div className="today-grid">
              <section className="today-entry-card">
                <div className="panel-heading compact">
                  <div>
                    <span className="section-tag">Quick Add</span>
                    <div className="transaction-type-toggle" aria-label="Today transaction type">
                      <button className={todayTransactionType === "expense" ? "nav-pill is-active" : "nav-pill"} onClick={() => setTodayTransactionType("expense")} type="button">Expense</button>
                      <button className={todayTransactionType === "income" ? "nav-pill is-active" : "nav-pill"} onClick={() => setTodayTransactionType("income")} type="button">Income</button>
                      <button className={todayTransactionType === "savings" ? "nav-pill is-active" : "nav-pill"} onClick={() => setTodayTransactionType("savings")} type="button">Savings</button>
                    </div>
                  </div>
                  <div className="expense-class-toggle" aria-label="Today expense type">
                    <button className={todayExpenseClass === "variable" ? "nav-pill is-active" : "nav-pill"} onClick={() => setTodayExpenseClass("variable")} type="button">Variable</button>
                    <button className={todayExpenseClass === "fixed" ? "nav-pill is-active" : "nav-pill"} onClick={() => setTodayExpenseClass("fixed")} type="button">Fixed</button>
                  </div>
                </div>

                <form className="today-expense-form quick-add-form" onSubmit={handleAddTodayExpense}>
                  <label className="quick-add-name expense-name-field">
                    <span>{todayTransactionTypeTitle} name</span>
                    <input value={todayExpenseDraft.name} onFocus={() => setTodayExpenseNameFocused(true)} onBlur={() => setTodayExpenseNameFocused(false)} onChange={(event) => setTodayExpenseDraft((current) => ({ ...current, name: event.target.value }))} placeholder={todayTransactionType === "income" ? "Paycheck, bonus, reimbursement..." : todayTransactionType === "savings" ? "Emergency fund, goal transfer..." : "Coffee, groceries, gas..."} autoComplete="off" />
                    {todayExpenseNameFocused && rememberedExpenseSuggestions.length ? (
                      <div className="expense-suggestion-list">
                        {rememberedExpenseSuggestions.map((transaction) => (
                          <button key={transaction.id} className="expense-suggestion" type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => selectRememberedExpense(transaction)}>
                            <span>{transaction.name}</span>
                            <small>{getCategoryLabel(state.settings.categories, transaction.type, transaction.categoryId, transaction.subcategoryId)}</small>
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </label>
                  <label className="quick-add-amount">
                    <span>Amount</span>
                    <div className="amount-control">
                      <span className="amount-addon">$</span>
                      <input type="number" min="0" step="0.01" value={todayExpenseDraft.amount} onChange={(event) => setTodayExpenseDraft((current) => ({ ...current, amount: event.target.value }))} placeholder="0.00" />
                      <span className="amount-addon amount-currency">USD</span>
                    </div>
                  </label>
                  <label className="quick-add-category">
                    <span>Category</span>
                    <select value={todayExpenseDraft.categoryId} onChange={(event) => setTodayExpenseDraft((current) => ({ ...current, categoryId: event.target.value, subcategoryId: "" }))}>
                      <option value="">Choose category</option>
                      {getCategoryOptions(state.settings.categories, todayTransactionType).map((category) => (
                        <option key={category.id} value={category.id}>{category.icon} {category.name}</option>
                      ))}
                    </select>
                  </label>
                  <label className="quick-add-subcategory">
                    <span>Subcategory</span>
                    <select value={todayExpenseDraft.subcategoryId} onChange={(event) => setTodayExpenseDraft((current) => ({ ...current, subcategoryId: event.target.value }))}>
                      <option value="">Choose subcategory</option>
                      {todayExpenseSubcategories.map((subcategory) => (
                        <option key={subcategory.id} value={subcategory.id}>{subcategory.icon} {subcategory.name}</option>
                      ))}
                    </select>
                  </label>
                  <div className="distribution-row">
                    <button className={todayExpenseDistributed ? "distribution-toggle is-active" : "distribution-toggle"} type="button" onClick={toggleTodayExpenseDistribution}>Distribution</button>
                    {todayExpenseClass === "fixed" ? (
                      <label className="fixed-frequency-field">
                        <span>Frequency</span>
                        <select value={todayFixedFrequency} onChange={(event) => setTodayFixedFrequency(event.target.value)}>
                          {frequencyOptions.map((option) => <option key={option} value={option}>{formatFrequencyOption(option)}</option>)}
                        </select>
                      </label>
                    ) : null}
                  </div>
                  {todayExpenseDistributed ? (
                    <div className="date-range-grid">
                      <div className="date-field">
                        <div className="field-label-row">
                          <span>{todayExpenseClass === "fixed" ? "Start date" : "Distribution start"}</span>
                          <button className="today-mini-button" type="button" onClick={() => setTodayExpenseDraft((current) => ({ ...current, startDate: today, endDate: current.endDate && current.endDate < today ? "" : current.endDate }))}>Today</button>
                        </div>
                        <div className="date-input-shell">
                          <input ref={todayStartDateRef} type="date" value={todayExpenseDraft.startDate} onChange={(event) => setTodayExpenseDraft((current) => ({ ...current, startDate: event.target.value, endDate: current.endDate && current.endDate < event.target.value ? "" : current.endDate }))} />
                          <button className="calendar-button" type="button" onClick={() => openDatePicker(todayStartDateRef)} aria-label="Pick start date" />
                        </div>
                      </div>
                      <div className="date-field">
                        <div className="field-label-row">
                          <span>{todayExpenseClass === "fixed" ? "End date" : "Distribution end"}</span>
                        </div>
                        <div className="date-input-shell">
                          <input ref={todayEndDateRef} type="date" min={todayExpenseDraft.startDate} value={todayExpenseDraft.endDate} onChange={(event) => setTodayExpenseDraft((current) => ({ ...current, endDate: event.target.value }))} />
                          <button className="calendar-button" type="button" onClick={() => openDatePicker(todayEndDateRef)} aria-label="Pick end date" />
                        </div>
                      </div>
                    </div>
                  ) : null}
                  <div className="form-actions">
                    <button type="submit">Add {todayExpenseClassTitle} {todayTransactionTypeTitle}</button>
                  </div>
                </form>
              </section>

              <section className="today-entry-card">
                <div className="panel-heading compact">
                  <div>
                    <span className="section-tag">Today&apos;s Lines</span>
                    <h3>{todayExpenseClassTitle} {todayTransactionTypePlural} on {currentTimelineDay?.date ?? today}</h3>
                  </div>
                </div>

                {todayExpenseEntries.length ? (
                  <div className="today-line-list">
                    {todayExpenseEntries.map((entry) => (
                      <article className="today-line-item" key={entry.id}>
                        <div>
                          <span>{entry.name}</span>
                          <small>{getCategoryLabel(state.settings.categories, entry.type, entry.source?.categoryId, entry.source?.subcategoryId)}</small>
                        </div>
                        <strong>{formatSignedCurrency(entry.amount)}</strong>
                        <div className="today-line-actions">
                          <button className="ghost small" type="button" onClick={() => handleEditTodayLine(entry)}>Edit</button>
                          <button className="ghost small danger" type="button" onClick={() => handleDeleteTransaction(entry.transactionId)}>Delete</button>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="empty-block">No {todayExpenseClassLabel} {todayTransactionTypePlural} are hitting the current day yet.</div>
                )}
              </section>
            </div>
          </section>
        ) : null}

        {activePage === "buckets" ? (
          <section className="panel ledger-panel">
            <div className="panel-heading">
              <div>
                <span className="section-tag">Buckets</span>
                <h2>Daily buckets for {selectedTimelineDay?.date ?? visibleSelectedDate}</h2>
              </div>
              <p className="subtle">Pick any forecast day and inspect the lines for that day in the same bucket layout.</p>
            </div>

            <div className="bucket-day-toolbar">
              <label className="bucket-day-picker">
                <span>View day</span>
                <input type="date" value={visibleSelectedDate} onChange={(event) => handleSelectedDayChange(event.target.value)} />
              </label>
              <MetricCard label="Current Balance" value={formatCurrency(selectedTimelineDay?.balance ?? 0)} tone="primary" />
              <MetricCard label="Day Net" value={formatSignedCurrency(selectedTimelineDay?.net ?? 0)} tone={(selectedTimelineDay?.net ?? 0) >= 0 ? "income" : "expense"} />
            </div>

            <div className="bucket-grid">
              <DailyBucketPanel title="Fixed Income" tone="income" items={selectedDayBuckets.fixedIncome} categories={state.settings.categories} />
              <DailyBucketPanel title="Variable Income" tone="income-soft" items={selectedDayBuckets.variableIncome} categories={state.settings.categories} />
              <DailyBucketPanel title="Fixed Expenses" tone="expense" items={selectedDayBuckets.fixedExpenses} categories={state.settings.categories} />
              <DailyBucketPanel title="Variable Expenses" tone="expense-soft" items={selectedDayBuckets.variableExpenses} categories={state.settings.categories} />
              <DailyBucketPanel title="Fixed Savings" tone="income" items={selectedDayBuckets.fixedSavings} categories={state.settings.categories} />
              <DailyBucketPanel title="Variable Savings" tone="income-soft" items={selectedDayBuckets.variableSavings} categories={state.settings.categories} />
              <DailyBucketPanel title="Income Splits" tone="neutral" items={selectedDayBuckets.incomeSplits} categories={state.settings.categories} />
            </div>
          </section>
        ) : null}

        {activePage === "savings" ? (
          <>
            <section className="panel today-panel">
              <div className="panel-heading">
                <div>
                  <span className="section-tag">Savings</span>
                  <h2>Savings snapshot</h2>
                </div>
                <p className="subtle">Track the separate savings balance, direct savings contributions, and income routed into savings.</p>
              </div>

              <div className="metric-grid today-metric-grid">
                <MetricCard label="Savings Balance" value={formatCurrency(currentTimelineDay?.savingsBalance ?? forecast.startingSavingsBalance)} tone="income" />
                <MetricCard label="Savings Added Today" value={formatCurrency(currentTimelineDay?.savingsNet ?? 0)} tone="income-soft" />
                <MetricCard label="Fixed Savings Today" value={formatCurrency(currentTimelineDay?.statement.fixedSavings ?? 0)} tone="neutral" />
                <MetricCard label="Income Splits Today" value={formatCurrency(currentTimelineDay?.statement.incomeSplits ?? 0)} tone="primary" />
              </div>
            </section>

            <section className="panel ledger-panel">
              <div className="panel-heading">
                <div>
                  <span className="section-tag">Savings Buckets</span>
                  <h2>Daily savings buckets for {selectedTimelineDay?.date ?? visibleSelectedDate}</h2>
                </div>
                <p className="subtle">Savings has its own view so we can inspect direct contributions separately from income split diversions.</p>
              </div>

              <div className="bucket-day-toolbar">
                <label className="bucket-day-picker">
                  <span>View day</span>
                  <input type="date" value={visibleSelectedDate} onChange={(event) => handleSelectedDayChange(event.target.value)} />
                </label>
                <MetricCard label="Savings Balance" value={formatCurrency(selectedTimelineDay?.savingsBalance ?? 0)} tone="income" />
                <MetricCard label="Savings Added" value={formatCurrency(selectedTimelineDay?.savingsNet ?? 0)} tone="income-soft" />
              </div>

              <div className="bucket-grid">
                <DailyBucketPanel title="Fixed Savings" tone="income" items={selectedDayBuckets.fixedSavings} categories={state.settings.categories} />
                <DailyBucketPanel title="Variable Savings" tone="income-soft" items={selectedDayBuckets.variableSavings} categories={state.settings.categories} />
                <DailyBucketPanel title="Income Splits" tone="primary" items={selectedDayBuckets.incomeSplits} categories={state.settings.categories} />
              </div>
            </section>
          </>
        ) : null}

        {activePage === "planner" ? (
          <>
            <section className="panel statement-panel">
              <div className="panel-heading">
                <div>
                  <span className="section-tag">Forecast</span>
                  <h2>Detailed forecast</h2>
                </div>
                <p className="subtle">The deeper planning view still breaks each day into statement buckets and a rolling balance.</p>
              </div>

              <div className="metric-grid">
                <MetricCard label="Opening Balance" value={formatCurrency(forecast.startingBalance)} tone="neutral" />
                <MetricCard label="Opening Savings" value={formatCurrency(forecast.startingSavingsBalance)} tone="income-soft" />
                <MetricCard label="Fixed Income" value={formatCurrency(forecast.totals.statement.fixedIncome)} tone="income" />
                <MetricCard label="Total Savings" value={formatCurrency(forecast.totals.savingsNet)} tone="income" />
                <MetricCard label="Day Net" value={formatCurrency(forecast.totals.statement.net)} tone="primary" />
              </div>

              <div className="chart-card">
                <div className="chart-copy">
                  <h3>Balance arc</h3>
                  <p>{forecast.rangeStart} through {forecast.rangeEnd}</p>
                </div>
                <svg viewBox="0 0 840 260" className="balance-chart" role="img" aria-label="Projected balance chart">
                  <defs>
                    <linearGradient id="chartFill" x1="0%" x2="0%" y1="0%" y2="100%">
                      <stop offset="0%" stopColor="rgba(23, 79, 70, 0.35)" />
                      <stop offset="100%" stopColor="rgba(23, 79, 70, 0.02)" />
                    </linearGradient>
                  </defs>
                  <path d={chart.area} fill="url(#chartFill)" />
                  <path d={chart.line} fill="none" stroke="var(--chart-line)" strokeWidth="5" strokeLinecap="round" />
                  <text x="22" y="26">{formatCurrency(chart.max)}</text>
                  <text x="22" y="246">{formatCurrency(chart.min)}</text>
                </svg>
              </div>

              <div className="statement-table-shell">
                <table className="statement-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Fixed Income</th>
                      <th>Variable Income</th>
                      <th>Fixed Expenses</th>
                      <th>Variable Expenses</th>
                      <th>Fixed Savings</th>
                      <th>Variable Savings</th>
                      <th>Income Splits</th>
                      <th>Day Net</th>
                      <th>Balance</th>
                      <th>Savings</th>
                    </tr>
                  </thead>
                  <tbody>
                    {forecast.timeline.map((day) => (
                      <tr key={day.date} className={day.date === selectedDay ? "is-selected" : ""} onClick={() => setSelectedDay(day.date)}>
                        <td>{day.date}</td>
                        <td>{formatCurrency(day.statement.fixedIncome)}</td>
                        <td>{formatCurrency(day.statement.variableIncome)}</td>
                        <td>{formatCurrency(day.statement.fixedExpenses)}</td>
                        <td>{formatCurrency(day.statement.variableExpenses)}</td>
                        <td>{formatCurrency(day.statement.fixedSavings)}</td>
                        <td>{formatCurrency(day.statement.variableSavings)}</td>
                        <td>{formatCurrency(day.statement.incomeSplits)}</td>
                        <td className={day.net >= 0 ? "positive" : "negative"}>{formatSignedCurrency(day.net)}</td>
                        <td>{formatCurrency(day.balance)}</td>
                        <td>{formatCurrency(day.savingsBalance)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <div className="detail-grid">
              <aside className="sidebar">
                <section className="panel sticky-panel">
                  <div className="panel-heading">
                    <div>
                      <span className="section-tag">Selected Day</span>
                      <h2>{selectedTimelineDay?.date ?? "No day selected"}</h2>
                    </div>
                  </div>

                  {selectedTimelineDay ? (
                    <>
                      <div className="day-slice-grid">
                        <SliceCard title="Fixed Income" amount={selectedTimelineDay.statement.fixedIncome} tone="income" />
                        <SliceCard title="Variable Income" amount={selectedTimelineDay.statement.variableIncome} tone="income-soft" />
                        <SliceCard title="Fixed Expenses" amount={selectedTimelineDay.statement.fixedExpenses} tone="expense" />
                        <SliceCard title="Variable Expenses" amount={selectedTimelineDay.statement.variableExpenses} tone="expense-soft" />
                        <SliceCard title="Fixed Savings" amount={selectedTimelineDay.statement.fixedSavings} tone="income" />
                        <SliceCard title="Income Splits" amount={selectedTimelineDay.statement.incomeSplits} tone="neutral" />
                      </div>
                      <pre className="markdown-preview">{selectedMarkdown}</pre>
                    </>
                  ) : (
                    <div className="empty-block">No timeline row is available yet.</div>
                  )}
                </section>
              </aside>

              <div className="detail-main">
                <section className="panel composer-panel">
                  <div className="panel-heading">
                    <div>
                      <span className="section-tag">Compose</span>
                      <h2>Add or refine a cashflow line</h2>
                    </div>
                    <button className="ghost" type="button" onClick={() => resetDraft()}>Clear Draft</button>
                  </div>

                  <form className="composer-grid" onSubmit={handleSaveTransaction}>
                    <label><span>Name</span><input value={draft.name} onChange={(event) => handleDraftChange("name", event.target.value)} required /></label>
                    <label><span>Type</span><select value={draft.type} onChange={(event) => handleDraftChange("type", event.target.value)}><option value="income">Income</option><option value="expense">Expense</option><option value="savings">Savings</option></select></label>
                    <label><span>Class</span><select value={draft.cashflowClass} onChange={(event) => handleDraftChange("cashflowClass", event.target.value)}><option value="fixed">Fixed</option><option value="variable">Variable</option></select></label>
                    <label><span>Kind</span><select value={draft.kind} onChange={(event) => handleDraftChange("kind", event.target.value)}><option value="recurring">Recurring</option><option value="one_time">One-Time</option></select></label>
                    <label><span>Amount</span><input type="number" min="0" step="0.01" value={draft.amount} onChange={(event) => handleDraftChange("amount", event.target.value)} required /></label>
                    {draft.type === "income" ? (
                      <label><span>Savings Rule %</span><input type="number" min="0" max="100" step="0.01" value={draft.savingsRulePercent || 0} onChange={(event) => handleDraftChange("savingsRulePercent", event.target.value)} /></label>
                    ) : null}
                    {draft.kind === "recurring" ? (
                      <label><span>Frequency</span><select value={draft.frequency} onChange={(event) => handleDraftChange("frequency", event.target.value)}>{frequencyOptions.map((option) => <option key={option} value={option}>{formatFrequencyOption(option)}</option>)}</select></label>
                    ) : null}
                    <label><span>Category</span><select value={draft.categoryId} onChange={(event) => handleDraftChange("categoryId", event.target.value)}><option value="">Choose category</option>{getCategoryOptions(state.settings.categories, draft.type).map((category) => <option key={category.id} value={category.id}>{category.icon} {category.name}</option>)}</select></label>
                    <label><span>Subcategory</span><select value={draft.subcategoryId} onChange={(event) => handleDraftChange("subcategoryId", event.target.value)}><option value="">Choose subcategory</option>{draftSubcategories.map((subcategory) => <option key={subcategory.id} value={subcategory.id}>{subcategory.icon} {subcategory.name}</option>)}</select></label>
                    <label><span>Start Date</span><input type="date" value={draft.startDate} onChange={(event) => handleDraftChange("startDate", event.target.value)} required /></label>
                    <label><span>End Date</span><input type="date" value={draft.endDate} onChange={(event) => handleDraftChange("endDate", event.target.value)} /></label>
                    {draft.kind === "recurring" && draft.frequency === "semimonthly" ? (
                      <div className="full-span semimonthly-grid">
                        <label><span>Semimonthly Day One</span><input type="number" min="1" max="31" value={draft.schedule.semimonthlyDays[0]} onChange={(event) => handleSemimonthlyDayChange(0, event.target.value)} /></label>
                        <label><span>Semimonthly Day Two</span><input type="number" min="1" max="31" value={draft.schedule.semimonthlyDays[1]} onChange={(event) => handleSemimonthlyDayChange(1, event.target.value)} /></label>
                      </div>
                    ) : null}
                    <label className="toggle-row full-span"><input type="checkbox" checked={draft.active} onChange={(event) => handleDraftChange("active", event.target.checked)} /><span>Keep this line active</span></label>
                    <div className="form-actions full-span"><button type="submit">{draft.id ? "Update line" : "Add line"}</button></div>
                  </form>
                </section>

                <section className="panel ledger-panel">
                  <div className="panel-heading">
                    <div>
                      <span className="section-tag">Buckets</span>
                      <h2>Recurring lines by statement bucket</h2>
                    </div>
                  </div>

                  <div className="bucket-grid">
                    <BucketPanel title="Fixed Income" tone="income" items={groupedTransactions.fixedIncome} categories={state.settings.categories} summaries={transactionSummaryMap} onEdit={handleEditTransaction} onDelete={handleDeleteTransaction} />
                    <BucketPanel title="Variable Income" tone="income-soft" items={groupedTransactions.variableIncome} categories={state.settings.categories} summaries={transactionSummaryMap} onEdit={handleEditTransaction} onDelete={handleDeleteTransaction} />
                    <BucketPanel title="Fixed Expenses" tone="expense" items={groupedTransactions.fixedExpenses} categories={state.settings.categories} summaries={transactionSummaryMap} onEdit={handleEditTransaction} onDelete={handleDeleteTransaction} />
                    <BucketPanel title="Variable Expenses" tone="expense-soft" items={groupedTransactions.variableExpenses} categories={state.settings.categories} summaries={transactionSummaryMap} onEdit={handleEditTransaction} onDelete={handleDeleteTransaction} />
                    <BucketPanel title="Fixed Savings" tone="income" items={groupedTransactions.fixedSavings} categories={state.settings.categories} summaries={transactionSummaryMap} onEdit={handleEditTransaction} onDelete={handleDeleteTransaction} />
                    <BucketPanel title="Variable Savings" tone="income-soft" items={groupedTransactions.variableSavings} categories={state.settings.categories} summaries={transactionSummaryMap} onEdit={handleEditTransaction} onDelete={handleDeleteTransaction} />
                  </div>
                </section>
              </div>
            </div>
          </>
        ) : null}

        {activePage === "settings" ? (
          <section className="panel settings-page">
            <div className="panel-heading">
              <div>
                <span className="section-tag">Settings</span>
                <h2>Workspace settings</h2>
              </div>
              <p className="subtle">Choose a setting on the left and configure it on the right.</p>
            </div>

            <div className="settings-layout">
              <aside className="settings-nav">
                <button className={settingsSection === "categories" ? "settings-link is-active" : "settings-link"} onClick={() => setSettingsSection("categories")} type="button">Categories</button>
                <button className={settingsSection === "forecast" ? "settings-link is-active" : "settings-link"} onClick={() => setSettingsSection("forecast")} type="button">Forecast</button>
                <button className={settingsSection === "appearance" ? "settings-link is-active" : "settings-link"} onClick={() => setSettingsSection("appearance")} type="button">Appearance</button>
              </aside>

              <div className="settings-detail">
                {settingsSection === "categories" ? (
                  <>
                    <div className="settings-toolbar">
                      <div className="pill-toggle">
                        <button className={categoryType === "expense" ? "nav-pill is-active" : "nav-pill"} onClick={() => setCategoryType("expense")} type="button">Expense Categories</button>
                        <button className={categoryType === "income" ? "nav-pill is-active" : "nav-pill"} onClick={() => setCategoryType("income")} type="button">Income Categories</button>
                        <button className={categoryType === "savings" ? "nav-pill is-active" : "nav-pill"} onClick={() => setCategoryType("savings")} type="button">Savings Categories</button>
                      </div>
                      <button type="button" onClick={() => addCategory(categoryType)}>Add Category</button>
                    </div>

                    <div className="category-manager">
                      {categoryOptions.map((category) => (
                        <section className="category-card" key={category.id}>
                          <div className="category-header">
                            <label><span>Icon</span><input value={category.icon} onChange={(event) => updateCategory(categoryType, category.id, "icon", event.target.value)} /></label>
                            <label className="grow"><span>Category Name</span><input value={category.name} onChange={(event) => updateCategory(categoryType, category.id, "name", event.target.value)} /></label>
                            {categoryType === "income" ? (
                              <label>
                                <span>Default Savings %</span>
                                <input type="number" min="0" max="100" step="0.01" value={category.defaultSavingsRulePercent ?? ""} onChange={(event) => updateCategory(categoryType, category.id, "defaultSavingsRulePercent", event.target.value)} />
                              </label>
                            ) : null}
                            <button className="ghost danger" type="button" onClick={() => deleteCategory(categoryType, category.id)}>Delete</button>
                          </div>
                          <div className="subcategory-list">
                            {category.subcategories.map((subcategory) => (
                              <div className="subcategory-row" key={subcategory.id}>
                                <label><span>Icon</span><input value={subcategory.icon} onChange={(event) => updateSubcategory(categoryType, category.id, subcategory.id, "icon", event.target.value)} /></label>
                                <label className="grow"><span>Subcategory Name</span><input value={subcategory.name} onChange={(event) => updateSubcategory(categoryType, category.id, subcategory.id, "name", event.target.value)} /></label>
                                {categoryType === "income" ? (
                                  <label>
                                    <span>Default Savings %</span>
                                    <input type="number" min="0" max="100" step="0.01" value={subcategory.defaultSavingsRulePercent ?? ""} onChange={(event) => updateSubcategory(categoryType, category.id, subcategory.id, "defaultSavingsRulePercent", event.target.value)} />
                                  </label>
                                ) : null}
                                <button className="ghost danger" type="button" onClick={() => deleteSubcategory(categoryType, category.id, subcategory.id)}>Delete</button>
                              </div>
                            ))}
                          </div>
                          <div className="form-actions"><button className="ghost" type="button" onClick={() => addSubcategory(categoryType, category.id)}>Add Subcategory</button></div>
                        </section>
                      ))}
                    </div>
                  </>
                ) : null}

                {settingsSection === "forecast" ? (
                  <div className="form-grid">
                    <label><span>Starting Balance</span><input type="number" step="0.01" value={state.settings.startingBalance} onChange={(event) => updateSettings("startingBalance", Number(event.target.value))} /></label>
                    <label><span>Starting Savings Balance</span><input type="number" step="0.01" value={state.settings.startingSavingsBalance ?? 0} onChange={(event) => updateSettings("startingSavingsBalance", Number(event.target.value))} /></label>
                    <label><span>Forecast Start</span><input type="date" value={state.settings.forecastStartDate} onChange={(event) => updateSettings("forecastStartDate", event.target.value)} /></label>
                    <label><span>Forecast Days</span><input type="number" min="7" value={state.settings.forecastDays} onChange={(event) => updateSettings("forecastDays", Number(event.target.value))} /></label>
                  </div>
                ) : null}

                {settingsSection === "appearance" ? (
                  <div className="appearance-grid">
                    <MetricCard label="Theme Mode" value={state.settings.themeMode} tone="neutral" />
                    <MetricCard label="Resolved Theme" value={resolvedTheme} tone="primary" />
                    <MetricCard label="Dark Mode Rule" value="auto by time of day" tone="income-soft" />
                    <div className="appearance-controls">
                      <label><span>Theme preference</span><select value={state.settings.themeMode} onChange={(event) => updateSettings("themeMode", event.target.value)}><option value="auto">Auto</option><option value="light">Light</option><option value="dark">Dark</option></select></label>
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          </section>
        ) : null}
      </main>
      {todayEditDraft ? (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setTodayEditDraft(null)}>
          <section className="today-edit-modal" role="dialog" aria-modal="true" aria-labelledby="today-edit-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="panel-heading compact">
              <div>
                <span className="section-tag">Edit Expense</span>
                <h2 id="today-edit-title">Refine today&apos;s line</h2>
              </div>
              <button className="ghost small" type="button" onClick={() => setTodayEditDraft(null)}>Close</button>
            </div>

            <form className="today-edit-grid" onSubmit={handleSaveTodayEdit}>
              <label><span>Name</span><input value={todayEditDraft.name} onChange={(event) => handleTodayEditChange("name", event.target.value)} required /></label>
              <label><span>Class</span><select value={todayEditDraft.cashflowClass} onChange={(event) => handleTodayEditChange("cashflowClass", event.target.value)}><option value="fixed">Fixed</option><option value="variable">Variable</option></select></label>
              <label><span>Kind</span><select value={todayEditDraft.kind} onChange={(event) => handleTodayEditChange("kind", event.target.value)}><option value="recurring">Recurring</option><option value="one_time">One-Time</option></select></label>
              <label><span>Amount</span><input type="number" min="0" step="0.01" value={todayEditDraft.amount} onChange={(event) => handleTodayEditChange("amount", event.target.value)} required /></label>
              {todayEditDraft.kind === "recurring" ? (
                <label><span>Frequency</span><select value={todayEditDraft.frequency} onChange={(event) => handleTodayEditChange("frequency", event.target.value)}>{frequencyOptions.map((option) => <option key={option} value={option}>{formatFrequencyOption(option)}</option>)}</select></label>
              ) : null}
              <label><span>Category</span><select value={todayEditDraft.categoryId} onChange={(event) => handleTodayEditChange("categoryId", event.target.value)}><option value="">Choose category</option>{getCategoryOptions(state.settings.categories, "expense").map((category) => <option key={category.id} value={category.id}>{category.icon} {category.name}</option>)}</select></label>
              <label><span>Subcategory</span><select value={todayEditDraft.subcategoryId} onChange={(event) => handleTodayEditChange("subcategoryId", event.target.value)}><option value="">Choose subcategory</option>{todayEditSubcategories.map((subcategory) => <option key={subcategory.id} value={subcategory.id}>{subcategory.icon} {subcategory.name}</option>)}</select></label>
              <label><span>Start Date</span><input type="date" value={todayEditDraft.startDate} onChange={(event) => handleTodayEditChange("startDate", event.target.value)} required /></label>
              <label><span>End Date</span><input type="date" min={todayEditDraft.startDate} value={todayEditDraft.endDate} onChange={(event) => handleTodayEditChange("endDate", event.target.value)} /></label>
              {todayEditDraft.kind === "recurring" && todayEditDraft.frequency === "semimonthly" ? (
                <div className="full-span semimonthly-grid">
                  <label><span>Semimonthly Day One</span><input type="number" min="1" max="31" value={todayEditDraft.schedule.semimonthlyDays[0]} onChange={(event) => handleTodayEditSemimonthlyDayChange(0, event.target.value)} /></label>
                  <label><span>Semimonthly Day Two</span><input type="number" min="1" max="31" value={todayEditDraft.schedule.semimonthlyDays[1]} onChange={(event) => handleTodayEditSemimonthlyDayChange(1, event.target.value)} /></label>
                </div>
              ) : null}
              <label className="toggle-row full-span"><input type="checkbox" checked={todayEditDraft.active} onChange={(event) => handleTodayEditChange("active", event.target.checked)} /><span>Keep this line active</span></label>
              <div className="form-actions full-span">
                <button type="submit">Save Expense</button>
                <button className="ghost" type="button" onClick={() => setTodayEditDraft(null)}>Cancel</button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
      {csvExportDraft ? (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setCsvExportDraft(null)}>
          <section className="today-edit-modal export-csv-modal" role="dialog" aria-modal="true" aria-labelledby="csv-export-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="panel-heading compact">
              <div>
                <span className="section-tag">Export CSV</span>
                <h2 id="csv-export-title">Full date range export</h2>
              </div>
              <button className="ghost small" type="button" onClick={() => setCsvExportDraft(null)}>Close</button>
            </div>

            <form className="export-csv-grid" onSubmit={handleCsvExport}>
              <label>
                <span>Start Date</span>
                <input type="date" value={csvExportDraft.startDate} onChange={(event) => handleCsvExportDateChange("startDate", event.target.value)} required />
              </label>
              <label>
                <span>End Date</span>
                <input type="date" min={csvExportDraft.startDate} value={csvExportDraft.endDate} onChange={(event) => handleCsvExportDateChange("endDate", event.target.value)} required />
              </label>
              <div className="export-summary full-span">
                <strong>{csvExportDayCount} days ready</strong>
                <p>This file includes daily summary rows plus every income, expense, savings, and income-split detail line in the selected range.</p>
                {!csvExportRangeReady ? <small>Expanding the forecast range. Try Export CSV again in a moment.</small> : null}
              </div>
              <div className="form-actions full-span">
                <button type="submit" disabled={!csvExportRangeReady}>Export CSV</button>
                <button className="ghost" type="button" onClick={() => setCsvExportDraft(null)}>Cancel</button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
      {csvImportDraft ? (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setCsvImportDraft(null)}>
          <section className="today-edit-modal import-csv-modal" role="dialog" aria-modal="true" aria-labelledby="csv-import-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="panel-heading compact">
              <div>
                <span className="section-tag">Import CSV</span>
                <h2 id="csv-import-title">Merge transactions</h2>
              </div>
              <button className="ghost small" type="button" onClick={() => setCsvImportDraft(null)}>Close</button>
            </div>

            <form className="import-csv-grid" onSubmit={handleCsvImport}>
              <label className="full-span">
                <span>Choose CSV</span>
                <input type="file" accept=".csv,text/csv" onChange={(event) => handleCsvImportFile(event.target.files?.[0])} />
              </label>
              <label className="full-span">
                <span>CSV Text</span>
                <textarea value={csvImportDraft.text} onChange={(event) => handleCsvImportText(event.target.value, csvImportDraft.fileName)} placeholder="Paste a FinProg CSV export here..." />
              </label>
              <div className="export-summary full-span">
                <strong>{csvImportDraft.fileName || "Ready for a CSV"}</strong>
                <p>Import reads transaction detail rows, skips generated income-split rows, and merges by transaction ID or matching transaction shape.</p>
                {csvImportDraft.message ? <small>{csvImportDraft.message}</small> : null}
              </div>
              <div className="form-actions full-span">
                <button type="submit">Import CSV</button>
                <button className="ghost" type="button" onClick={handleCsvConvertDownload}>Download Converted CSV</button>
                <button className="ghost" type="button" onClick={() => setCsvImportDraft(null)}>Done</button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
    </div>
  );
}

function MetricCard({ label, value, tone }) {
  return (
    <article className={`metric-card tone-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function SliceCard({ title, amount, tone }) {
  return (
    <article className={`slice-card tone-${tone}`}>
      <span>{title}</span>
      <strong>{formatCurrency(amount)}</strong>
    </article>
  );
}

function BucketPanel({ title, items, categories, summaries, onEdit, onDelete, tone }) {
  return (
    <section className={`bucket-panel tone-${tone}`}>
      <header>
        <h3>{title}</h3>
        <span>{items.length} line{items.length === 1 ? "" : "s"}</span>
      </header>
      {items.length ? (
        <div className="bucket-list">
          {items.map((item) => {
            const summary = summaries[item.id] ?? {};
            return (
            <article key={item.id} className="bucket-item">
              <div>
                <h4>{item.name}</h4>
                <p>{summary.scheduleDescription ?? "Schedule unavailable"}</p>
                <small>{getCategoryLabel(categories, item.type, item.categoryId, item.subcategoryId)}</small>
              </div>
              <div className="bucket-meta">
                <strong>{formatSignedCurrency(item.type === "expense" || item.type === "savings" ? -item.amount : item.amount)}</strong>
                <span>{formatSignedCurrency(summary.dailyRate ?? 0)}/day</span>
                {item.type === "income" && item.savingsRulePercent ? <span>Split: {item.savingsRulePercent}% to savings</span> : null}
                <span>Next: {summary.nextOccurrence ?? "—"}</span>
              </div>
              <div className="bucket-actions">
                <button className="ghost small" type="button" onClick={() => onEdit(item)}>Edit</button>
                <button className="ghost small danger" type="button" onClick={() => onDelete(item.id)}>Delete</button>
              </div>
            </article>
            );
          })}
        </div>
      ) : (
        <div className="empty-block">No lines in this bucket yet.</div>
      )}
    </section>
  );
}

function DailyBucketPanel({ title, items, tone, categories }) {
  function getEntryKindLabel(item) {
    if (item.entryKind === "one_time") {
      return "One-time";
    }
    if (item.entryKind === "distributed_range") {
      return "Distributed range";
    }
    return "Daily recurring allocation";
  }

  return (
    <section className={`bucket-panel tone-${tone}`}>
      <header>
        <h3>{title}</h3>
        <span>{items.length} line{items.length === 1 ? "" : "s"}</span>
      </header>
      {items.length ? (
        <div className="bucket-list">
          {items.map((item) => (
            <article key={item.id} className="bucket-item">
              <div>
                <h4>{item.name}</h4>
                <p>{getEntryKindLabel(item)}</p>
                <small>{getCategoryLabel(categories, item.type, item.source?.categoryId, item.source?.subcategoryId)}</small>
              </div>
              <div className="bucket-meta">
                <strong>{formatSignedCurrency(item.entryKind === "income_split" ? -(item.savingsAmount ?? 0) : item.amount)}</strong>
                {item.entryKind === "income_split" ? <span>Added to savings: {formatCurrency(item.savingsAmount ?? 0)}</span> : null}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="empty-block">No lines in this bucket for the selected day.</div>
      )}
    </section>
  );
}
