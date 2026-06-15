# 社媒账号数据汇总 — API 文档

Base URL: `http://127.0.0.1:8787`

## 通用说明

- 所有接口返回 JSON，`Content-Type: application/json; charset=utf-8`
- 成功时 HTTP 状态码 `200`
- 错误时返回 `{"error": {"message": "...", "detail": "..."}}`
- CSV 导出接口返回 `text/csv; charset=utf-8`

---

## 1. 数据库状态

```
GET /api/status
```

**响应示例：**

```json
{
  "dbPath": "/app/data/yixiaoer_daily_accounts.sqlite",
  "dbExists": true,
  "scriptsDir": "/app/scripts",
  "scriptsDirExists": true,
  "dateRange": {
    "minDate": "2026-04-06",
    "maxDate": "2026-06-15"
  },
  "platforms": [
    {"name": "抖音", "accountCount": 5},
    {"name": "快手", "accountCount": 5}
  ],
  "accountCount": 22,
  "metricCount": 7360
}
```

---

## 2. 查询指标

```
GET /api/metrics
```

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `date` | string | 单日模式 | 日期，格式 `YYYY-MM-DD` |
| `start` | string | 范围模式 | 开始日期 |
| `end` | string | 范围模式 | 结束日期 |
| `platform` | string | 否 | 平台名称，如 `抖音`、`快手` |
| `includeEmpty` | string | 否 | `"1"` 时包含无数据的账号，补 `-` |

> `date` 和 `start`/`end` 二选一。`start` 须 `<= end`。

**响应示例：**

```json
{
  "rows": [
    {
      "metric_date": "2026-06-15",
      "platform_name": "抖音",
      "platform_account_name": "千威能量站",
      "platform_account_id": "xxx",
      "login_status": "正常",
      "fans": "12",
      "play": "1234",
      "exposure": "5678",
      "like": "90",
      "comment": "5",
      "share": "3",
      "collect": "2",
      "publish_count": "1"
    }
  ],
  "rawRows": [{...}],
  "count": 1,
  "columns": ["metric_date", "platform_name", ...]
}
```

- `rows` — 格式化后的数据，数值为空显示 `"-"`
- `rawRows` — 原始数据，数值为空显示 `null`
- `fans` 列显示的是净增粉丝（`net_fans`），无增量数据时显示 `"-"`

---

## 3. 导出 CSV

```
GET /api/export.csv
```

参数同 `/api/metrics`。返回 `Content-Disposition: attachment`，浏览器会触发下载。

**示例：**

```bash
curl "http://127.0.0.1:8787/api/export.csv?start=2026-06-01&end=2026-06-15" -o data.csv
```

---

## 4. 设置（API Key）

### 查询配置

```
GET /api/settings
```

```json
{
  "hasApiKey": true,
  "usesEnvironmentApiKey": true,
  "hasSettingsKey": false
}
```

- `hasApiKey` — 当前是否有可用 Key
- `usesEnvironmentApiKey` — 是否来自环境变量 `YIXIAOER_API_KEY`
- `hasSettingsKey` — 是否通过页面保存过 Key

### 保存 Key

```
POST /api/settings
Content-Type: application/json

{"apiKey": "your_api_key_here"}
```

### 清除 Key

```
POST /api/settings
Content-Type: application/json

{"clear": true}
```

**优先级：** 环境变量 `YIXIAOER_API_KEY` > `config/settings.json`。通过页面保存的 Key 在环境变量缺失时生效。

---

## 5. 自动同步

### 查询配置

```
GET /api/schedule
```

```json
{
  "enabled": true,
  "intervalMinutes": 360,
  "mode": "latest",
  "nextRun": 1718400000.0,
  "lastRun": "2026-06-15T10:00:00+08:00",
  "lastResult": {"ok": true, "returnCode": 0}
}
```

- `enabled` — 是否启用
- `intervalMinutes` — 间隔（分钟），最小 5
- `mode` — `"latest"` 最近一天 / `"full"` 全量
- `nextRun` — 下次运行时间戳（Unix 秒）
- `lastRun` — 上次运行 ISO 时间
- `lastResult` — 上次运行结果

### 更新配置

```
POST /api/schedule
Content-Type: application/json

{
  "enabled": true,
  "intervalMinutes": 360,
  "mode": "latest"
}
```

参数均必填。更新后立即生效，旧的定时器会被取消。

---

## 6. 触发刷新

```
POST /api/refresh
Content-Type: application/json

{"mode": "latest"}
```

- `mode`: `"latest"` 增量刷新 / `"full"` 全量刷新

**响应（成功）：**

```json
{
  "ok": true,
  "mode": "latest",
  "returnCode": 0,
  "stdout": "...",
  "stderr": ""
}
```

**响应（脚本失败，HTTP 500）：**

```json
{
  "ok": false,
  "mode": "latest",
  "returnCode": 1,
  "stdout": "...",
  "stderr": "Error: ..."
}
```

调用前需确保后端已配置 API Key（环境变量或 settings.json）。

---

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `YIXIAOER_API_KEY` | 蚁小二 API Key | - |
| `YIXIAOER_DB_PATH` | SQLite 路径 | `./data/yixiaoer_daily_accounts.sqlite` |
| `YIXIAOER_SCRIPTS_DIR` | 采集脚本目录 | `./scripts` |