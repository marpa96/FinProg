const today = new Date().toISOString().slice(0, 10);

export const STORAGE_KEY = "finprog.cashflowPlanner.v1";
export const AVERAGE_DAYS_PER_YEAR = 365.2425;

export const DEFAULT_STATE = {
  settings: {
    startingBalance: 0,
    forecastStartDate: today,
    forecastDays: 90,
  },
  transactions: [],
};

export const SAMPLE_STATE = {
  settings: {
    startingBalance: 1200,
    forecastStartDate: today,
    forecastDays: 60,
  },
  transactions: [
    {
      id: "sample-paycheck",
      name: "Primary Paycheck",
      type: "income",
      kind: "recurring",
      cashflowClass: "fixed",
      amount: 2200,
      frequency: "biweekly",
      startDate: today,
      endDate: "",
      schedule: {},
      active: true,
    },
    {
      id: "sample-rent",
      name: "Rent",
      type: "expense",
      kind: "recurring",
      cashflowClass: "fixed",
      amount: 1450,
      frequency: "monthly",
      startDate: today,
      endDate: "",
      schedule: {},
      active: true,
    },
    {
      id: "sample-internet",
      name: "Internet",
      type: "expense",
      kind: "recurring",
      cashflowClass: "fixed",
      amount: 70,
      frequency: "monthly",
      startDate: today,
      endDate: "",
      schedule: {},
      active: true,
    },
    {
      id: "sample-gym",
      name: "Gym Membership",
      type: "expense",
      kind: "recurring",
      cashflowClass: "variable",
      amount: 30,
      frequency: "semimonthly",
      startDate: today,
      endDate: "",
      schedule: {
        semimonthlyDays: [5, 20],
      },
      active: true,
    },
    {
      id: "sample-bonus",
      name: "Tax Refund",
      type: "income",
      kind: "one_time",
      cashflowClass: "variable",
      amount: 650,
      frequency: "",
      startDate: today,
      endDate: "",
      schedule: {},
      active: true,
    },
  ],
};

export function getFrequencyLabel(transaction) {
  if (transaction.kind === "one_time") {
    return "One-Time";
  }

  const labels = {
    weekly: "Weekly",
    biweekly: "Biweekly",
    semimonthly: "Semimonthly",
    monthly: "Monthly",
    yearly: "Yearly",
  };

  return labels[transaction.frequency] ?? transaction.frequency;
}
