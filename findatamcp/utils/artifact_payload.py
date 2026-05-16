"""MCP 工具 envelope 统一构造器（v3：content-first）

契约：
  - content[0].text   LLM 必看:header + markdown 表格(前 N 行) + 引导
  - structuredContent 机器/UI 读的数据层

structuredContent 字段:
  - rows / columns / row_count / date_range  数据本体(rows 仅在非 as_file 模式 inline)
  - path / download_urls                     仅 as_file=True
  - data / daily_data.items                  仅 include_ui=True 的 iframe 兼容别名,
                                             与 rows 同源

四种组合(as_file, include_ui)的差异:
  F, F (默认)  rows inline,    无 UI 别名
  F, T         rows inline,    +data/daily_data
  T, F         rows=[],path,   无 UI 别名
  T, T         rows=[],path,   data=[]/daily_data=[]

per-call UI 绑定:
  include_ui=True 时,ToolResult.meta = {"ui": {"resourceUri": ui_uri}},
  对应 wire 上 CallToolResult._meta.ui.resourceUri,前端按此渲染 iframe。
  tool 注册时不再静态绑定 app=AppConfig(...),tools/list 不带 _meta.ui,
  iframe 渲染完全由 per-call meta 驱动。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

# data_file_store 的 store / get_download_urls 调用点已全部撤掉
# (as_file 通路停用,改由 deepagents 端 offloading 自动落盘到 agent sandbox)。
# infer_schema 仍是列类型推断的本地工具,继续用。
# data_file_store 对象本身仍被 routes/data_download.py + resources/large_data.py
# + utils/large_data_handler.py 引用,模块文件留作 orphan,下个迭代再清。
from ..cache.data_file_store import infer_schema


def _safe_name(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]", "_", s).strip("_.") or "data"


_FILENAME_PRIORITY_KEYS = (
    "ts_code", "stock_code", "index_code", "fund_code", "symbol", "code",
    "start_date", "end_date", "trade_date", "period", "indicator",
)


def build_semantic_filename(tool_name: str, query_params: Dict[str, Any]) -> str:
    """tool_name + 关键参数 + 日期范围 → .jsonl。"""
    parts: List[str] = [_safe_name(tool_name)]
    for k in _FILENAME_PRIORITY_KEYS:
        v = query_params.get(k)
        if v is None or v == "":
            continue
        parts.append(_safe_name(str(v)))
    return "_".join(parts) + ".jsonl"


def build_columns_typed(
    rows: List[Dict[str, Any]], column_names: List[str]
) -> List[Dict[str, str]]:
    """[{name, type}] 格式（合并原 columns list + schema dict）。"""
    schema = infer_schema(rows, column_names)
    return [{"name": c, "type": schema[c]["type"]} for c in column_names]


def _fmt_cell(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        s = f"{v:.4f}".rstrip("0").rstrip(".")
        return s if s else "0"
    return str(v)


def render_jsonl_body(rows: List[Dict[str, Any]]) -> str:
    """全量 rows 渲染成 JSONL（每行一条紧凑 dict）。

    选 JSONL 不选 markdown table / JSON array 的原因:
      - 上层 deepagents offloading 触发后预览策略是 "首 10 行",JSONL 每行就是
        一条完整记录,前 10 行预览有实际信息量;markdown 前 10 行只有表头,
        JSON array 一整块只有一个 "[" 字符。
      - 大数据(几千几万行)直接 inline 没事,deepagents 检测 content >20K tokens
        会自动写到 agent sandbox /workspace/large_tool_results/,findata 侧不再
        重复做文件存储 + path 拼接(旧 as_file 通路引出的死循环源头)。
    """
    if not rows:
        return ""
    return "\n".join(
        json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in rows
    )


def render_markdown_table(
    rows: List[Dict[str, Any]],
    columns_typed: List[Dict[str, str]],
    limit: int = 10,
) -> str:
    """前 limit 行渲染为 markdown 表格。空表返回空串。

    【已不在 content.text 主路径使用】content.text 现在走 JSONL,见
    render_jsonl_body。函数保留供潜在外部调用,无内部调用点。
    """
    if not rows or not columns_typed:
        return ""
    names = [c["name"] for c in columns_typed]
    header = "| " + " | ".join(names) + " |"
    sep = "|" + "|".join([" --- "] * len(names)) + "|"
    body = "\n".join(
        "| " + " | ".join(_fmt_cell(r.get(n)) for n in names) + " |"
        for r in rows[:limit]
    )
    return f"{header}\n{sep}\n{body}"


def build_content_trailer(
    *,
    ui_uri: Optional[str],
    row_count: int,
    include_ui: bool,
) -> str:
    """content.text 尾部引导文案。

    rows 永远全量内联(JSONL),不再有 as_file 分支 / artifact path / data_id /
    download_urls。trailer 只补两件事:
      1. UI 渲染同步提示(include_ui=True 时)
      2. row_count 数值 + 一句"如何后续处理"
    """
    lines: List[str] = []
    if ui_uri and include_ui:
        lines.append(f"📊 UI 已同步渲染（{ui_uri}）。")
    if row_count == 0:
        lines.append("无数据。")
    else:
        lines.append(
            f"完整 {row_count} 行数据已 inline 在上方 (JSONL,每行一条记录)。"
            "需要做后续脚本处理 → execute / dispatch_worker 直接读取上方文本。"
        )
    return "\n".join(lines)


def build_artifact_envelope(
    rows: List[Dict[str, Any]],
    *,
    tool_name: str,
    query_params: Dict[str, Any],
    ui_uri: str,
    as_file: bool,
    include_ui: bool,
    header_text: str = "",
    max_rows_in_text: int = 10,
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """生成 envelope 各部件,调用方用 finalize_artifact_result 包成 ToolResult。

    structuredContent 字段(调用方 .update 进去):
      row_count, columns, rows, date_range  恒有 (rows 永远全量)
      data, daily_data                      仅 include_ui=True (与 rows 同源,
                                            供 ui:// iframe 渲染:多数模板读 raw.data,
                                            kline-chart 读 raw.daily_data.items)

    内部带下划线字段由 finalize_artifact_result pop 掉,不进 structuredContent:
      _content_text   content[0].text 全文(JSONL)

    as_file / filename / max_rows_in_text 参数保留只为向后兼容入参(避免改 18
    个 tool 签名),功能上忽略:rows 永远全量内联,文件落盘交给 deepagents
    offloading 机制(content >20K tokens 时自动写到 agent sandbox)。
    """
    column_names = list(rows[0].keys()) if rows else []
    columns_typed = build_columns_typed(rows, column_names)
    row_count = len(rows)

    # rows 永远全量,不再因 as_file 截断。as_file 入参形同虚设。
    # 三个字段(rows/data/daily_data.items)共用同一引用,序列化时各自一份副本。
    payload: List[Dict[str, Any]] = list(rows)

    fields: Dict[str, Any] = {
        "row_count": row_count,
        "columns": columns_typed,
        "rows": payload,
    }
    if include_ui:
        fields["data"] = payload
        fields["daily_data"] = {"items": payload}

    # date_range:从首个 date 列推
    date_col = next((c["name"] for c in columns_typed if c["type"] == "date"), None)
    if date_col and rows:
        vals = [r[date_col] for r in rows if r.get(date_col) is not None]
        if vals:
            try:
                fields["date_range"] = [min(vals), max(vals)]
            except TypeError:
                pass

    # content.text:header + 空行 + JSONL 全量 + trailer。
    # 不再调 data_file_store / 不再拼 path / 不再回填 download_urls /
    # 不再 render_markdown_table —— 那些都属于已停用的 as_file 通路。
    jsonl_body = render_jsonl_body(rows)
    trailer = build_content_trailer(
        ui_uri=ui_uri,
        row_count=row_count,
        include_ui=include_ui,
    )
    parts: List[str] = [
        p for p in (header_text.rstrip() if header_text else "", jsonl_body, trailer) if p
    ]
    fields["_content_text"] = "\n\n".join(parts)
    return fields


# 老版本工具可能在 result 里写过的字段:finalize 时统一剔除,然后由 env 重写。
# 现在所有 tools 都走 envelope,这里基本是防御性兜底,留着不亏。
_LEGACY_STRUCTURED_KEYS = (
    "rows_preview", "_llm_hint", "schema",
    "daily_data", "data_note", "items_note",
    "items_truncated", "items_resource_uri",
    "preview", "data_id", "resource_uri",
    "expires_in", "is_truncated",
)


def finalize_artifact_result(
    *,
    rows: List[Dict[str, Any]],
    result: Dict[str, Any],
    tool_name: str,
    query_params: Dict[str, Any],
    ui_uri: str,
    as_file: bool,
    include_ui: bool,
    header_text: str = "",
    max_rows_in_text: int = 10,
    filename: Optional[str] = None,
) -> ToolResult:
    """统一 envelope 出口,始终返回 ToolResult 以控制 content.text。

    流程:
      1. build_artifact_envelope 生成数据字段 + _content_text
      2. 剥离 _LEGACY_STRUCTURED_KEYS 残留(防御),把 env 字段合入 result
      3. 包成 ToolResult(content + structuredContent)
    """
    env = build_artifact_envelope(
        rows,
        tool_name=tool_name,
        query_params=query_params,
        ui_uri=ui_uri,
        as_file=as_file,
        include_ui=include_ui,
        header_text=header_text,
        max_rows_in_text=max_rows_in_text,
        filename=filename,
    )
    content_text = env.pop("_content_text", "")

    for k in _LEGACY_STRUCTURED_KEYS:
        result.pop(k, None)
    result.update(env)

    meta: Optional[Dict[str, Any]] = None
    if include_ui and ui_uri:
        meta = {"ui": {"resourceUri": ui_uri}}

    return ToolResult(
        content=[TextContent(type="text", text=content_text)],
        structured_content=result,
        meta=meta,
    )


# 旧 API 保留兼容（以防有外部调用），内部全部迁到 build_artifact_envelope
def build_artifact_fields(
    rows: List[Dict[str, Any]],
    *,
    tool_name: str,
    query_params: Dict[str, Any],
    ui_uri: str,
    as_file: bool,
    include_ui: bool,
    preview_limit: int = 20,  # 已忽略，保留签名兼容
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """【已废弃】保留签名兼容；新代码请用 build_artifact_envelope / finalize_artifact_result。

    这个函数仍会返回若干字段，但会把 content_text/_llm_hint 的概念抽掉，
    rows 是完整数据（以前是 preview）。
    """
    env = build_artifact_envelope(
        rows,
        tool_name=tool_name,
        query_params=query_params,
        ui_uri=ui_uri,
        as_file=as_file,
        include_ui=include_ui,
        max_rows_in_text=10,
        filename=filename,
    )
    env.pop("_content_text", None)
    return env


AS_FILE_INCLUDE_UI_DECISION_GUIDE = """

【include_ui 决策指南】
默认 include_ui=False:content.text 内联 JSONL 全量数据(每行一条记录)+ 结构化数据,
不附加 ui:// iframe。适合纯文本 / 分析 / 后续脚本处理场景。

何时设 include_ui=True(启用内嵌交互式 UI):
  - 用户明确要求"画图 / 出图 / 看走势 / 看分布 / 渲染图表"等可视化诉求
  - 你确认调用方 Host 支持 MCP Apps iframe 渲染(如 Claude.ai web、其它 UI Host)
  - 数据本身高度适合可视化(K 线、净值曲线、资金流、相关性矩阵等)
  - 设了 include_ui=True 后,structuredContent 会带 data + daily_data 别名,
    ToolResult.meta 不再屏蔽 ui 钩子,前端 iframe 才能拿到数据渲染。

注:as_file 参数已停用(仍保留在签名里向后兼容),传 True 等同 False,数据始终
全量 inline——deepagents 端会在 content >20K tokens 时自动 offload 到 agent
sandbox /workspace/large_tool_results/,findata 侧不再做文件存储。
"""
