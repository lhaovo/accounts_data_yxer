import { api } from "./api.js";
import { $, setButtonDisabled } from "./dom.js";
import { checkedAccountIds } from "./filters.js";

const TASK_BUTTON_IDS = ["refreshAccounts", "fetchRecent", "fetchFull", "openFullUpdateConfirm"];

function setFetchProgress(message, visible = true) {
  const el = $("fetchProgress");
  el.textContent = message || "";
  el.classList.toggle("hidden", !visible);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function refreshAccounts(reload) {
  setButtonDisabled(TASK_BUTTON_IDS, true);
  setFetchProgress("正在启动账号刷新...");
  try {
    await api.refreshAccounts(checkedAccountIds());
    await pollFetchStatus(reload);
  } catch (err) {
    setFetchProgress(err.message);
    throw err;
  } finally {
    setButtonDisabled(TASK_BUTTON_IDS, false);
  }
}

async function pollFetchStatus(reload) {
  while (true) {
    const status = await api.fetchStatus();
    if (!status.running) {
      if (status.error) {
        setFetchProgress(`任务失败：${status.error}`);
        return;
      }

      const result = status.result || {};
      if (status.mode === "refresh-accounts") {
        setFetchProgress(`账号刷新完成：触发 ${result.triggered || 0} 个，跳过 ${result.skipped || 0} 个，失败 ${result.errors || 0} 个`);
      } else {
        setFetchProgress(`同步完成：${result.daysFetched || 0} 天，${result.accountsWritten || 0} 条`);
      }
      await reload();
      setTimeout(() => setFetchProgress("", false), 5000);
      return;
    }

    const total = status.total || 0;
    const current = status.current || 0;
    const currentText = status.currentDate ? ` ${status.currentDate}` : "";
    const label = status.mode === "refresh-accounts" ? "刷新账号中" : "同步中";
    setFetchProgress(total ? `${label} ${current}/${total}${currentText}` : `${label}...`);
    await sleep(1500);
  }
}

export async function startFetch(mode, reload) {
  setButtonDisabled(TASK_BUTTON_IDS, true);
  const label = mode === "all" ? "全量数据" : mode === "full" ? "一个月数据" : "三天数据";
  setFetchProgress(`正在启动${label}更新...`);
  try {
    await api.startFetch(mode);
    await pollFetchStatus(reload);
  } catch (err) {
    setFetchProgress(err.message);
    throw err;
  } finally {
    setButtonDisabled(TASK_BUTTON_IDS, false);
  }
}
