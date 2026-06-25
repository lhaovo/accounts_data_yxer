import { api } from "./api.js";
import { $, setButtonDisabled } from "./dom.js";
import { checkedAccountIds } from "./filters.js";

function setFetchProgress(message, visible = true) {
  const el = $("fetchProgress");
  el.textContent = message || "";
  el.classList.toggle("hidden", !visible);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function refreshAccounts(reload) {
  $("refreshAccounts").disabled = true;
  setFetchProgress("正在刷新账号...");
  try {
    const data = await api.refreshAccounts(checkedAccountIds());
    setFetchProgress(`已触发 ${data.triggered || 0} 个账号，跳过 ${data.skipped || 0} 个，失败 ${data.errors || 0} 个`);
    await reload();
  } finally {
    $("refreshAccounts").disabled = false;
    setTimeout(() => setFetchProgress("", false), 5000);
  }
}

async function pollFetchStatus(reload) {
  while (true) {
    const status = await api.fetchStatus();
    if (!status.running) {
      if (status.error) {
        setFetchProgress(`同步失败：${status.error}`);
        return;
      }

      const result = status.result || {};
      setFetchProgress(`同步完成：${result.daysFetched || 0} 天，${result.accountsWritten || 0} 条`);
      await reload();
      setTimeout(() => setFetchProgress("", false), 5000);
      return;
    }

    const total = status.total || 0;
    const current = status.current || 0;
    const dateText = status.currentDate ? ` ${status.currentDate}` : "";
    setFetchProgress(total ? `同步中 ${current}/${total}${dateText}` : "同步中...");
    await sleep(1500);
  }
}

export async function startFetch(mode, reload) {
  setButtonDisabled(["fetchRecent", "fetchFull"], true);
  setFetchProgress(mode === "full" ? "正在启动全量同步..." : "正在启动三天同步...");
  try {
    await api.startFetch(mode);
    await pollFetchStatus(reload);
  } catch (err) {
    setFetchProgress(err.message);
    throw err;
  } finally {
    setButtonDisabled(["fetchRecent", "fetchFull"], false);
  }
}
