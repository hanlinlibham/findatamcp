# findatamcp

基于 MCP（Model Context Protocol）的金融数据服务器，面向 LLM Agent 提供 A 股行情、财务、指数、基金、宏观等结构化数据访问能力。底层数据源为 Tushare Pro。

原名 `tushare_mcp`，重构后更名为 `findatamcp`，采用模块化包结构。

## 快速开始

### 安装

```bash
# Python 3.10+，推荐 conda
conda create -n findatamcp python=3.12
conda activate findatamcp

pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填入 TUSHARE_TOKEN
```

### 运行

```bash
# 方式 A：Streamable HTTP（默认，推荐）
python -m findatamcp.server

# 方式 B：SSE
python -m findatamcp.server_sse
# 端点：
#   GET  http://127.0.0.1:8006/sse
#   POST http://127.0.0.1:8006/messages

# 方式 C：PM2（生产部署）
./start.sh          # 等价于 pm2 start pm2.config.js
./stop.sh
```

PM2 配置通过环境变量覆盖：

| 变量 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `FINDATA_PYTHON` | `~/miniforge3/envs/mcp_server/bin/python` | Python 解释器路径 |
| `FINDATA_MCP_DIR` | `pm2.config.js` 所在目录 | 仓库根路径 |
| `FINDATA_LOG_DIR` | `~/.mcp-logs` | 日志目录 |
| `MCP_SERVER_HOST` | `127.0.0.1` | 绑定地址 |
| `MCP_SERVER_PORT` | `8006` | 端口 |

## 目录结构

```
findatamcp/
├── findatamcp/             # 主包
│   ├── server.py           # Streamable HTTP 入口
│   ├── server_sse.py       # SSE 入口
│   ├── config.py           # 配置
│   ├── database.py         # SQLite 查询
│   ├── entity_store.py     # 实体索引（拼音 / 别名）
│   ├── cache/              # 数据缓存（tushare / 计算 / 文件产物）
│   ├── tools/              # MCP tools（12 模块）
│   ├── resources/          # MCP resources（大数据 / UI apps / stats）
│   ├── prompts/            # MCP prompts
│   ├── routes/             # HTTP 路由（数据下载等）
│   └── utils/              # artifact / errors / response / ui_hint 等
├── tests/                  # pytest 测试
├── docs/                   # 文档
├── static/                 # 前端资源（AG Charts / ECharts）
├── legacy/                 # 历史脚本归档（不在生产路径上）
├── pm2.config.js           # PM2 部署配置
├── start.sh / stop.sh
└── requirements.txt
```

## 工具一览

当前注册 42 个 MCP tool，按领域分为 12 个模块：

| 模块 | 内容 |
| :--- | :--- |
| `market_data` | 实时行情、历史 K 线、日线 |
| `market_flow` | 资金流、成交明细 |
| `market_statistics` | 涨跌家数、板块统计 |
| `financial_data` | 财务三表、指标、分红 |
| `performance_data` | 业绩预告 / 快报 |
| `index_data` | 指数行情与成分股 |
| `fund_data` | 公募基金净值、持仓 |
| `sector` | 行业 / 概念板块 |
| `macro_data` | 宏观经济指标 |
| `analysis` | 技术指标、相关性、对齐处理 |
| `search` | 代码 / 名称 / 拼音 / 别名搜索 |
| `meta` | 元数据与能力发现 |

同时提供 resources（`entity_stats`、`large_data`、`stock_data`、`ui_apps`）和 prompts（`stock_analysis`）。

## 测试

```bash
pytest tests/
```

测试覆盖缓存、数据处理、市场统计、工具注册、SSE 客户端、端到端流程。

## 配置

`.env` 常用变量：

```bash
TUSHARE_TOKEN=your_token_here       # 必需
MCP_SERVER_HOST=127.0.0.1
MCP_SERVER_PORT=8006
MCP_TRANSPORT=streamable-http        # 或 sse
LOG_LEVEL=INFO
PYTHONUNBUFFERED=1
```

## 架构要点

- **依赖注入**：`server.py` 组装 `TushareAPI` / `EntityStore` / cache，注入到各 `register_*_tools(mcp, api, …)`
- **异步非阻塞**：tushare 同步调用以 thread executor 包装，避免阻塞事件循环
- **缓存分层**：tushare 原始响应 / 计算结果 / 文件产物（JSONL + 列 schema sidecar）
- **大数据响应**：工具可选 `as_file=true`，改为写入文件并返回资源 URI，配合 `include_ui=true` 让客户端直接渲染
- **实体索引**：`EntityStore` 内存表 + pypinyin 索引，支持中文名 / 拼音首字母 / 别名检索

## 文档

- [docs/README.md](docs/README.md) — 详细架构文档
- [docs/SSE_GUIDE.md](docs/SSE_GUIDE.md) — SSE 部署与客户端接入
- [docs/TUSHARE_TOOL_REFACTOR_CHECKLIST.md](docs/TUSHARE_TOOL_REFACTOR_CHECKLIST.md) — 工具重构清单
- [docs/upgrade.md](docs/upgrade.md) — 升级记录
