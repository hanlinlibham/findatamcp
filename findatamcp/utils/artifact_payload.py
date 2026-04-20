"""MCP 工具 envelope 统一构造器（v3：content-first，去混淆）

核心契约：
  - content[0].text  = LLM 唯一可信信道：header 摘要 + markdown 表格 + 引导
  - structuredContent = 机器读的数据层（rows 单源、columns 带 type、path 可选）
    不放 hint、不放引用路径、不放副本。

四种组合（as_file, include_ui）行为不变：
  F, T → UI + text 内联 markdown 表格（前 N 行）
  T, T → UI + text 表格 + path
  T, F → 无 UI + text 表格 + path（ToolResult.meta={ui: None}）
  F, F → 无 UI + text 表格
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from ..cache.data_file_store import data_file_store, infer_schema


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


def render_markdown_table(
    rows: List[Dict[str, Any]],
    columns_typed: List[Dict[str, str]],
    limit: int = 10,
) -> str:
    """前 limit 行渲染为 markdown 表格。空表返回空串。"""
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
    rows_shown: int,
    path: Optional[str],
    include_ui: bool,
) -> str:
    """content.text 尾部引导文案。不引用 structuredContent 字段路径。"""
    lines: List[str] = []
    if ui_uri and include_ui:
        lines.append(f"📊 UI 已同步渲染（{ui_uri}）。")
    if path:
        lines.append(f"📁 完整 {row_count} 行数据已写入 {path}。")
        if include_ui:
            lines.append("用户可在 artifact 面板打开此文件交互查看；你也可以用 execute 读此文件做进一步分析。")
        else:
            lines.append("无内嵌 UI。你可以用 execute + matplotlib/plotly 绘图，或直接让用户在 artifact 面板查看此文件。")
    elif row_count == 0:
        lines.append("无数据。")
    elif row_count > rows_shown:
        lines.append(f"上方表格仅显示前 {rows_shown} 行（共 {row_count} 行）。需要完整数据做文件导出或脚本处理时，重新调用并设 as_file=True。")
    else:
        lines.append("当前数据已内嵌上方表格，够回答大部分问题时直接答。需要把数据落成文件做后续处理时，重新调用并设 as_file=True。")
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
    """生成 envelope 各部件。

    返回：
        # structuredContent 字段（调用方 .update 进去）
        row_count    : int
        columns      : list[{name, type}]
        rows         : list[dict]        唯一数据源（完整数据）
        date_range   : [min, max] | 缺省 （当且仅当有 date 列）
        path         : str               仅 as_file=True
        download_urls: dict              仅 as_file=True

        # 以下字段由调用方消费，不进 structuredContent
        _content_text  : str             content[0].text 全文
        _meta_override : dict | None     ToolResult.meta（include_ui=False 时 {'ui': None}）
    """
    column_names = list(rows[0].keys()) if rows else []
    columns_typed = build_columns_typed(rows, column_names)
    row_count = len(rows)

    fields: Dict[str, Any] = {
        "row_count": row_count,
        "columns": columns_typed,
        "rows": list(rows),
    }

    # date_range：选第一个识别为 date 的列
    date_col = next((c["name"] for c in columns_typed if c["type"] == "date"), None)
    if date_col and rows:
        vals = [r[date_col] for r in rows if r.get(date_col) is not None]
        if vals:
            try:
                fields["date_range"] = [min(vals), max(vals)]
            except TypeError:
                pass

    path: Optional[str] = None
    if as_file and rows:
        meta = data_file_store.store(rows, tool_name, query_params)
        urls = data_file_store.get_download_urls(meta.data_id)
        semantic = filename or build_semantic_filename(tool_name, query_params)
        path = f"/workspace/{semantic}"
        fields["path"] = path
        fields["download_urls"] = urls

    table_md = render_markdown_table(rows, columns_typed, limit=max_rows_in_text)
    trailer = build_content_trailer(
        ui_uri=ui_uri,
        row_count=row_count,
        rows_shown=min(row_count, max_rows_in_text),
        path=path,
        include_ui=include_ui,
    )
    parts: List[str] = []
    if header_text:
        parts.append(header_text.rstrip())
    if table_md:
        parts.append(table_md)
    if trailer:
        parts.append(trailer)
    fields["_content_text"] = "\n\n".join(parts)
    fields["_meta_override"] = {"ui": None} if not include_ui else None
    return fields


# 历史上留下来的字段，新 envelope 契约下统一剔除
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
    """统一 envelope 出口 —— 始终返回 ToolResult 以控制 content.text。

    - 清理 result 里的旧字段（rows_preview/_llm_hint/daily_data/...）
    - 合入 row_count/columns/rows/date_range/path
    - content[0].text = header + markdown table + trailer
    - include_ui=False → meta={ui: None} 覆盖信号
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
    meta_override = env.pop("_meta_override", None)

    for k in _LEGACY_STRUCTURED_KEYS:
        result.pop(k, None)
    result.update(env)

    return ToolResult(
        content=[TextContent(type="text", text=content_text)],
        structured_content=result,
        meta=meta_override,
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

【as_file / include_ui 决策指南】
默认（as_file=False, include_ui=True）：UI iframe + content.text 内联 markdown 表格，
通常足以回答问题；不要重复调用。
何时设 as_file=True（把完整数据写成 .jsonl 文件）：
  - 用户明确要求"保存 / 导出 / 下载"数据
  - 你计划用 execute 工具对数据做自定义分析（聚合月线、多标的对比、计算指标等）
  - 数据规模或维度超出内嵌 UI 范围
  - 用户要求以表格形式交互（排序、筛选）
何时设 include_ui=False（跳过内嵌 UI）：
  - 你已决定 as_file=True 并打算自己绘图——避免两张图混淆
  - 用户只需要数据做逻辑判断，不需要可视化
"""
