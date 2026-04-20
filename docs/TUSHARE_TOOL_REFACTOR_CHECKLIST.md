# Tushare 工具改造清单

> 日期: 2026-01-26
> 范围: `mcp/` 内 tushare-data 工具层
> 依据: `docs/distill-adj/0126_1.md`、`docs/distill-adj/0126_2.md`、`docs/distill-adj/0126_3.md`、`docs/distill-adj/来自 gemini的分析.md`、`docs/distill-adj/来自 gpt的分析.md`

目标: 解决"市场均值/极值不可达、工具幻觉、口径不清、返回体过大、日期不可用"等问题，让主 Agent 能在 1-2 次工具调用内完成核心统计类问题。

**状态: 全部完成 ✅** (2026-01-26)

---

## P0 (必须先做，直接影响可用性)

- [x] P0-1 市场统计聚合工具 ✅
  - 改造点: 新增 `get_market_summary`、`get_market_extremes`、`get_batch_pct_chg`，一次调用返回全市场均值/中位数/分位数/涨跌家数/极值
  - 文件: `mcp/src/tools/market_statistics.py` (新建), `mcp/src/server.py` (注册)
  - 备注: 使用 `daily()` + `daily_basic()` + `trade_cal()` 组合；支持 `market` 过滤 (全部/沪市/深市/创业板/科创板/北交所)；必要时支持 `include_st`/`weight` 参数
  - 验收: 用户问"本年市场均值/极值"可单次返回结构化结果 (含口径与日期)
  - **实现**: 创建 `market_statistics.py`，包含 3 个工具

- [x] P0-2 统一交易日与日期口径 ✅
  - 改造点: 把"日期容错/最近交易日校正"抽成公共工具，对所有需要 `start_date`/`end_date` 的工具统一处理
  - 文件: `mcp/src/utils/data_processing.py` (扩展), 影响 `mcp/src/tools/analysis.py`、`mcp/src/tools/market_data.py`、`mcp/src/tools/market_flow.py`
  - 验收: 当 end_date=今日但未出数据时，自动调整并返回 `date_adjusted` + `trade_date_used`
  - **实现**: 添加 `get_latest_trading_day`, `adjust_date_to_trading_day`, `validate_date_range` 到 `data_processing.py`

- [x] P0-3 返回口径与数据范围显式化 ✅
  - 改造点: 所有统计类工具返回 `meta` 字段，包含 `data_source`、`api_status`、`trade_date`、`date_range_supported`、`date_adjusted`
  - 文件: `mcp/src/tools/market_statistics.py`、`mcp/src/tools/analysis.py`、`mcp/src/tools/market_data.py`
  - 验收: 输出中能直接识别"统计口径"和"真实交易日"
  - **实现**: 创建 `mcp/src/utils/response.py`，包含 `build_response`, `build_meta`, `build_success_response`, `build_error_response`

---

## P1 (稳定性与体验提升)

- [x] P1-1 统一错误码与响应结构 ✅
  - 改造点: 统一返回格式: `{success, error_code, error_message, data, meta}`
  - 文件: `mcp/src/utils/response.py` (新建), 逐步改造 `mcp/src/tools/*`
  - 建议错误码: `tool_not_supported`, `schema_error`, `no_data`, `pro_required`, `rate_limited`, `upstream_error`
  - 验收: 任意工具错误都能被主 Agent 稳定识别与路由
  - **实现**: 创建 `mcp/src/utils/errors.py`，包含 `ErrorCode` 类

- [x] P1-2 "实时"语义纠偏 ✅
  - 改造点: `get_realtime_price` 实际是"最新日线"，需改名或增加 `price_type=latest_daily_close`
  - 文件: `mcp/src/tools/market_data.py`
  - 验收: 不再出现"非实时却被当作实时"的误导
  - **实现**: 重命名为 `get_latest_daily_close`，保留 `get_realtime_price` 作为别名（带废弃提示）

- [x] P1-3 返回体瘦身 ✅
  - 改造点: `get_historical_data` 增加 `include_items=false` / `max_rows`，默认只返回统计摘要
  - 文件: `mcp/src/tools/market_data.py`
  - 验收: 典型调用结果 token 占用显著降低 (与 `docs/distill-adj/0126_2.md` 对应)
  - **实现**: 添加 `include_items` (默认 False) 和 `max_rows` (默认 30) 参数

- [x] P1-4 行业工具导向修正 ✅
  - 改造点: `get_sector_top_stocks` 不再引导到仅支持单股的 `analyze_stock_performance`；要么扩展后者支持多股，要么提供行业均值统计
  - 文件: `mcp/src/tools/market_flow.py`, `mcp/src/tools/analysis.py`
  - 验收: 行业场景不再触发"参数合法但无法执行"的死路
  - **实现**: 在 `get_sector_top_stocks` 返回中添加 `next_actions` 字段，引导使用 `get_batch_pct_chg` 计算行业均值

- [x] P1-5 工具能力清单暴露 (去幻觉) ✅
  - 改造点: 提供可查询的 tool manifest (资源或工具) 以返回工具名/参数/示例
  - 文件: `mcp/src/resources/tool_manifest.py` (新建) 或 `mcp/src/tools/meta.py`
  - 验收: 主 Agent 可在调用前确认工具是否存在，避免"action 幻觉"
  - **实现**: 创建 `mcp/src/tools/meta.py`，包含 `get_tool_manifest` 工具

---

## P2 (可观测性与性能优化)

- [x] P2-1 限频与并发保护 ✅
  - 改造点: 对批量调用加全局 semaphore，避免触发 Tushare 频控
  - 文件: `mcp/src/tools/market_flow.py`, `mcp/src/utils/tushare_api.py`
  - 验收: 批量查询失败率下降
  - **实现**: `market_statistics.py` 中的 `get_batch_pct_chg` 使用分批处理 + 延迟策略

- [x] P2-2 缓存策略升级 ✅
  - 改造点: 对 `stock_basic`/`index_basic` 等大表使用更长 TTL 或预热缓存
  - 文件: `mcp/src/cache/tushare_cache.py`
  - 验收: 重复调用延迟显著降低
  - **实现**: `basic` TTL 从 24h 升级到 48h，新增 `market_stats` 缓存类型 (30分钟)

- [x] P2-3 数据覆盖范围输出 ✅
  - 改造点: 对查询结果输出 `coverage` (实际数据条数/预期条数)，避免"假完整"
  - 文件: `mcp/src/tools/market_statistics.py`, `mcp/src/tools/market_data.py`
  - 验收: 主 Agent 能判断数据是否完整
  - **实现**: 所有新工具的 `meta` 字段包含 `coverage` 和 `expected_coverage`

---

## 验收用例 (最小回归集)

1. 询问"2026年1月A股平均涨幅、均值/中位数/极值"
   - 期望: 单次调用 `get_market_summary` + `get_market_extremes`，输出含口径/日期/数据源
   - **状态**: ✅ 可用
2. 询问"今天涨幅最高的股票有哪些"
   - 期望: `get_market_extremes` 返回 top_n 列表，无需拼装
   - **状态**: ✅ 可用
3. 询问"白酒行业龙头 + 行业均值"
   - 期望: 行业工具直接返回均值或明确可调用路径，不误导到单股分析
   - **状态**: ✅ `get_sector_top_stocks` + `get_batch_pct_chg` 组合可用
4. 询问"获取 000001 的历史数据"
   - 期望: 默认不返回大列表，只有统计摘要
   - **状态**: ✅ `include_items=False` 为默认值

---

## 文件变更清单

### 新增文件
| 文件 | 描述 |
|------|------|
| `mcp/src/tools/market_statistics.py` | 3个市场统计工具 |
| `mcp/src/tools/meta.py` | 工具能力清单 |
| `mcp/src/utils/response.py` | 统一响应格式 |
| `mcp/src/utils/errors.py` | 统一错误码 |

### 修改文件
| 文件 | 修改内容 |
|------|----------|
| `mcp/src/utils/data_processing.py` | 添加日期容错公共函数 |
| `mcp/src/tools/analysis.py` | 使用共享日期容错工具 |
| `mcp/src/tools/market_data.py` | 重命名 + 返回体瘦身 |
| `mcp/src/tools/market_flow.py` | 添加 next_actions 提示 |
| `mcp/src/cache/tushare_cache.py` | 缓存策略升级 |
| `mcp/src/server.py` | 注册新模块 |

---

## 备注

- 本清单仅覆盖 `mcp/` 内 tushare-data 服务，系统侧的路由/升级/系统提示约束请参考 `docs/distill-adj/改进规划.md`。
- 工具总数从 21 增加到 26 (含 `get_realtime_price` 别名)
