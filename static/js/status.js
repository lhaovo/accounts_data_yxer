import { api } from "./api.js";
import { $ } from "./dom.js";
import { populateFilters } from "./filters.js";
import { state } from "./state.js";

export async function loadStatus() {
  const data = await api.status();
  state.status = data;

  $("statusText").textContent = data.dbExists
    ? `数据库：${data.dbPath}`
    : `未找到数据库：${data.dbPath}`;
  $("accountCount").textContent = data.accountCount ?? "-";
  $("metricCount").textContent = data.metricCount ?? "-";

  const minDate = data.dateRange?.minDate || data.overviewDateRange?.minDate || "";
  const maxDate = data.dateRange?.maxDate || data.overviewDateRange?.maxDate || "";
  $("dateRange").textContent = minDate && maxDate ? `${minDate} 至 ${maxDate}` : "-";

  populateFilters(data);
}
