import { api } from "./api.js";
import { $, $all, on } from "./dom.js";

let reloadPage = async () => {};

function selectedRowCheckboxes() {
  return $all("#rowsBody input[type=checkbox]:checked");
}

function selectedUniqueAccounts() {
  const unique = [];
  const seen = new Set();
  for (const cb of selectedRowCheckboxes()) {
    const id = cb.dataset.accountId;
    if (!seen.has(id)) {
      seen.add(id);
      unique.push({ id, platform: cb.dataset.platformName });
    }
  }
  return unique;
}

export function updateMergeButton() {
  const ids = [...new Set(selectedRowCheckboxes().map((cb) => cb.dataset.accountId))];
  $("mergeBtn").classList.toggle("hidden", ids.length !== 2);
}

async function startMerge(idA, idB) {
  const dialog = $("mergeDialog");
  const content = $("mergeContent");
  content.innerHTML = "<p>正在查询账号详情...</p>";
  dialog.showModal();

  let detailA = null;
  let detailB = null;
  try { detailA = await api.accountDetail(idA); } catch (err) {}
  try { detailB = await api.accountDetail(idB); } catch (err) {}

  const validA = detailA && detailA.platformAccountName;
  const validB = detailB && detailB.platformAccountName;
  content.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px">
      <div style="border:1px solid var(--line);border-radius:6px;padding:12px;${!validA ? 'opacity:0.4' : ''}">
        <div style="color:var(--muted);font-size:11px;margin-bottom:4px">账号 A</div>
        <div style="font-weight:650">${detailA?.platformAccountName || '不存在'}</div>
        <div style="font-size:12px;color:var(--muted)">${detailA?.platformName || '-'}</div>
        <div style="font-size:11px;word-break:break-all;color:var(--muted);margin-top:4px">${idA}</div>
        ${!validA ? '<div style="color:#dc2626;font-size:12px;margin-top:4px">该账号已失效</div>' : ''}
      </div>
      <div style="border:1px solid var(--line);border-radius:6px;padding:12px;${!validB ? 'opacity:0.4' : ''}">
        <div style="color:var(--muted);font-size:11px;margin-bottom:4px">账号 B</div>
        <div style="font-weight:650">${detailB?.platformAccountName || '不存在'}</div>
        <div style="font-size:12px;color:var(--muted)">${detailB?.platformName || '-'}</div>
        <div style="font-size:11px;word-break:break-all;color:var(--muted);margin-top:4px">${idB}</div>
        ${!validB ? '<div style="color:#dc2626;font-size:12px;margin-top:4px">该账号已失效</div>' : ''}
      </div>
    </div>
    <div style="margin-bottom:10px">
      <label style="font-size:13px;font-weight:500">将数据合并到：</label>
      <select id="mergeTarget" style="width:100%;margin-top:4px">
        ${validB ? '<option value="' + idB + '|' + (detailB.platformAccountName || '') + '">账号 B: ' + (detailB.platformAccountName || '') + ' (' + idB + ')</option>' : ''}
        ${validA ? '<option value="' + idA + '|' + (detailA.platformAccountName || '') + '">账号 A: ' + (detailA.platformAccountName || '') + ' (' + idA + ')</option>' : ''}
      </select>
    </div>
  `;

  if (!validA && !validB) {
    content.innerHTML += '<p style="color:#dc2626">两个账号均已失效，无法合并。</p>';
    $("mergeConfirm").disabled = true;
  } else {
    $("mergeConfirm").disabled = false;
    $("mergeConfirm").textContent = "确认合并";
  }
}

function openSelectedMerge() {
  const unique = selectedUniqueAccounts();
  if (unique.length !== 2) return;

  if (unique[0].platform !== unique[1].platform) {
    alert("两个账号不在同一平台，无法合并。\n平台1: " + unique[0].platform + "\n平台2: " + unique[1].platform);
    return;
  }

  startMerge(unique[0].id, unique[1].id).catch((err) => alert(err.message));
}

async function handleMergeConfirm() {
  const ids = [...new Set(selectedRowCheckboxes().map((cb) => cb.dataset.accountId))];
  if (ids.length !== 2) return;

  const targetSelect = $("mergeTarget");
  if (!targetSelect) return;

  const parts = targetSelect.value.split("|");
  const toId = parts[0];
  const toName = parts.slice(1).join("|");
  const fromId = ids.find((id) => id !== toId);
  if (!fromId) return;

  try {
    $("mergeConfirm").disabled = true;
    $("mergeConfirm").textContent = "合并中...";
    const data = await api.mergeAccounts({ fromId, toId, toName });
    $("mergeDialog").close();
    alert("合并完成！更新了 " + data.overviewRowsUpdated + " 条概览数据。");
    await reloadPage();
  } catch (err) {
    $("mergeContent").innerHTML += '<p style="color:#dc2626;margin-top:8px">合并失败: ' + err.message + '</p>';
    alert("合并失败: " + err.message);
  } finally {
    $("mergeConfirm").disabled = false;
    $("mergeConfirm").textContent = "确认合并";
  }
}

export function bindMergeEvents(options) {
  reloadPage = options.reloadPage;

  on("selectAllCheckbox", "change", function () {
    const checked = this.checked;
    $all("#rowsBody input[type=checkbox]").forEach((cb) => {
      cb.checked = checked;
    });
    updateMergeButton();
  });

  on("mergeBtn", "click", openSelectedMerge);
  on("mergeCancel", "click", () => $("mergeDialog").close());
  on("mergeClose", "click", () => $("mergeDialog").close());
  on("mergeConfirm", "click", () => handleMergeConfirm().catch((err) => alert(err.message)));
  on("mergeDialog", "close", () => {
    $("mergeConfirm").disabled = false;
    $("mergeConfirm").textContent = "确认合并";
  });
}
