# Tushare MCP Server

企业级金融数据 MCP 服务器，提供 32 个专业金融数据工具，覆盖 A 股行情、财务报表、量化分析、宏观经济全流程。

## 特性

- **32个专业工具**：覆盖行情、财务、分析、市场统计、宏观经济全流程
- **宏观经济数据**：GDP/CPI/PMI/M2/LPR 一站式获取，支持经济周期判断
- **市场统计聚合**：单次调用获取全市场均值/涨跌家数/极值排名
- **LLM 优化提示词**：每个工具都有"适用场景"和"不适用场景"说明，帮助 Agent 选择正确工具
- **生产级性能**：异步非阻塞、智能缓存、数据对齐
- **日期容错**：自动调整非交易日到最近有效交易日

## 快速开始

### 1. 安装依赖

```bash
cd mcp
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件：

```bash
# Tushare Token（必需，从 https://tushare.pro 获取）
TUSHARE_TOKEN=your_token_here

# 服务器配置
MCP_HOST=0.0.0.0
MCP_PORT=8006
```

### 3. 启动服务

```bash
# 方式1：直接启动
python src/server.py

# 方式2：使用 PM2（推荐生产环境）
./start.sh
```

---

## 工具分类与选择指南

### 如何选择正确的工具？

| 用户问法 | 推荐工具 | 说明 |
|---------|---------|------|
| "市场/A股平均涨幅是多少" | `get_market_summary` | 市场整体统计 |
| "今天涨幅最高的股票" | `get_market_extremes` | 涨跌排行榜 |
| "000001 现在价格多少" | `get_latest_daily_close` | 单股最新收盘价 |
| "白酒行业今年涨了多少" | `get_sector_top_stocks` + `get_batch_pct_chg` | 行业分析组合 |
| "宏观经济环境怎么样" | `get_macro_summary` | 宏观经济概览 |
| "GDP/CPI/PMI 是多少" | `get_macro_summary` 或具体工具 | 宏观指标 |
| "介绍一下平安银行" | `get_stock_data` | 综合信息 |

---

## 工具清单（32个）

### 一、宏观经济数据（7个）

提供中国宏观经济数据，帮助理解市场环境和货币政策。

| 工具 | 功能 | 关键返回 |
|------|------|----------|
| `get_macro_summary` | ⭐ 宏观经济概览（首选） | GDP/CPI/PMI/M2/LPR + 经济周期分析 |
| `get_gdp_data` | 季度 GDP 数据 | 总量、同比、第一/二/三产业 |
| `get_cpi_data` | CPI 消费价格指数 | 同比、环比、通胀水平判断 |
| `get_ppi_data` | PPI 工业品价格 | 同比、环比、生产/生活资料 |
| `get_pmi_data` | PMI 采购经理指数 | PMI值、扩张/收缩判断（50为荣枯线） |
| `get_money_supply` | M0/M1/M2 货币供应量 | 同比增速、货币政策松紧判断 |
| `get_interest_rates` | SHIBOR/LPR 利率 | 各期限利率、贷款基准 |

**宏观数据使用示例：**

```python
# 一站式获取宏观经济概览
result = await get_macro_summary()

# 返回结构
{
  "data": {
    "gdp": {"quarter": "2024Q4", "gdp_yoy": 5.0},
    "cpi": {"month": "202412", "yoy": 0.1},
    "pmi": {"month": "202412", "manufacturing_pmi": 50.1, "interpretation": "扩张"},
    "money": {"month": "202412", "m2_yoy": 7.3},
    "lpr": {"lpr_1y": 3.10, "lpr_5y": 3.60}
  },
  "analysis": {
    "growth": "中高速增长",
    "inflation": "低通胀",
    "manufacturing": "制造业温和扩张",
    "monetary_policy": "适度宽松"
  }
}
```

### 二、市场统计工具（3个）

解决"市场均值/极值不可达"问题，单次调用返回完整统计数据。

| 工具 | 功能 | 关键返回 |
|------|------|----------|
| `get_market_summary` | ⭐ 全市场统计（首选） | 平均涨幅、涨跌家数、涨停跌停、成交额 |
| `get_market_extremes` | 极值排名 | 涨幅/跌幅 Top N 列表 |
| `get_batch_pct_chg` | 批量涨跌幅 | 多股区间涨跌幅 + 均值统计 |

**市场统计使用示例：**

```python
# 获取今日 A 股市场统计
result = await get_market_summary()
data = result['data']

print(f"平均涨幅: {data['pct_chg_stats']['mean']:.2f}%")
print(f"上涨: {data['advance_decline']['advance']} 家")
print(f"涨停: {data['limit_stats']['limit_up']} 家")
print(f"成交额: {data['amount_stats']['total']:.0f} 亿")

# 获取涨幅 Top 10
result = await get_market_extremes(top_n=10)
for stock in result['data']['top_gainers']:
    print(f"{stock['name']}: +{stock['pct_chg']}%")
```

### 三、行情数据工具（4个）

| 工具 | 功能 | 适用场景 |
|------|------|----------|
| `get_latest_daily_close` | ⭐ 最新日收盘价 | 查询单股价格、涨跌幅 |
| `get_stock_data` | 综合数据 | 全面了解一只股票 |
| `get_historical_data` | 历史行情统计 | 区间最高/最低价、波动率 |
| `get_moneyflow` | 资金流向 | 主力/散户买卖分析 |

> ⚠️ `get_latest_daily_close` 返回的是**日线收盘数据**，非盘中实时行情。

### 四、行业板块工具（2个）

| 工具 | 功能 | 适用场景 |
|------|------|----------|
| `get_sector_top_stocks` | 行业龙头股列表 | "白酒行业有哪些龙头" |
| `get_top_list` | 龙虎榜数据 | 游资动向、异动股 |

**行业分析使用示例：**

```python
# 步骤1：获取白酒龙头股
sector = await get_sector_top_stocks(sector_name="白酒", limit=10)
codes = sector['codes']  # ['600519.SH', '000858.SZ', ...]

# 步骤2：计算行业区间涨跌幅
batch = await get_batch_pct_chg(codes, "20260101", "20260127")

print(f"行业均值: {batch['data']['statistics']['mean']:.2f}%")
for item in batch['data']['results']:
    print(f"  {item['name']}: {item['pct_chg']:.2f}%")
```

### 五、财务数据工具（5个）

| 工具 | 功能 |
|------|------|
| `get_income_statement` | 利润表 |
| `get_balance_sheet` | 资产负债表 |
| `get_cashflow_statement` | 现金流量表 |
| `get_financial_indicator` | 财务指标 |
| `get_financial_indicators` | 核心财务指标 |

### 六、业绩数据工具（2个）

| 工具 | 功能 |
|------|------|
| `get_forecast` | 业绩预告 |
| `get_express` | 业绩快报 |

### 七、量化分析工具（5个）

| 工具 | 功能 | 适用场景 |
|------|------|----------|
| `get_financial_metrics` | 财务指标聚合 | CAGR/YoY/TTM 计算 |
| `analyze_price_correlation` | 相关性分析 | 多股相关性、Beta |
| `analyze_stock_performance` | 深度量化 | Sharpe/RSI/MACD |
| `calculate_metrics` | 相关性矩阵 | 组合分析 |
| `analyze_sector` | 行业分析 | 板块对比 |

### 八、搜索工具（3个）

| 工具 | 功能 |
|------|------|
| `search_stocks` | 股票搜索 |
| `search_financial_entity` | 金融实体搜索（支持拼音） |
| `get_entity_by_code` | 精确查询实体 |

### 九、元数据工具（1个）

| 工具 | 功能 |
|------|------|
| `get_tool_manifest` | 获取所有工具清单和使用说明 |

---

## 项目结构

```
mcp/
├── src/                          # 源代码
│   ├── server.py                 # MCP 服务器入口
│   ├── config.py                 # 配置管理
│   │
│   ├── tools/                    # MCP 工具模块
│   │   ├── macro_data.py         # 宏观经济数据（7个工具）
│   │   ├── market_statistics.py  # 市场统计（3个工具）
│   │   ├── market_data.py        # 行情数据（4个工具）
│   │   ├── market_flow.py        # 市场流向（2个工具）
│   │   ├── financial_data.py     # 财务数据（5个工具）
│   │   ├── performance_data.py   # 业绩数据（2个工具）
│   │   ├── analysis.py           # 量化分析（5个工具）
│   │   ├── search.py             # 搜索工具（3个工具）
│   │   └── meta.py               # 元数据（1个工具）
│   │
│   ├── cache/                    # 缓存机制
│   │   └── tushare_cache.py      # 分级 TTL 缓存
│   │
│   └── utils/                    # 工具函数
│       ├── tushare_api.py        # Tushare API 封装
│       ├── data_processing.py    # 日期容错、数据清洗
│       ├── response.py           # 统一响应格式
│       └── errors.py             # 统一错误码
│
├── docs/                         # 文档
│   └── README.md                 # 本文档
│
├── start.sh                      # 启动脚本
├── pm2.config.js                 # PM2 配置
└── requirements.txt              # 依赖
```

---

## 性能优化

### 智能缓存（分级 TTL）

| 数据类型 | TTL | 说明 |
|---------|-----|------|
| realtime | 60秒 | 日线数据（盘中） |
| daily | 1小时 | 日线数据 |
| financial | 24小时 | 财务/宏观数据 |
| basic | 48小时 | 基础信息 |
| market_stats | 30分钟 | 市场统计 |

### 日期容错

- 自动检测非交易日（周末、节假日）
- 自动调整到最近有效交易日
- 返回 `meta.date_adjusted` 标识是否调整

---

## 统一响应格式

所有工具返回统一的响应结构：

```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "data_source": "tushare_pro",
    "trade_date": "20260127",
    "date_adjusted": false,
    "coverage": 5287
  },
  "analysis": { ... },  // 部分工具提供
  "timestamp": "2026-01-27T10:00:00"
}
```

---

## 错误码

| 错误码 | 说明 |
|--------|------|
| `no_data` | 未找到数据 |
| `pro_required` | 需要 Tushare Pro |
| `rate_limited` | 触发频率限制 |
| `invalid_date` | 无效日期 |
| `invalid_stock_code` | 无效股票代码 |
| `upstream_error` | 上游 API 错误 |

---

## 更新日志

### v2.2.0 (2026-01-27)
- **新增宏观经济数据模块（7个工具）**
  - `get_macro_summary` - 宏观经济一站式概览
  - `get_gdp_data` - 季度 GDP 数据
  - `get_cpi_data` - CPI 消费价格指数
  - `get_ppi_data` - PPI 工业品价格
  - `get_pmi_data` - PMI 采购经理指数
  - `get_money_supply` - M0/M1/M2 货币供应量
  - `get_interest_rates` - SHIBOR/LPR 利率
- 优化所有工具的提示词，添加"适用场景"和"不适用场景"
- 移除废弃的 `get_realtime_price`（使用 `get_latest_daily_close` 替代）
- 更新工具清单 `get_tool_manifest`

### v2.1.0 (2026-01-26)
- 新增市场统计工具（3个）
- 新增工具能力清单
- 统一响应格式和错误码
- 日期容错公共工具

### v2.0.0 (2025-11-20)
- 模块化重构
- 添加语义泛化工具

### v1.0.0
- 21个专业金融工具
- 生产级性能优化
