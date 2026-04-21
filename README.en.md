# findatamcp

> English · [中文](README.md)

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](#license)
[![MCP](https://img.shields.io/badge/MCP-2025--06--18-purple)](https://modelcontextprotocol.io/)
[![FastMCP](https://img.shields.io/badge/built%20on-FastMCP-orange)](https://github.com/jlowin/fastmcp)

**One call. Data for the model. UI for the human.**

**findatamcp** lets LLM agents pull both *structured data for the model* and *an interactive chart for the user* in a single tool call. It ships 42 financial-data tools (A-share quotes, financial statements, funds, macro) and renders results as live UI — zoomable K-lines, market breadth dashboards, money-flow lines — via the MCP Apps spec. One fetch, no re-invocations, users interact directly in the artifact panel. Backed by Tushare Pro.

Formerly `tushare_mcp`; renamed to `findatamcp` after a modular refactor.

---

## Implementation path

### Overview

```mermaid
flowchart LR
    Agent["LLM Agent"] -->|"@mcp.tool call"| Tool["Tool handler"]
    Tool --> Envelope["artifact_payload.<br/>finalize_artifact_result"]
    Envelope --> TR["ToolResult"]

    TR --> Content["content[0].text<br/>markdown preview + trailer"]
    TR --> Struct["structuredContent<br/>rows / columns / schema"]
    TR --> Meta["meta.ui<br/>= ui://findata/*"]

    Struct -->|"rows ≤ 200"| Inline["inline full rows"]
    Struct -->|"rows &gt; 200"| Store["data_file_store<br/>.jsonl + schema sidecar"]
    Store --> DataURI["data://table/{id}"]
    Store --> HTTP["GET /data/{id}.jsonl"]

    Content --> LLM["LLM reads summary,<br/>decides next step"]
    Meta --> IFrame["sandboxed iframe<br/>ECharts render"]
    DataURI --> Next["subsequent step:<br/>resources/read · execute"]
```

### Design assumptions: two ways LLM agents collapse on financial-data workloads

The whole project is built around two empirically observed failure modes:

**Collapse ①: too many tools, the LLM can't choose.**
Dumping 42 tool descriptions into the system prompt costs thousands of tokens before the conversation even begins, and near-duplicate names (`get_stock_data` / `get_realtime_price` / `get_historical_data` all touch quotes) interfere with each other — the model routinely picks wrong or probes repeatedly.

Solution → **progressive disclosure** in `findatamcp/tools/meta.py`:
- `get_tool_manifest()` — returns a catalogue grouped into 9 categories with `name + summary` only, so the LLM sees a table of contents first.
- `focus_category("Quotes")` — via FastMCP's `ctx.disable_components(match_all=True)` + `enable_components(tags=...)`, all tools outside the requested category are **hidden from the LLM's view entirely**, leaving that category plus the three navigation tools.
- `show_all_tools()` — restores the full surface.
- Every `@mcp.tool(tags={"Quotes"}, ...)` carries a category tag; critical modules (`market_statistics`, `macro_data`) also spell out "When to use / When not to use" in their docstrings for direct decision hints.

With visibility control on by default the LLM sees 3–8 tools at a time; the full 42 come back only when `show_all_tools` is invoked.

**Collapse ②: a single tool call blows out the context.**
Ask "show me CSI 300 daily bars for the past eight years" and a naïve implementation serialises 2000+ rows × 10 columns of JSON straight into `content.text` — 30k+ tokens in one response, after which the conversation is effectively done.

Solution → **keep data out of the context; put pointers in** (`findatamcp/utils/large_data_handler.py` + `findatamcp/resources/large_data.py`):
- `THRESHOLD = 200 rows`. Above that, nothing is inlined.
- Returns `preview` (first 5 rows) + `summary` (date range + per-numeric-column latest/min/max/mean) + `resource_uri = data://table/{id}`. The LLM sees a dozen lines of summary while the full 2000 rows sit in a `.jsonl` artifact.
- To read details, the LLM calls `resources/read` on that URI; to compute metrics it invokes `execute` against the file; the frontend UI drills through `stock://calc_metrics/...` / `data://` on demand.
- For long time series (K-lines etc.), `sample_rows` does an additional max-120-point equidistant sample, keeping UI render cost bounded.

Together, both the *system prompt tokens* (tool descriptions) and *message tokens* (tool returns) are **actively offloaded** rather than left to rely on whatever context window the host happens to support.

### 1. Envelope contract: content + structuredContent + meta

Every tool exits through `finalize_artifact_result` in `findatamcp/utils/artifact_payload.py`, producing a `ToolResult` with three carefully separated layers:

| Layer | Consumer | Contents |
| :--- | :--- | :--- |
| `content[0].text` | LLM | header + first 10 rows as markdown table + trailer ("UI rendered"/"N rows total"/"pass `as_file=True` for full data") |
| `structuredContent` | UI iframe / `execute` tool | The single source of truth: `row_count` / `columns=[{name,type}]` / `rows=[…]` / optional `date_range` / optional `path` / optional `download_urls` |
| `meta` | MCP host | `{ui: None}` to explicitly suppress UI rendering when `include_ui=False`; otherwise inherits the `ui://` registered via `app=AppConfig(...)` |

The LLM always sees concise text + guidance — never drowned in rows. The UI and downstream scripts consume `structuredContent.rows`. Both sides read from the same `rows` list, so no drift between preview and full data.

### 2. Four families of resource URIs: UI, large data, entities, derived metrics

Beyond tools, findatamcp exposes four classes of MCP resources. Each URI scheme addresses a concrete context-budget problem:

| Scheme | Example | Purpose |
| :--- | :--- | :--- |
| `ui://findata/*` | `ui://findata/kline-chart` | HTML + inlined ECharts; the host renders interactive components inside a sandboxed iframe |
| `data://table/{data_id}` | `data://table/7f3e…` | On-demand fetch of >200-row artifacts so the LLM never has to carry the full table through context |
| `entity://{stats,search/…,code/…,markets}` | `entity://search/Maotai` | Security entity catalogue (code / name / pinyin / alias / stats), sub-millisecond lookup |
| `stock://calc_metrics/{calc_id}[/pair/{a}/{b}]` | `stock://calc_metrics/abc/pair/600519.SH/000858.SZ` | Time-series by-products of correlation computations plus derived metrics (volatility, max drawdown, Sharpe, monthly comparison) |

The common principle: **keep the context carrying only pointers and summaries; the actual data body lives in resources, fetched on demand**.

### 3. MCP UI: `ui://` resources + iframe postMessage

`findatamcp/resources/ui_apps.py` registers `ui://findata/*` (`market-dashboard`, `kline-chart`, `moneyflow-chart`, `macro-panel`, `data-table`). Each returns a complete HTML document:

- **Zero CDN dependency** — `static/echarts.min.js` is read into memory at startup and inlined as a `<script>` tag. This satisfies the sandboxed iframe's CSP and works in air-gapped deployments.
- **Theme forwarding** — the HTML uses `light-dark()` CSS variables; when the host emits `ui/notifications/host-context-changed`, the iframe applies the new palette.
- **Four handshake messages** (protocol `2025-06-18`):
  - `ui/initialize` (host → iframe; iframe replies with `result.protocolVersion + appCapabilities`)
  - `ui/notifications/initialized` (iframe → host, signalling readiness)
  - `ui/notifications/tool-input` (host → iframe, carrying the tool arguments)
  - `ui/notifications/tool-result` (host → iframe, carrying `structuredContent` or `content`; the iframe parses and renders)

A tool only needs to declare the binding via `@mcp.tool(app=AppConfig(ui_uri="ui://findata/kline-chart"))` and the host forwards `structuredContent` to the matching iframe.

### 4. Large-data context control: threshold dispatch + preview + resource URI

The core context saver lives in `findatamcp/utils/large_data_handler.py`. Every tool that may return a large table goes through this layer:

- **`THRESHOLD = 200 rows`**. Below the threshold the full table is inlined along with the column schema; above it, the tool immediately switches to "preview + resource" mode.
- **Top-N preview** (`build_preview_rows`, typically `preview_rows=5`; daily-bar tools can set `mode="tail"` for the most recent rows).
- **Auto-summary** (`_build_summary`) — scans once: detects date columns to emit `date_range`, for every numeric column emits `{latest, min, max, mean}`. The LLM can answer "max / mean / range" questions without ever reading the full table.
- **UI equidistant sampling** (`sample_rows`, default `max_points=120`) — long K-line series are down-sampled before rendering, preserving shape while keeping the iframe responsive.
- **Artifact dump** (`data_file_store.store`, `findatamcp/cache/data_file_store.py`) — writes a `.jsonl` (date/code columns forced to strings, `NaN → null`) plus a `schema` sidecar (`{col: {"type": date|string|number|bool}}`), so downstream AG Grid infers column types directly. 24h TTL with background sweep.
- **Pointers returned**: `is_truncated=true`, `data_id`, `resource_uri=data://table/{id}`, `download_urls`, `summary`, `preview`, `schema`, `total_rows`. The LLM decides whether to fetch more.
- **HTTP download routes** (`findatamcp/routes/data_download.py`) — beyond the MCP resource, `GET /data/{id}.jsonl`, `GET /data/{id}.json`, and `GET /data/{id}/info` are mounted for the artifact panel's "download" button.

A complementary pair of flags at the tool level (`findatamcp/utils/artifact_payload.py`) captures product intent:

- `as_file=True` — force disk dump even for ≤200 rows. Use when the user asks to "save" or when the LLM plans to call `execute` for further analysis.
- `include_ui=False` — explicitly disable UI (`meta.ui=None`). Use when the LLM will plot itself with matplotlib and wants to avoid two competing charts.

These three paths together — inline under 200, resource above 200, forced file dump — make the LLM's context footprint predictable in every scenario.

### 5. LLM behaviour: preventing redundant calls

UI-rendering tools have a known failure mode: the LLM only reads `content.text` and doesn't realise the iframe has already drawn the chart, so it re-invokes "to check". `findatamcp/utils/ui_hint.py` and `artifact_payload.build_content_trailer` cooperate to pin four guidance lines at the tail of the text:

```
UI rendered (ui://findata/kline-chart).
Full 245 rows written to /workspace/xxx.jsonl.
The user can open it in the artifact panel; you may read it with execute for further analysis.
```

Tool docstrings also embed `AS_FILE_INCLUDE_UI_DECISION_GUIDE`, exposing the `as_file` / `include_ui` decision table directly to the model. In practice this materially cuts duplicate calls.

### 6. Dependency injection + tool registration

`server.py` wires a one-shot DI container at startup:

```python
api = TushareAPI(token, cache=tushare_cache)
db  = EntityStore.from_sqlite(db_path)
mcp = FastMCP("findatamcp")

register_market_tools(mcp, api)
register_financial_tools(mcp, api)
register_search_tools(mcp, api, db)
# … 12 register_*_tools calls
```

Each module's `register_*_tools(mcp, api, [db])` hangs its `@mcp.tool` / `@mcp.resource` / `@mcp.prompt` decorators on the FastMCP instance. Tests can swap `api` for a mock and `db` for an in-memory fixture.

### 7. Cache layering

| Layer | Location | Invalidation |
| :--- | :--- | :--- |
| Raw Tushare responses | `cache/tushare_cache.py` | Keyed by endpoint + param hash; TTL tuned per frequency |
| Computed results (alignment, indicators) | `cache/calc_cache.py` | Per-process LRU; cleared on restart |
| File artifacts (`.jsonl` + schema) | `cache/data_file_store.py` | 24h TTL, background sweep |

On the async front, Tushare's Python SDK is synchronous, so `TushareAPI` wraps every call in `asyncio.to_thread` — the FastMCP event loop never blocks on network I/O.

### 8. Entity search: EntityStore + pypinyin

Search tools regularly need to map "baijiu sector", "招商银行", or "平安" to concrete `ts_code` lists. `entity_store.py` loads the full security universe from SQLite into memory at startup:

- Primary index: `ts_code → entity`
- Inverted index: `name / pinyin-full / pinyin-initials / alias → set[ts_code]`
- Chinese names are pre-encoded with `pypinyin`, so "zsyh / 招行 / 招商银行" all resolve to the same code

Searches hit the in-memory index with a TF ranking, responses are sub-millisecond, and Tushare never gets called for lookups.

---


## Why findatamcp

When wiring LLM agents to financial data, the real bottlenecks aren't the data itself — they are two engineering problems that show up again and again:

- **Tool descriptions blow out the system prompt.** Forty-two tools shipped up front cost thousands of tokens, and near-duplicates interfere with each other — the model picks wrong, then probes again. findatamcp uses **progressive disclosure** to keep the *default* visible surface at 3–8 tools (`get_tool_manifest` for the catalogue → `focus_category` to narrow → `show_all_tools` to expand).
- **One tool call fills the context.** 2000 daily bars serialised as JSON is 30k+ tokens — one response and the conversation is done. findatamcp dispatches on a **200-row threshold**: above it you only get back `preview + summary + resource_uri`; the full data lives in a `.jsonl` artifact, pulled on demand.
- **Data goes to both the model and the human.** The same `structuredContent` is piped through the MCP Apps spec into a sandboxed iframe and rendered as zoomable K-lines / dashboards / money-flow lines; the LLM sees only a markdown preview + guidance and won't loop "because it can't see the chart".
- **Production details are baked in.** Zero CDN dependency (ECharts inlined locally), three-tier caching, async Tushare, PM2 supervision, HTTP artifact download routes, fuzzy entity search (pypinyin + aliases). Not a demo.

## Preview

Structured tool results are shipped through MCP Apps (SEP-1865, protocol `2025-06-18`). The host renders a registered `ui://` resource inside a sandboxed iframe, while the LLM sees a concise markdown-table summary in `content[0].text` — so the same data reaches both the user and the model without duplication or re-invocation.

<p align="center">
  <img src="docs/pic/overview.png" alt="A-share market overview" width="720"><br>
  <sub><code>get_market_overview</code> — one-page market stats: gainers/losers, averages, PE/PB medians, donut breakdown</sub>
</p>

<p align="center">
  <img src="docs/pic/k-line-ui.png" alt="CSI 300 daily K-line" width="720"><br>
  <sub><code>get_historical_data(ts_code="000300.SH", include_ui=True)</code> — daily candles with dual MA + volume, zoom & pan enabled</sub>
</p>

## Quick start

```bash
# Python 3.10+
conda create -n findatamcp python=3.12
conda activate findatamcp

pip install -r requirements.txt
cp .env.example .env
# edit .env, set TUSHARE_TOKEN

# run (pick one)
python -m findatamcp.server              # Streamable HTTP (recommended)
python -m findatamcp.server_sse          # SSE, for Claude Desktop et al.
./start.sh                               # PM2 daemon
docker compose up -d                     # Docker (see below)
```

### Docker

```bash
export TUSHARE_TOKEN=your_token
docker compose up -d
# endpoint: http://127.0.0.1:8006
# logs:     docker logs -f findatamcp
# artifacts persist in the named volume findatamcp-data (mounted at /data)
```

Streamable HTTP is the default transport. For SSE, uncomment the `command: ["python", "-m", "findatamcp.server_sse"]` line in `docker-compose.yml`. The image is based on `python:3.12-slim`; the built image is ~400 MB.

> ⚠️ `Dockerfile` and `docker-compose.yml` are provided but **not yet CI-validated**. On first use, run `docker compose build && docker compose up` locally to confirm before rolling to production.

### PM2 environment variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `FINDATA_PYTHON` | `~/miniforge3/envs/mcp_server/bin/python` | Python interpreter path |
| `FINDATA_MCP_DIR` | `pm2.config.js` parent dir | Repo root |
| `FINDATA_LOG_DIR` | `~/.mcp-logs` | Log directory |
| `FINDATA_DATA_DIR` | `/tmp/findatamcp_data` | Large artifact dump directory |
| `MCP_SERVER_HOST` | `127.0.0.1` | Bind address |
| `MCP_SERVER_PORT` | `8006` | Port |
| `SERVER_BASE_URL` | `http://127.0.0.1:8006` | External base URL for artifacts |

## Client integration

### Claude Desktop (SSE)

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "findatamcp": {
      "transport": "sse",
      "url": "http://127.0.0.1:8006/sse"
    }
  }
}
```

Start the server with `python -m findatamcp.server_sse` or `./start_sse.sh`. After restarting Claude Desktop, findatamcp appears in the tools panel. On first use, call `get_tool_manifest` to see categories, then `focus_category` to narrow the surface.

### Cursor / Continue.dev / VS Code MCP extensions

Same SSE endpoint:

```json
{
  "mcp.servers": {
    "findatamcp": {
      "url": "http://127.0.0.1:8006/sse",
      "transport": "sse"
    }
  }
}
```

### Custom agent (Python httpx)

See [docs/SSE_GUIDE.md](docs/SSE_GUIDE.md) for a complete client example (handshake → sessionId → tool call).

## Layout

```
findatamcp/
├── findatamcp/             # main package
│   ├── server.py           # Streamable HTTP entry, assembles the DI container
│   ├── server_sse.py       # SSE entry
│   ├── config.py           # configuration
│   ├── database.py         # SQLite query helpers
│   ├── entity_store.py     # in-memory entity index (pypinyin)
│   ├── cache/              # tushare responses / computed results / file artifacts
│   │   ├── tushare_cache.py
│   │   ├── calc_cache.py
│   │   └── data_file_store.py
│   ├── tools/              # MCP tools (12 modules × 42 @mcp.tool)
│   ├── resources/          # MCP resources
│   │   ├── ui_apps.py      # ui:// interactive components (HTML + inline ECharts)
│   │   ├── large_data.py   # data:// JSONL artifact reader
│   │   ├── stock_data.py
│   │   └── entity_stats.py
│   ├── prompts/            # MCP prompts (e.g., stock_analysis)
│   ├── routes/             # extra HTTP routes (downloads)
│   └── utils/
│       ├── artifact_payload.py    # unified envelope builder
│       ├── ui_hint.py             # LLM guidance text
│       ├── tushare_api.py
│       ├── data_processing.py     # alignment / halted-trading handling
│       ├── technical_indicators.py
│       ├── large_data_handler.py
│       ├── response.py
│       └── errors.py
├── tests/                  # pytest suite
├── docs/                   # docs (including screenshots)
├── static/                 # frontend assets (ECharts, bundled locally)
├── pm2.config.js           # PM2 deployment config
├── start.sh / stop.sh      # PM2 lifecycle
├── start_sse.sh            # SSE foreground launcher
└── requirements.txt
```

## Tool catalogue

**42 MCP tools** across **12 modules**:

| Module | Scope |
| :--- | :--- |
| `market_data` | Realtime quotes, historical candles, daily bars |
| `market_flow` | Money flow, tick detail |
| `market_statistics` | Breadth, sector stats |
| `financial_data` | Three statements, ratios, dividends |
| `performance_data` | Earnings previews / flash reports |
| `index_data` | Index quotes & constituents |
| `fund_data` | Mutual-fund NAV & holdings |
| `sector` | Industry / thematic sectors |
| `macro_data` | Macro indicators (GDP / CPI / PMI / M2 / LPR …) |
| `analysis` | Technical indicators, correlation, alignment |
| `search` | Code / name / pinyin / alias lookup |
| `meta` | Metadata & capability discovery |

Also exposed: resources (`entity_stats`, `large_data`, `stock_data`, `ui_apps`) and prompts (`stock_analysis`).

## Use cases

**① Desktop AI research workbench (Claude Desktop / Cursor)**
Wire up the SSE endpoint and ask: "Pull CSI 300 daily bars for the past six months, overlay 5/20-day MAs." The tool does two things at once: the LLM gets a markdown summary — "120 trading days, +3.4% cumulative, 20-day MA sits at 4520" — while the artifact panel renders a zoomable chart with dual MAs and volume. Ask "which day closed highest" and the LLM answers from the summary without re-calling the tool.

**② Internal asset-management / research data plane**
Deploy findatamcp behind a firewall as the AI data engine. Analysts query financial statements, market breadth, or sector money flow through your internal agent. Over-threshold payloads are auto-dumped to `.jsonl` and exposed via the `/data/{id}.jsonl` download route for downstream risk / attribution systems, while `data://table/{id}` lets subsequent agent steps re-read the same data for further computation — all without round-tripping through memory.

**③ Macro / sector dashboards, generated on demand**
A daily-report workflow chains `get_macro_monthly_indicator` (GDP / CPI / PMI / M2 / LPR) + `get_sector_flow` + `get_market_overview`. The LLM drafts a market brief from the summaries while `ui://findata/macro-panel` renders a single interactive dashboard with multi-indicator lines and sector donut charts. No frontend code required.


## Configuration

Common `.env` variables:

```bash
TUSHARE_TOKEN=your_token_here       # required
MCP_SERVER_HOST=127.0.0.1
MCP_SERVER_PORT=8006
MCP_TRANSPORT=streamable-http        # or sse
LOG_LEVEL=INFO
PYTHONUNBUFFERED=1
```

## Testing

```bash
pytest tests/
```

Covers cache, data processing, market statistics, tool registration, SSE client, and end-to-end flows.

## Docs

- [docs/SSE_GUIDE.md](docs/SSE_GUIDE.md) — SSE deployment and client integration

## License

Tushare Pro data usage is subject to the [Tushare user agreement](https://tushare.pro/document/1). Code in this repo is released under MIT.
