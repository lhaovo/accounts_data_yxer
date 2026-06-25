import { api } from "./api.js";
import { $, on } from "./dom.js";
import { bindFilterEvents, buildQuery } from "./filters.js";
import { updateMergeButton, bindMergeEvents } from "./merge.js";
import { refreshAccounts, startFetch } from "./refresh.js";
import {
  clearSettings,
  openSettings,
  saveSchedule,
  saveSettings,
  stopScheduleTimer,
} from "./settings.js";
import { loadStatus } from "./status.js";
import { bindSortHeaders, renderRows } from "./table.js";

async function queryRows() {
  $("queryButton").disabled = true;
  try {
    const data = await api.metrics(buildQuery());
    renderRows(data.rows || [], updateMergeButton);
  } finally {
    $("queryButton").disabled = false;
  }
}

async function reloadPage() {
  await loadStatus();
  await queryRows();
}

function downloadCsv() {
  window.location.href = `/api/export.csv?${buildQuery().toString()}`;
}

function bindEvents() {
  bindFilterEvents();
  bindSortHeaders((rows) => renderRows(rows, updateMergeButton));
  bindMergeEvents({ reloadPage });

  on("queryButton", "click", () => queryRows().catch((err) => alert(err.message)));
  on("csvButton", "click", downloadCsv);
  on("settingsButton", "click", () => openSettings().catch((err) => ($("settingsMessage").textContent = String(err))));
  on("settingsDialog", "close", stopScheduleTimer);
  on("saveSettings", "click", () => saveSettings().catch((err) => ($("settingsMessage").textContent = String(err))));
  on("clearSettings", "click", () => clearSettings().catch((err) => ($("settingsMessage").textContent = String(err))));
  on("saveSchedule", "click", () => saveSchedule().catch((err) => ($("scheduleMessage").textContent = String(err))));
  on("refreshAccounts", "click", () => refreshAccounts(reloadPage).catch((err) => alert(err.message)));
  on("fetchRecent", "click", () => startFetch("recent", reloadPage).catch((err) => alert(err.message)));
  on("fetchFull", "click", () => startFetch("full", reloadPage).catch((err) => alert(err.message)));
}

async function boot() {
  bindEvents();
  await reloadPage();
}

boot().catch((err) => {
  $("statusText").textContent = err.message;
});
