# 蚁小二 API 文档

Base URL: `https://www.yixiaoer.cn/api`

鉴权方式：请求头 `Authorization: {API_KEY}`

---

## 1. 增量概览（新）

```
GET /overview/incremental
```

按平台 + 时间范围获取账号概览增量数据，返回聚合后的汇总结果。

**参数（均为可选）：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `platform` | string | 否 | 平台名称，如 `小红书`、`抖音`。不填返回全部平台 |
| `startTime` | number | 否 | 开始时间，毫秒时间戳（东八区） |
| `endTime` | number | 否 | 结束时间，毫秒时间戳（东八区，含） |

- 不填时间参数：默认返回**昨天**的单日数据
- 不填 platform：返回全部平台

**调用示例：**

```
GET /overview/incremental?platform=小红书&startTime=1781539200000&endTime=1782143999999
```

**响应结构：**

```json
{
  "summary": {
    "accountCount": 37,
    "visibleAccountCount": 45,
    "platformAccountCounts": { "头条号": 3, "抖音": 8, "快手": 9, ... },
    "publishedAccountCount": 13,
    "publishTotal": 87,
    "fansTotal": 346,
    "playTotal": 421436,
    "commentsTotal": 1128,
    "likesTotal": 1047,
    "favoritesTotal": 513
  },
  "trends": [
    { "date": "2026-06-16", "publishTotal": 46, "fansTotal": 98, ... }
  ],
  "accounts": [
    {
      "platformAccountId": "69d472fe832c2e0bf3ea872e",
      "platformName": "头条号",
      "platformAccountName": "千威能量站",
      "status": 1,
      "updatedAt": 1782263321802,
      "overviewUpdatedAt": 1782263321796,
      "publishTotal": 0,
      "fansTotal": 1,
      "playTotal": 296,
      "commentsTotal": 0,
      "likesTotal": 9,
      "favoritesTotal": 0
    }
  ]
}
```

### 与 `/platform-accounts/overviews-v2` 的区别

| | `/overview/incremental` | `/platform-accounts/overviews-v2` |
|---|---|---|
| 数据粒度 | 已聚合的汇总值 | 逐指标的原始时间点 |
| 平台过滤 | 可选，支持全平台一次查 | 按 platform 逐个遍历 |
| 时间过滤 | 支持 startTime/endTime | 无原生时间过滤 |
| 趋势 | 自带 trends（按天） | 无 |
| 汇总 | 自带 summary | 无 |

---

## 2. 单账号概览刷新

```
PUT /platform-accounts/{platformAccountId}/overview
```

触发指定账号从源平台重新拉取概览数据。**异步操作**，每次调用有 2 分钟冷却。

**响应：**

```json
{
  "statusCode": 0,
  "data": {
    "platformAccountId": "69d472fe832c2e0bf3ea872e",
    "overviewData": {
      "value": null,
      "updateTime": 1782282303377
    },
    "updateTime": 1782282303377,
    "refreshDisabledUntil": 1782282423377,
    "refreshStatus": "syncing"
  }
}
```

| 字段 | 说明 |
|------|------|
| `refreshStatus` | `"syncing"` 表示正在后台同步 |
| `refreshDisabledUntil` | 冷却结束时间（毫秒时间戳），距上次刷新整整 2 分钟 |
| `overviewData.value` | 刷新完成前为 `null`，完成后返回实际数据 |

---

## 3. 已使用的接口（参考）

| 接口 | 方法 | 用途 |
|------|------|------|
| `/v2/platform/accounts` | GET | 获取账号列表 |
| `/platform-accounts/overviews-v2` | GET | 按平台分页获取账号概览原始数据 |
| `/contents/overviews` | GET | 获取内容发布数据，统计发布量 |
