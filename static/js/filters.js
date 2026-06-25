import { $, $all, checkedValues, on, setHidden } from "./dom.js";
import { state } from "./state.js";

function todayLike(value) {
  return value || new Date().toISOString().slice(0, 10);
}

function renderFilterList(id, items, createLabel) {
  const list = $(id);
  list.innerHTML = "";
  for (const item of items || []) {
    list.appendChild(createLabel(item));
  }
}

function makePlatformLabel(item) {
  const label = document.createElement("label");
  label.innerHTML = '<input type="checkbox" value="' + item.name + '" /> ' + item.name + ' <span style="color:var(--muted);font-size:11px">' + item.accountCount + '</span>';
  return label;
}

function makeAccountLabel(account) {
  const label = document.createElement("label");
  label.innerHTML = '<input type="checkbox" value="' + account.platform_account_id + '" /> ' + account.platform_account_name + ' <span style="color:var(--muted);font-size:11px">' + account.platform_name + '</span>';
  return label;
}

function updateTriggerText(listSelector, buttonId, emptyText) {
  const checked = $all(`${listSelector} input[type="checkbox"]:checked`);
  $(buttonId).querySelector("span").textContent = checked.length ? `已选 ${checked.length} 个` : emptyText;
}

function setAllChecked(listSelector, checked) {
  $all(`${listSelector} input[type="checkbox"]`).forEach((cb) => {
    cb.checked = checked;
    cb.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

export function setMode(mode) {
  state.mode = mode;
  $("singleMode").classList.toggle("active", mode === "single");
  $("rangeMode").classList.toggle("active", mode === "range");
  $all(".single-date").forEach((el) => setHidden(el, mode !== "single"));
  $all(".range-date").forEach((el) => setHidden(el, mode !== "range"));
  $all(".merge-only").forEach((el) => setHidden(el, mode !== "range"));
}

export function buildQuery() {
  const params = new URLSearchParams();
  if (state.mode === "single") {
    params.set("date", $("dateInput").value);
  } else {
    params.set("start", $("startInput").value);
    params.set("end", $("endInput").value);
  }

  const platforms = checkedValues("#platformList input[type=\"checkbox\"]");
  if (platforms.length) params.set("platforms", platforms.join(","));
  if ($("includeEmptyInput").checked) params.set("includeEmpty", "1");
  if (state.mode === "range" && $("mergeInput").checked) params.set("merge", "1");

  const accountIds = checkedAccountIds();
  if (accountIds.length) params.set("accountIds", accountIds.join(","));
  return params;
}

export function checkedAccountIds() {
  return checkedValues("#accountList input[type=\"checkbox\"]");
}

export function populateFilters(data) {
  renderFilterList("platformList", data.platforms, makePlatformLabel);
  renderFilterList("accountList", data.accounts, makeAccountLabel);

  const maxDate = data.dateRange?.maxDate || "";
  const minDate = data.dateRange?.minDate || "";
  const defaultDate = maxDate || new Date().toISOString().slice(0, 10);
  $("dateInput").value = todayLike(defaultDate);
  $("startInput").value = todayLike(minDate || defaultDate);
  $("endInput").value = todayLike(defaultDate);

  updateTriggerText("#platformList", "platformFilterBtn", "全部平台");
  updateTriggerText("#accountList", "accountFilterBtn", "全部账号");
}

export function bindFilterEvents() {
  on("singleMode", "click", () => setMode("single"));
  on("rangeMode", "click", () => setMode("range"));

  on("platformFilterBtn", "click", (event) => {
    event.stopPropagation();
    $("platformDropdown").classList.toggle("hidden");
  });
  on("selectAllPlatforms", "click", () => setAllChecked("#platformList", true));
  on("clearAllPlatforms", "click", () => setAllChecked("#platformList", false));
  on("platformList", "change", () => updateTriggerText("#platformList", "platformFilterBtn", "全部平台"));

  on("accountFilterBtn", "click", (event) => {
    event.stopPropagation();
    $("accountDropdown").classList.toggle("hidden");
  });
  on("selectAllAccounts", "click", () => setAllChecked("#accountList", true));
  on("clearAllAccounts", "click", () => setAllChecked("#accountList", false));
  on("accountList", "change", () => updateTriggerText("#accountList", "accountFilterBtn", "全部账号"));

  document.addEventListener("click", (event) => {
    if (!$("platformFilter").contains(event.target)) $("platformDropdown").classList.add("hidden");
    if (!$("accountFilter").contains(event.target)) $("accountDropdown").classList.add("hidden");
  });
}
