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

import re
from typing import Any, Dict, List, Optional

from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from ..cache.data_file_store import data_file_store, infer_schema


# as_file=True 时仍内联前 N 行,让调用方能做 schema 探测 / 小样本决策,
# 不必为"看一眼数据"再触发一次 as_file=False 重取。
# N=20 是 prompt 预算与可用性的平衡:fan-out 5 worker × 20 行 ≈ ~5K tokens。
INLINE_PREVIEW_LIMIT = 20


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
    data_id: Optional[str],
    rows_inlined: int,
    include_ui: bool,
) -> str:
    """content.text 尾部引导文案。不引用 structuredContent 字段路径。"""
    lines: List[str] = []
    if ui_uri and include_ui:
        lines.append(f"📊 UI 已同步渲染（{ui_uri}）。")
    if path:
        # path / data_id 是 findata 内部 artifact 标识,findata 把文件写到自己
        # 进程的 /tmp/findatamcp_data/,主 agent 的 sandbox 既不能 read_file
        # 也不能 curl download_urls(--network none)。trailer 必须显式禁止两条
        # 错误路径,并指明可用替代。
        lines.append(
            f"📁 完整 {row_count} 行已存为 findata 内部 artifact（id={data_id}）。"
        )
        if rows_inlined > 0:
            lines.append(
                f"structured rows 字段含前 {rows_inlined} 行预览,够 schema 探测 / 小样本决策。"
            )
        lines.append(
            "需要全量数据做后续处理 → dispatch_worker('data-fetcher', ...) 让 worker 重新拉。"
        )
        lines.append(
            "**不要 read_file / execute 读 path**——它是 artifact 标识,不在 sandbox 里。"
        )
        lines.append(
            "**不要 curl download_urls**——sandbox 是 --network none,URL 只供前端面板用。"
        )
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
    """生成 envelope 各部件,调用方用 finalize_artifact_result 包成 ToolResult。

    structuredContent 字段(调用方 .update 进去):
      row_count, columns, rows, date_range  恒有 (rows 在 as_file 时为 [])
      path, download_urls                   仅 as_file=True
      data, daily_data                      仅 include_ui=True (与 rows 同源,
                                            供 ui:// iframe 渲染:多数模板读 raw.data,
                                            kline-chart 读 raw.daily_data.items)

    内部带下划线字段由 finalize_artifact_result pop 掉,不进 structuredContent:
      _content_text   content[0].text 全文
    """
    column_names = list(rows[0].keys()) if rows else []
    columns_typed = build_columns_typed(rows, column_names)
    row_count = len(rows)

    # 统一决定 inline 数据载体:as_file 时保留前 INLINE_PREVIEW_LIMIT 行作预览
    # (旧版本是 [] —— 强迫调用方再发一次 as_file=False 才能看数据,UX 差)。
    # 三个字段(rows/data/daily_data.items)共用同一引用,序列化时各自一份副本。
    payload: List[Dict[str, Any]] = (
        list(rows[:INLINE_PREVIEW_LIMIT]) if as_file else list(rows)
    )

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

    path: Optional[str] = None
    data_id: Optional[str] = None
    if as_file and rows:
        meta = data_file_store.store(rows, tool_name, query_params)
        urls = data_file_store.get_download_urls(meta.data_id)
        semantic = filename or build_semantic_filename(tool_name, query_params)
        path = f"/workspace/{semantic}"
        data_id = meta.data_id
        # data_id 顶层暴露:opaque artifact 标识,为后续 agent-side resolver
        # (主 agent 通过 MCP 把 data_id 换成 sandbox 内可读路径)铺路。
        # path 字段值保留 (前端 artifact 面板兼容),不破坏。
        fields["data_id"] = data_id
        fields["path"] = path
        fields["download_urls"] = urls

    table_md = render_markdown_table(rows, columns_typed, limit=max_rows_in_text)
    trailer = build_content_trailer(
        ui_uri=ui_uri,
        row_count=row_count,
        rows_shown=min(row_count, max_rows_in_text),
        path=path,
        data_id=data_id,
        rows_inlined=len(payload) if as_file else 0,
        include_ui=include_ui,
    )
    parts: List[str] = [p for p in (header_text.rstrip() if header_text else "", table_md, trailer) if p]
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

【as_file / include_ui 决策指南】
默认（as_file=False, include_ui=False）：仅 content.text 内联 markdown 表格 + 结构化数据，
不附加 ui:// iframe、不下发 UI 兼容字段；适合纯文本/分析场景，省 token 和带宽。
何时设 include_ui=True（启用内嵌交互式 UI）：
  - 用户明确要求"画图 / 出图 / 看走势 / 看分布 / 渲染图表"等可视化诉求
  - 你确认调用方 Host 支持 MCP Apps iframe 渲染（如 Claude.ai web、其它 UI Host）
  - 数据本身高度适合可视化（K 线、净值曲线、资金流、相关性矩阵等）
  - 设了 include_ui=True 后,structuredContent 会带 data + daily_data 别名,
    ToolResult.meta 不再屏蔽 ui 钩子,前端 iframe 才能拿到数据渲染。
何时设 as_file=True（把完整数据写成 .jsonl 文件）：
  - 用户明确要求"保存 / 导出 / 下载"数据
  - 你计划用 execute 工具对数据做自定义分析（聚合月线、多标的对比、计算指标等）
  - 数据规模或维度大,inline markdown 表格无法承载
"""
