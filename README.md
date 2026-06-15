# 社媒账号数据汇总

本地 Web 服务，用于查询 SQLite 中的社媒账号数据、导出 CSV，并可触发数据刷新。

数据来源：[蚁小二](https://www.yixiaoer.cn) API，支持抖音、快手、小红书、视频号、微信公众号、头条号、新浪微博。

## 快速启动

```bash
# 1. 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的蚁小二 API Key

# 2. 启动
docker compose up -d
```

打开 http://localhost:8787

## 本地开发

```powershell
$env:YIXIAOER_API_KEY = "你的 API Key"
python app.py --host 127.0.0.1 --port 8787
```

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `YIXIAOER_API_KEY` | 蚁小二 API Key（必需） | - |
| `YIXIAOER_DB_PATH` | SQLite 数据库路径 | `./data/yixiaoer_daily_accounts.sqlite` |
| `YIXIAOER_SCRIPTS_DIR` | 采集脚本目录 | `./scripts` |

## 目录结构

```
├── app.py                  # Web 服务主程序
├── Dockerfile
├── docker-compose.yml
├── .env.example            # 环境变量模板
├── config/
│   └── settings.json       # 页面保存的 API Key（gitignore）
├── data/
│   └── yixiaoer_daily_accounts.sqlite   # SQLite 数据库（gitignore）
├── scripts/
│   ├── collect_daily_accounts.py        # 全量采集
│   └── collect_latest_day.py            # 增量采集
└── static/
    ├── index.html
    ├── app.js
    └── styles.css
```

## 页面功能

- 单日 / 日期范围查询，按平台过滤
- 数据表格支持排序，含汇总行
- 粉丝列显示每日净增粉丝
- CSV 导出
- 刷新最近一天 / 全量刷新
- 页面内配置 API Key（写入 config/settings.json，环境变量优先）

## 数据刷新

点击页面右上角"刷新最近一天"或"全量刷新"按钮。刷新会调用 `scripts/` 下的采集脚本从蚁小二 API 拉取最新数据。

也可以手动执行：

```powershell
$env:YIXIAOER_API_KEY = "你的 API Key"
python scripts/collect_latest_day.py
```