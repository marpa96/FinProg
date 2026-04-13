import { useEffect, useMemo, useState } from "react";

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
    titleClassName: "balance-hero",
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
    categoryId: "",
    subcategoryId: "",
  });

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

    if (!forecast.timeline.some((entry) => entry.date === selectedDay)) {
      setSelectedDay(currentTimelineDay?.date ?? forecast.timeline[0]?.date ?? "");
    }
  }, [currentTimelineDay, forecast.timeline, selectedDay]);

  const selectedTimelineDay = forecast.timeline.find((entry) => entry.date === selectedDay) ?? currentTimelineDay ?? forecast.timeline[0];
  const selectedMarkdown = selectedTimelineDay ? (forecastData.markdownByDate?.[selectedTimelineDay.date] ?? "") : "";
  const pageHeader = getPageHeader(activePage, currentTimelineDay, selectedTimelineDay, forecast);
  const transactionSummaryMap = useMemo(
    () => Object.fromEntries((forecast.transactionSummaries ?? []).map((summary) => [summary.id, summary])),
    [forecast.transactionSummaries],
  );
  const categoryOptions = getCategoryOptions(state.settings.categories, categoryType);
  const todayExpenseSubcategories = getSubcategoryOptions(state.settings.categories, "expense", todayExpenseDraft.categoryId);
  const draftSubcategories = getSubcategoryOptions(state.settings.categories, draft.type, draft.categoryId);

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

    const transaction = buildDraftTransaction({
      id: crypto.randomUUID(),
      name: todayExpenseDraft.name.trim() || "Today Variable Expense",
      type: "expense",
      kind: "one_time",
      cashflowClass: "variable",
      amount,
      frequency: "",
      startDate: currentTimelineDay?.date ?? today,
      endDate: "",
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
      categoryId: "",
      subcategoryId: "",
    });
  }

  function handleEditTransaction(transaction) {
    setDraft(createDraftFromTransaction(transaction));
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

  const todayVariableEntries = (currentTimelineDay?.detailEntries ?? []).filter(
    (entry) => entry.type === "expense" && entry.cashflowClass === "variable",
  );

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
            <div className="panel-heading">
              <div>
                <span className="section-tag">Today</span>
                <h2>Current balance</h2>
              </div>
              <p className="subtle">This balance uses the current forecast day, not the opening scenario balance.</p>
            </div>

            <div className="metric-grid today-metric-grid">
              <MetricCard label="Current Balance" value={formatCurrency(currentTimelineDay?.balance ?? forecast.startingBalance)} tone="primary" />
              <MetricCard label="Savings Balance" value={formatCurrency(currentTimelineDay?.savingsBalance ?? forecast.startingSavingsBalance)} tone="income-soft" />
              <MetricCard label="Day Net" value={formatSignedCurrency(currentTimelineDay?.net ?? 0)} tone={(currentTimelineDay?.net ?? 0) >= 0 ? "income" : "expense"} />
              <MetricCard label="Savings Added Today" value={formatCurrency(currentTimelineDay?.savingsNet ?? 0)} tone="income" />
              <MetricCard label="Variable Expenses Today" value={formatCurrency(currentTimelineDay?.statement.variableExpenses ?? 0)} tone="expense" />
            </div>

            <div className="today-grid">
              <section className="today-entry-card">
                <div className="panel-heading compact">
                  <div>
                    <span className="section-tag">Quick Add</span>
                    <h3>Add today&apos;s variable expense</h3>
                  </div>
                </div>

                <form className="today-expense-form" onSubmit={handleAddTodayExpense}>
                  <label>
                    <span>Expense name</span>
                    <input value={todayExpenseDraft.name} onChange={(event) => setTodayExpenseDraft((current) => ({ ...current, name: event.target.value }))} placeholder="Coffee, groceries, gas..." />
                  </label>
                  <label>
                    <span>Amount</span>
                    <input type="number" min="0" step="0.01" value={todayExpenseDraft.amount} onChange={(event) => setTodayExpenseDraft((current) => ({ ...current, amount: event.target.value }))} placeholder="0.00" />
                  </label>
                  <label>
                    <span>Category</span>
                    <select value={todayExpenseDraft.categoryId} onChange={(event) => setTodayExpenseDraft((current) => ({ ...current, categoryId: event.target.value, subcategoryId: "" }))}>
                      <option value="">Choose category</option>
                      {getCategoryOptions(state.settings.categories, "expense").map((category) => (
                        <option key={category.id} value={category.id}>{category.icon} {category.name}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>Subcategory</span>
                    <select value={todayExpenseDraft.subcategoryId} onChange={(event) => setTodayExpenseDraft((current) => ({ ...current, subcategoryId: event.target.value }))}>
                      <option value="">Choose subcategory</option>
                      {todayExpenseSubcategories.map((subcategory) => (
                        <option key={subcategory.id} value={subcategory.id}>{subcategory.icon} {subcategory.name}</option>
                      ))}
                    </select>
                  </label>
                  <div className="form-actions">
                    <button type="submit">Add Expense</button>
                  </div>
                </form>
              </section>

              <section className="today-entry-card">
                <div className="panel-heading compact">
                  <div>
                    <span className="section-tag">Today&apos;s Lines</span>
                    <h3>{currentTimelineDay?.date ?? today}</h3>
                  </div>
                </div>

                {todayVariableEntries.length ? (
                  <div className="today-line-list">
                    {todayVariableEntries.map((entry) => (
                      <article className="today-line-item" key={entry.id}>
                        <div>
                          <span>{entry.name}</span>
                          <small>{getCategoryLabel(state.settings.categories, "expense", entry.source?.categoryId, entry.source?.subcategoryId)}</small>
                        </div>
                        <strong>{formatSignedCurrency(entry.amount)}</strong>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="empty-block">No variable expenses are hitting the current day yet.</div>
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
                <h2>Daily buckets for {selectedTimelineDay?.date ?? forecast.rangeStart}</h2>
              </div>
              <p className="subtle">Pick any forecast day and inspect the lines for that day in the same bucket layout.</p>
            </div>

            <div className="bucket-day-toolbar">
              <label className="bucket-day-picker">
                <span>View day</span>
                <input type="date" value={selectedTimelineDay?.date ?? ""} min={forecast.rangeStart} max={forecast.rangeEnd} onChange={(event) => setSelectedDay(event.target.value)} />
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
                  <h2>Daily savings buckets for {selectedTimelineDay?.date ?? forecast.rangeStart}</h2>
                </div>
                <p className="subtle">Savings has its own view so we can inspect direct contributions separately from income split diversions.</p>
              </div>

              <div className="bucket-day-toolbar">
                <label className="bucket-day-picker">
                  <span>View day</span>
                  <input type="date" value={selectedTimelineDay?.date ?? ""} min={forecast.rangeStart} max={forecast.rangeEnd} onChange={(event) => setSelectedDay(event.target.value)} />
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
                      <label><span>Frequency</span><select value={draft.frequency} onChange={(event) => handleDraftChange("frequency", event.target.value)}>{frequencyOptions.map((option) => <option key={option} value={option}>{option}</option>)}</select></label>
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
                    <label><span>Forecast Days</span><input type="number" min="7" max="366" value={state.settings.forecastDays} onChange={(event) => updateSettings("forecastDays", Number(event.target.value))} /></label>
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
                <p>{item.entryKind === "one_time" ? "One-time" : "Daily recurring allocation"}</p>
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
