import { $, $all } from "./dom.js";
import { numericColumns, state, totalTargets } from "./state.js";

function parseNumber(value) {
  if (value === null || value === undefined || value === "-") return null;
  const number = Number(String(value).replace(/,/g, ""));
  return Number.isFinite(number) ? number : null;
}

function formatNumber(value) {
  if (value === null || value === undefined) return "-";
  return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
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
  $all("th.sortable").forEach((th) => {
    const active = th.dataset.sort === state.sortKey;
    th.classList.toggle("active", active);
    th.dataset.dir = active ? state.sortDir : "";
  });
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

function appendCell(tr, value, numeric = false) {
  const td = document.createElement("td");
  if (numeric) td.classList.add("numeric");
  td.textContent = value ?? "-";
  tr.appendChild(td);
}

export function renderRows(rows, onSelectionChange) {
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
    const tdCheck = document.createElement("td");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.dataset.accountId = row.platform_account_id;
    cb.dataset.platformName = row.platform_name;
    cb.addEventListener("change", onSelectionChange);
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
      appendCell(tr, value, index >= 4 && index <= 9);
    }
    body.appendChild(tr);
  }
}

export function bindSortHeaders(onSort) {
  $all("th.sortable").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (state.sortKey === key) {
        state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
      } else {
        state.sortKey = key;
        state.sortDir = numericColumns.has(key) ? "desc" : "asc";
      }
      onSort(state.lastRows);
    });
  });
}
