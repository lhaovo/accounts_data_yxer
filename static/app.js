const state = {
  mode: "single",
  status: null,
  lastRows: [],
  sortKey: "metric_date",
  sortDir: "asc",
  pendingRefreshMode: "latest",
};

const $ = (id) => document.getElementById(id);

const numericColumns = new Set(["fans", "play", "exposure", "like", "comment", "share", "collect", "publish_count"]);

const totalTargets = {
  fans: "totalFans",
  play: "totalPlay",
  exposure: "totalExposure",
  like: "totalLike",
  comment: "totalComment",
  share: "totalShare",
  collect: "totalCollect",
  publish_count: "totalPublish",
};

function todayLike(value) {
  return value || new Date().toISOString().slice(0, 10);
}

function buildQuery() {
  const params = new URLSearchParams();
  if (state.mode === "single") {
    params.set("date", $("dateInput").value);
  } else {
    params.set("start", $("startInput").value);
    params.set("end", $("endInput").value);
  }
  const platform = $("platformInput").value;
  if (platform) params.set("platform", platform);
  if ($("includeEmptyInput").checked) params.set("includeEmpty", "1");
  return params;
}

async function getJson(url, options) {
  const res = await fetch(url, options);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error?.message || `HTTP ${res.status}`);
  }
  return data;
}

function setMode(mode) {
  state.mode = mode;
  $("singleMode").classList.toggle("active", mode === "single");
  $("rangeMode").classList.toggle("active", mode === "range");
  document.querySelectorAll(".single-date").forEach((el) => el.classList.toggle("hidden", mode !== "single"));
  document.querySelectorAll(".range-date").forEach((el) => el.classList.toggle("hidden", mode !== "range"));
}

function parseNumber(value) {
  if (value === null || value === undefined || value === "-") return null;
  const number = Number(String(value).replace(/,/g, ""));
  return Number.isFinite(number) ? number : null;
}

function compareRows(a, b) {
  const key = state.sortKey;
  const direction = state.sortDir === "asc" ? 1 : -1;
  if (numericColumns.has(key)) {
    const av = parseNumber(a[key]);
    const bv = parseNumber(b[key]);
    if (av === null && bv === null) return 0;
    if (av === null) return 1;
    if (bv === null) return -1;
    return (av - bv) * direction;
  }
  const av = a[key] === "-" || a[key] === null || a[key] === undefined ? "" : String(a[key]);
  const bv = b[key] === "-" || b[key] === null || b[key] === undefined ? "" : String(b[key]);
  return av.localeCompare(bv, "zh-CN", { numeric: true }) * direction;
}

function sortedRows(rows) {
  return [...rows].sort(compareRows);
}

function updateSortIndicators() {
  document.querySelectorAll("th.sortable").forEach((th) => {
    const active = th.dataset.sort === state.sortKey;
    th.classList.toggle("active", active);
    th.dataset.dir = active ? state.sortDir : "";
  });
}

function formatNumber(value) {
  if (value === null || value === undefined) return "-";
  return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
}

function updateTotals(rows) {
  $("totalCount").textContent = `${rows.length} 行`;
  const totals = {};
  const counts = {};
  for (const key of Object.keys(totalTargets)) {
    totals[key] = 0;
    counts[key] = 0;
  }
  for (const row of rows) {
    for (const key of Object.keys(totalTargets)) {
      const value = parseNumber(row[key]);
      if (value === null) continue;
      totals[key] += value;
      counts[key] += 1;
    }
  }
  for (const [key, target] of Object.entries(totalTargets)) {
    $(target).textContent = counts[key] ? formatNumber(totals[key]) : "-";
  }
}

async function loadStatus() {
  const data = await getJson("/api/status");
  state.status = data;
  $("statusText").textContent = data.dbExists
    ? `数据库：${data.dbPath}`
    : `未找到数据库：${data.dbPath}`;
  $("accountCount").textContent = data.accountCount ?? "-";
  $("metricCount").textContent = data.metricCount ?? "-";
  const minDate = data.dateRange?.minDate || "";
  const maxDate = data.dateRange?.maxDate || "";
  $("dateRange").textContent = minDate && maxDate ? `${minDate} 至 ${maxDate}` : "-";

  $("platformInput").innerHTML = '<option value="">全部平台</option>';
  for (const item of data.platforms || []) {
    const option = document.createElement("option");
    option.value = item.name;
    option.textContent = `${item.name}（${item.accountCount}）`;
    $("platformInput").appendChild(option);
  }

  const defaultDate = maxDate || new Date().toISOString().slice(0, 10);
  $("dateInput").value = todayLike(defaultDate);
  $("startInput").value = todayLike(minDate || defaultDate);
  $("endInput").value = todayLike(defaultDate);
}

function renderRows(rows) {
  state.lastRows = rows;
  $("rowCount").textContent = rows.length;
  const body = $("rowsBody");
  body.innerHTML = "";
  updateSortIndicators();
  updateTotals(rows);
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="13" class="empty">暂无数据</td></tr>';
    return;
  }
  for (const row of sortedRows(rows)) {
    const tr = document.createElement("tr");
    const cells = [
      row.metric_date,
      row.platform_name,
      row.platform_account_name,
      row.platform_account_id,
      row.fans,
      row.play,
      row.exposure,
      row.like,
      row.comment,
      row.share,
      row.collect,
      row.publish_count,
      row.login_status,
    ];
    for (const [index, value] of cells.entries()) {
      const td = document.createElement("td");
      if (index >= 4 && index <= 11) td.classList.add("numeric");
      td.textContent = value ?? "-";
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
}

async function queryRows() {
  $("queryButton").disabled = true;
  try {
    const data = await getJson(`/api/metrics?${buildQuery().toString()}`);
    renderRows(data.rows || []);
  } finally {
    $("queryButton").disabled = false;
  }
}

function downloadCsv() {
  window.location.href = `/api/export.csv?${buildQuery().toString()}`;
}

async function loadSettingsState() {
  const data = await getJson("/api/settings");
  $("settingsMessage").textContent = data.hasApiKey
    ? "后端已保存 API Key。输入新值并保存可覆盖。"
    : "后端尚未保存 API Key。";
  return data;
}

async function openSettings() {
  $("settingsApiKeyInput").value = "";
  $("settingsMessage").textContent = "正在读取设置状态...";
  $("settingsDialog").showModal();
  await loadSettingsState();
}

async function saveSettings() {
  const value = $("settingsApiKeyInput").value.trim();
  if (!value) {
    $("settingsMessage").textContent = "请输入新的蚁小二 API Key。";
    return;
  }
  await getJson("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ apiKey: value }),
  });
  $("settingsApiKeyInput").value = "";
  $("settingsMessage").textContent = "已保存到后端。";
}

async function clearSettings() {
  await getJson("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ clear: true }),
  });
  $("settingsApiKeyInput").value = "";
  $("settingsMessage").textContent = "后端保存的 API Key 已清除。";
}

function openRefresh(mode) {
  state.pendingRefreshMode = mode;
  $("refreshOutput").textContent = mode === "full" ? "准备全量刷新。" : "准备刷新最近一天。";
  $("refreshDialog").showModal();
}

async function runRefresh() {
  const settings = await getJson("/api/settings");
  if (!settings.hasApiKey) {
    $("refreshOutput").textContent = "请先点击右上角设置按钮，填写并保存蚂小二 API Key。";
    return;
  }
  $("refreshOutput").textContent = "正在刷新...";
  try {
    const res = await fetch("/api/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: state.pendingRefreshMode }),
    });
    const data = await res.json();
    $("refreshOutput").textContent = JSON.stringify(data, null, 2);
    if (data.ok) await loadStatus();
  } catch (err) {
    $("refreshOutput").textContent = "刷新失败: " + err.message;
  }
}
function bindEvents() {
  $("singleMode").addEventListener("click", () => setMode("single"));
  $("rangeMode").addEventListener("click", () => setMode("range"));
  $("queryButton").addEventListener("click", () => queryRows().catch((err) => alert(err.message)));
  $("csvButton").addEventListener("click", downloadCsv);
  $("settingsButton").addEventListener("click", () => openSettings().catch((err) => ($("settingsMessage").textContent = String(err))));
  $("saveSettings").addEventListener("click", () => saveSettings().catch((err) => ($("settingsMessage").textContent = String(err))));
  $("clearSettings").addEventListener("click", () => clearSettings().catch((err) => ($("settingsMessage").textContent = String(err))));
  $("refreshLatest").addEventListener("click", () => openRefresh("latest"));
  $("refreshFull").addEventListener("click", () => openRefresh("full"));
  $("runRefresh").addEventListener("click", () => runRefresh().catch((err) => ($("refreshOutput").textContent = String(err))));
  $("refreshDialog").addEventListener("close", () => {
    if ($("refreshOutput").textContent.startsWith("准备")) return;
  });
  $("refreshOutput").addEventListener("dblclick", () => runRefresh().catch((err) => ($("refreshOutput").textContent = String(err))));
  document.querySelectorAll("th.sortable").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (state.sortKey === key) {
        state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
      } else {
        state.sortKey = key;
        state.sortDir = numericColumns.has(key) ? "desc" : "asc";
      }
      renderRows(state.lastRows);
    });
  });
}

async function boot() {
  bindEvents();
  await loadStatus();
  await queryRows();
}

boot().catch((err) => {
  $("statusText").textContent = err.message;
});
