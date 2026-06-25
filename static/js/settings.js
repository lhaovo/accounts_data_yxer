import { api } from "./api.js";
import { $ } from "./dom.js";

let scheduleTimer = null;

export async function loadSettingsState() {
  const data = await api.settings();
  $("settingsMessage").textContent = data.hasApiKey
    ? "后端已保存 API Key。输入新值并保存可覆盖。"
    : "后端尚未保存 API Key。";
  return data;
}

export async function loadScheduleState() {
  const data = await api.schedule();
  $("scheduleEnabled").checked = data.enabled || false;
  $("scheduleInterval").value = data.intervalMinutes || 360;
  $("scheduleMode").value = data.mode || "latest";
  $("schedulePreRefresh").checked = data.preRefresh || false;

  let msg = data.enabled
    ? `已启用，间隔 ${data.intervalMinutes / 60} 小时`
    : "未启用";
  if (data.enabled && data.preRefresh) {
    msg += "，同步前刷新账号";
  }
  if (data.nextRun) {
    msg += "，下次执行 " + new Date(data.nextRun * 1000).toLocaleString("zh-CN");
  }
  if (data.lastRun) {
    msg += "，上次 " + data.lastRun;
  }
  $("scheduleMessage").textContent = msg;
}

export async function openSettings() {
  $("settingsApiKeyInput").value = "";
  $("settingsMessage").textContent = "正在读取设置状态...";
  $("settingsDialog").showModal();
  await loadSettingsState();
  await loadScheduleState();
  scheduleTimer = setInterval(loadScheduleState, 30000);
}

export function stopScheduleTimer() {
  if (!scheduleTimer) return;
  clearInterval(scheduleTimer);
  scheduleTimer = null;
}

export async function saveSettings() {
  const value = $("settingsApiKeyInput").value.trim();
  if (!value) {
    $("settingsMessage").textContent = "请输入新的蚁小二 API Key。";
    return;
  }

  await api.saveSettings({ apiKey: value });
  $("settingsApiKeyInput").value = "";
  $("settingsMessage").textContent = "已保存到后端。";
}

export async function clearSettings() {
  await api.saveSettings({ clear: true });
  $("settingsApiKeyInput").value = "";
  $("settingsMessage").textContent = "后端保存的 API Key 已清除。";
}

export async function saveSchedule() {
  await api.saveSchedule({
    enabled: $("scheduleEnabled").checked,
    intervalMinutes: parseInt($("scheduleInterval").value, 10),
    mode: $("scheduleMode").value,
    preRefresh: $("schedulePreRefresh").checked,
  });
  await loadScheduleState();
}
