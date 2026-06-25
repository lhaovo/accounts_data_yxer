async function getJson(url, options) {
  const res = await fetch(url, options);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error?.message || `HTTP ${res.status}`);
  }
  if (data?.ok === false) {
    throw new Error(data.message || data.error?.message || "请求失败");
  }
  return data;
}

function postJson(url, body) {
  return getJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const api = {
  status: () => getJson("/api/status"),
  settings: () => getJson("/api/settings"),
  saveSettings: (body) => postJson("/api/settings", body),
  schedule: () => getJson("/api/schedule"),
  saveSchedule: (body) => postJson("/api/schedule", body),
  metrics: (query) => getJson(`/api/metrics?${query.toString()}`),
  refreshAccounts: (accountIds) => postJson("/api/refresh-accounts", { accountIds }),
  startFetch: (mode) => postJson("/api/fetch", { mode }),
  fetchStatus: () => getJson("/api/fetch-status"),
  accountDetail: (platformAccountId) => getJson(`/api/account-detail?platformAccountId=${encodeURIComponent(platformAccountId)}`),
  mergeAccounts: (body) => postJson("/api/merge-accounts", body),
};
