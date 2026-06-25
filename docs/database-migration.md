# 数据库与迁移说明

本文档记录当前数据库表职责、旧接口数据迁移方式，以及迁移后应用读写口径。

## 当前数据口径

当前页面查询、CSV 导出、账号合并、手动同步、自动同步均以 `daily_account_overviews` 为业务表。

`daily_account_metrics` 是旧接口时期的数据表。它保留在数据库中用于审计和一次性迁移，不再参与页面查询或同步写入。

## 主要表结构

### accounts

账号主表，按 `platform_account_id` 唯一。

关键字段：

- `platform_account_id`：账号 ID，主键
- `platform_name`：平台
- `platform_account_name`：账号名称
- `status`：登录状态

### daily_account_overviews

当前业务表。新接口 `/api/overview/incremental` 返回的每日账号概览写入此表。

唯一约束：

- `(metric_date, platform_account_id)`

关键字段：

- `metric_date`
- `platform_name`
- `platform_account_name`
- `platform_account_id`
- `login_status`
- `fans`
- `play`
- `like_count`
- `comment_count`
- `collect_count`
- `publish_count`
- `collected_at`

### daily_account_metrics

旧接口表。旧表按账号、日期、内容类型和指标 key 存多条指标行。

主键：

- `(metric_date, platform_account_id, content_type, metric_key)`

此表不删除，但迁移后不再作为业务查询来源。

## 迁移脚本

脚本路径：

```powershell
python scripts/migrate_metrics_to_overviews.py --db data/yixiaoer_daily_accounts.sqlite
```

默认是 dry-run，不写数据库。它会：

1. 打印 `daily_account_metrics` 和 `daily_account_overviews` 的结构。
2. 复用后端旧表解析逻辑，把 `daily_account_metrics` 汇总成每日账号概览行。
3. 统计将要写入 `daily_account_overviews` 的行数。
4. 默认保留新表已有 `(metric_date, platform_account_id)` 数据，不覆盖。

实际迁移命令：

```powershell
python scripts/migrate_metrics_to_overviews.py --db data/yixiaoer_daily_accounts.sqlite --apply
```

如需覆盖新表已有行，可加：

```powershell
--overwrite
```

默认不建议覆盖，因为新接口数据优先级更高。

## 已执行迁移结果

迁移前已创建数据库备份：

```text
data/yixiaoer_daily_accounts.before-migration-20260625-103319.sqlite
```

本次迁移结果：

```text
legacy metric rows scanned: 14133
legacy daily rows summarized: 1668
rows written: 1581
rows skipped because overview already exists: 87
overwrite existing rows: False
```

迁移后验证：

```text
daily_account_overviews total: 1669
migrated rows: 1581
duplicate (metric_date, platform_account_id): 0
```

## 迁移后应用行为

### 查询

`/api/metrics` 只读取 `daily_account_overviews`。

范围查询勾选“合并账号”时，会对 overview 查询结果按 `platform_account_id` 聚合，避免同一账号多天结果拆成多行。

### CSV 导出

CSV 导出与页面查询共用同一查询入口，也只读取 `daily_account_overviews`。

### 账号合并

账号合并只更新：

- `daily_account_overviews`
- `accounts`

旧表 `daily_account_metrics` 不再更新。

### 同步

手动“三天数据 / 全量数据”和自动同步均调用新接口 `/api/overview/incremental`，并写入 `daily_account_overviews`。

自动同步的“同步前刷新账号”选项会：

1. 调用账号刷新逻辑。
2. 等待 60 秒。
3. 执行三天数据或全量同步。

当前“全量”同步实际取最近 30 天；“三天数据”同步取最近 3 天。
