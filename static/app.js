const state = {
  mode: "single",
  status: null,
  lastRows: [],
  sortKey: "metric_date",
  sortDir: "asc",
  pendingRefreshMode: "latest",
};

const $ = (id) => document.getElementById(id);

const numericColumns = new Set(["fans", "play", "like", "comment", "collect", "publish_count"]);

const totalTargets = {
  fans: "totalFans",
  play: "totalPlay",
  like: "totalLike",
  comment: "totalComment",
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
  const checkedPlatforms = [...document.querySelectorAll("#platformList input[type=\"checkbox\"]:checked")].map(cb => cb.value);
  if (checkedPlatforms.length) params.set("platforms", checkedPlatforms.join(","));
  if ($("includeEmptyInput").checked) params.set("includeEmpty", "1");
  if (state.mode === "range" && $("mergeInput").checked) params.set("merge", "1");
  const checkedAccounts = [...document.querySelectorAll("#accountList input[type=\"checkbox\"]:checked")].map(cb => cb.value);
  if (checkedAccounts.length) params.set("accountIds", checkedAccounts.join(","));
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
  document.querySelectorAll(".merge-only").forEach((el) => el.classList.toggle("hidden", mode !== "range"));
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
  const ovMin = data.overviewDateRange?.minDate || "";
  const ovMax = data.overviewDateRange?.maxDate || "";
  if (ovMin && ovMax) {
    $("dateRange").textContent = ovMin + " 至 " + ovMax + " (新)";
  }
  const minDate = data.dateRange?.minDate || "";
  const maxDate = data.dateRange?.maxDate || "";
  $("dateRange").textContent = minDate && maxDate ? `${minDate} 至 ${maxDate}` : "-";

  // Populate platform filter
  const platformList = $("platformList");
  platformList.innerHTML = "";
  for (const item of data.platforms || []) {
    const label = document.createElement("label");
    label.innerHTML = '<input type="checkbox" value="' + item.name + '" /> ' + item.name + ' <span style="color:var(--muted);font-size:11px">' + item.accountCount + '</span>';
    platformList.appendChild(label);
  }

  const defaultDate = maxDate || new Date().toISOString().slice(0, 10);
  $("dateInput").value = todayLike(defaultDate);
  $("startInput").value = todayLike(minDate || defaultDate);
  $("endInput").value = todayLike(defaultDate);
  // Populate account filter
  const accountList = $("accountList");
  accountList.innerHTML = "";
  for (const acc of data.accounts || []) {
    const label = document.createElement("label");
    label.innerHTML = '<input type="checkbox" value="' + acc.platform_account_id + '" /> ' + acc.platform_account_name + ' <span style="color:var(--muted);font-size:11px">' + acc.platform_name + '</span>';
    accountList.appendChild(label);
  }
}

function renderRows(rows) {
  state.lastRows = rows;
  $("rowCount").textContent = rows.length;
  const body = $("rowsBody");
  body.innerHTML = "";
  updateSortIndicators();
  updateTotals(rows);
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="12" class="empty">暂无数据</td></tr>';
    return;
  }
  for (const row of sortedRows(rows)) {
    const tr = document.createElement("tr");

    // Checkbox cell
    const tdCheck = document.createElement("td");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.dataset.accountId = row.platform_account_id;
    cb.dataset.platformName = row.platform_name;
    cb.addEventListener("change", updateMergeButton);
    tdCheck.appendChild(cb);
    tr.appendChild(tdCheck);

    const cells = [
      row.metric_date,
      row.platform_name,
      row.platform_account_name,
      row.platform_account_id,
      row.fans,
      row.play,
      row.like,
      row.comment,
      row.collect,
      row.publish_count,
      row.login_status,
    ];
    for (const [index, value] of cells.entries()) {
      const td = document.createElement("td");
      if (index >= 4 && index <= 9) td.classList.add("numeric");
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
  await loadScheduleState();
  window._scheduleTimer = setInterval(loadScheduleState, 30000);
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

async function loadScheduleState() {
  const data = await getJson("/api/schedule");
  $("scheduleEnabled").checked = data.enabled || false;
  $("scheduleInterval").value = data.intervalMinutes || 360;
  $("scheduleMode").value = data.mode || "latest";
  let msg = data.enabled
    ? "已启用，间隔 " + (data.intervalMinutes / 60) + " 小时"
    : "未启用";
  if (data.nextRun) {
    const d = new Date(data.nextRun * 1000);
    msg += "，下次执行: " + d.toLocaleString("zh-CN");
  }
  if (data.lastRun) {
    msg += "，上次: " + data.lastRun;
  }
  $("scheduleMessage").textContent = msg;
}

async function saveSchedule() {
  const body = {
    enabled: $("scheduleEnabled").checked,
    intervalMinutes: parseInt($("scheduleInterval").value, 10),
    mode: $("scheduleMode").value,
  };
  await getJson("/api/schedule", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await loadScheduleState();
}


function bindEvents() {
  $("singleMode").addEventListener("click", () => setMode("single"));
  $("rangeMode").addEventListener("click", () => setMode("range"));
  $("queryButton").addEventListener("click", () => queryRows().catch((err) => alert(err.message)));
  $("csvButton").addEventListener("click", downloadCsv);
  $("settingsButton").addEventListener("click", () => openSettings().catch((err) => ($("settingsMessage").textContent = String(err))));
  $("settingsDialog").addEventListener("close", () => {
    if (window._scheduleTimer) { clearInterval(window._scheduleTimer); window._scheduleTimer = null; }
  });
  $("saveSettings").addEventListener("click", () => saveSettings().catch((err) => ($("settingsMessage").textContent = String(err))));
  $("clearSettings").addEventListener("click", () => clearSettings().catch((err) => ($("settingsMessage").textContent = String(err))));
  $("saveSchedule").addEventListener("click", () => saveSchedule().catch((err) => ($("scheduleMessage").textContent = String(err))));
  $("refreshAccounts").addEventListener("click", () => refreshAccounts().catch((err) => alert(err.message)));
  $("fetchRecent").addEventListener("click", () => startFetch("recent"));
  $("fetchFull").addEventListener("click", () => startFetch("full"));
  // Platform filter toggle
  $("platformFilterBtn").addEventListener("click", (e) => {
    e.stopPropagation();
    $("platformDropdown").classList.toggle("hidden");
  });
  $("selectAllPlatforms").addEventListener("click", () => {
    document.querySelectorAll("#platformList input[type=\"checkbox\"]").forEach(cb => { cb.checked = true; cb.dispatchEvent(new Event("change", {bubbles: true})); });
  });
  $("clearAllPlatforms").addEventListener("click", () => {
    document.querySelectorAll("#platformList input[type=\"checkbox\"]").forEach(cb => { cb.checked = false; cb.dispatchEvent(new Event("change", {bubbles: true})); });
  });
  $("platformList").addEventListener("change", () => {
    const checked = [...document.querySelectorAll("#platformList input[type=\"checkbox\"]:checked")];
    const btn = $("platformFilterBtn").querySelector("span");
    btn.textContent = checked.length ? "已选 " + checked.length + " 个" : "全部平台";
  });

  // Account filter toggle
  $("accountFilterBtn").addEventListener("click", (e) => {
    e.stopPropagation();
    $("accountDropdown").classList.toggle("hidden");
  });
  document.addEventListener("click", (e) => {
    if (!$("platformFilter").contains(e.target)) $("platformDropdown").classList.add("hidden");
    if (!$("accountFilter").contains(e.target)) $("accountDropdown").classList.add("hidden");
  });
  $("selectAllAccounts").addEventListener("click", () => {
    document.querySelectorAll("#accountList input[type=\"checkbox\"]").forEach(cb => { cb.checked = true; cb.dispatchEvent(new Event("change", {bubbles: true})); });
  });
  $("clearAllAccounts").addEventListener("click", () => {
    document.querySelectorAll("#accountList input[type=\"checkbox\"]").forEach(cb => { cb.checked = false; cb.dispatchEvent(new Event("change", {bubbles: true})); });
  });
  // Update trigger text on checkbox change
  $("accountList").addEventListener("change", () => {
    const checked = [...document.querySelectorAll("#accountList input[type=\"checkbox\"]:checked")];
    const btn = $("accountFilterBtn").querySelector("span");
    btn.textContent = checked.length ? "已选 " + checked.length + " 个" : "全部账号";
  });
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

function updateMergeButton() {
  const checked = [...document.querySelectorAll("#rowsBody input[type=checkbox]:checked")];
  const ids = [...new Set(checked.map(cb => cb.dataset.accountId))];
  const btn = $("mergeBtn");
  if (ids.length === 2) {
    btn.classList.remove("hidden");
  } else {
    btn.classList.add("hidden");
  }
}

$("selectAllCheckbox").addEventListener("change", function () {
  const checked = this.checked;
  document.querySelectorAll("#rowsBody input[type=checkbox]").forEach(cb => {
    cb.checked = checked;
  });
  updateMergeButton();
});

$("mergeBtn").addEventListener("click", () => {
  const checked = [...document.querySelectorAll("#rowsBody input[type=checkbox]:checked")];
  const unique = [];
  const seen = new Set();
  for (const cb of checked) {
    const id = cb.dataset.accountId;
    if (!seen.has(id)) {
      seen.add(id);
      unique.push({ id, platform: cb.dataset.platformName });
    }
  }
  if (unique.length !== 2) return;
  if (unique[0].platform !== unique[1].platform) {
    alert("两个账号不在同一平台，无法合并。\n平台1: " + unique[0].platform + "\n平台2: " + unique[1].platform);
    return;
  }
  startMerge(unique[0].id, unique[1].id);
});

async function startMerge(idA, idB) {
  const dialog = $("mergeDialog");
  const content = $("mergeContent");
  content.innerHTML = "<p>正在查询账号详情...</p>";
  dialog.showModal();

  let detailA = null, detailB = null;
  try { detailA = await getJson("/api/account-detail?platformAccountId=" + idA); } catch (e) {}
  try { detailB = await getJson("/api/account-detail?platformAccountId=" + idB); } catch (e) {}

  const validA = detailA && detailA.platformAccountName;
  const validB = detailB && detailB.platformAccountName;

  content.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px">
      <div style="border:1px solid var(--line);border-radius:6px;padding:12px;${!validA ? 'opacity:0.4' : ''}">
        <div style="color:var(--muted);font-size:11px;margin-bottom:4px">账号 A</div>
        <div style="font-weight:650">${detailA?.platformAccountName || '不存在'}</div>
        <div style="font-size:12px;color:var(--muted)">${detailA?.platformName || '-'}</div>
        <div style="font-size:11px;word-break:break-all;color:var(--muted);margin-top:4px">${idA}</div>
        ${!validA ? '<div style="color:#dc2626;font-size:12px;margin-top:4px">⚠ 该账号已失效</div>' : ''}
      </div>
      <div style="border:1px solid var(--line);border-radius:6px;padding:12px;${!validB ? 'opacity:0.4' : ''}">
        <div style="color:var(--muted);font-size:11px;margin-bottom:4px">账号 B</div>
        <div style="font-weight:650">${detailB?.platformAccountName || '不存在'}</div>
        <div style="font-size:12px;color:var(--muted)">${detailB?.platformName || '-'}</div>
        <div style="font-size:11px;word-break:break-all;color:var(--muted);margin-top:4px">${idB}</div>
        ${!validB ? '<div style="color:#dc2626;font-size:12px;margin-top:4px">⚠ 该账号已失效</div>' : ''}
      </div>
    </div>
    <div style="margin-bottom:10px">
      <label style="font-size:13px;font-weight:500">将数据合并到：</label>
      <select id="mergeTarget" style="width:100%;margin-top:4px">
        ${validB ? '<option value="' + idB + '|' + (detailB.platformAccountName || '') + '">账号 B: ' + (detailB.platformAccountName || '') + ' (' + idB + ')</option>' : ''}
        ${validA ? '<option value="' + idA + '|' + (detailA.platformAccountName || '') + '">账号 A: ' + (detailA.platformAccountName || '') + ' (' + idA + ')</option>' : ''}
      </select>
    </div>
    <div style="margin-bottom:10px">
      <label style="font-size:13px;font-weight:500">目标账号名称：</label>
      <input id="mergeNewName" type="text" style="width:100%;margin-top:4px" placeholder="输入新的账号名称" />
    </div>
  `;

  if (!validA && !validB) {
    content.innerHTML += '<p style="color:#dc2626">两个账号均已失效，无法合并。</p>';
    $("mergeConfirm").disabled = true;
  } else {
    $("mergeConfirm").disabled = false;
  }
}

$("mergeConfirm").addEventListener("click", async () => {
  const checked = [...document.querySelectorAll("#rowsBody input[type=checkbox]:checked")];
  const ids = [...new Set(checked.map(cb => cb.dataset.accountId))];
  if (ids.length !== 2) return;

  const targetSelect = $("mergeTarget");
  if (!targetSelect) return;
  const [toId, defaultName] = targetSelect.value.split("|");
  const toName = $("mergeNewName").value.trim() || defaultName;
  const fromId = ids.find(id => id !== toId);
  if (!fromId) return;

  try {
    $("mergeConfirm").disabled = true;
    $("mergeConfirm").textContent = "合并中...";
    const data = await getJson("/api/merge-accounts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fromId, toId, toName }),
    });
    $("mergeDialog").close();
    alert("合并完成！更新了 " + data.overviewRowsUpdated + " 条概览数据。");
    await loadStatus();
    await queryRows();
  } catch (err) {
    alert("合并失败: " + err.message);
  } finally {
    $("mergeConfirm").disabled = false;
    $("mergeConfirm").textContent = "确认合并";
  }
});

$("mergeDialog").addEventListener("close", () => {
  $("mergeConfirm").disabled = false;
  $("mergeConfirm").textContent = "确认合并";
});
