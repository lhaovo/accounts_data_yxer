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

function yesterdayText() {
  const date = new Date();
  date.setDate(date.getDate() - 1);
  return date.toISOString().slice(0, 10);
}

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
  on("openFullUpdateConfirm", "click", () => {
    $("fullUpdateMessage").textContent = `确认更新 2026-04-01 至 ${yesterdayText()} 的全部数据？已有同日期同账号数据时，会按阅读量保留较大的一条。`;
    $("fullUpdateDialog").showModal();
  });
  on("fullUpdateCancel", "click", () => $("fullUpdateDialog").close());
  on("fullUpdateClose", "click", () => $("fullUpdateDialog").close());
  on("fullUpdateConfirm", "click", () => {
    $("fullUpdateDialog").close();
    startFetch("all", reloadPage).catch((err) => alert(err.message));
  });
}

async function boot() {
  bindEvents();
  await reloadPage();
}

boot().catch((err) => {
  $("statusText").textContent = err.message;
});
