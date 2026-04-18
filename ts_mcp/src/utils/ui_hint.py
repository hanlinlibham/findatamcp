"""UI 渲染型工具的 LLM 提示文案生成

所有带 app=AppConfig(...) 的 MCP 工具都会在前端渲染 iframe，
但 LLM 从 content 文本里看不到 iframe 已渲染的信号，容易误判为"数据不够"
而重复调用。此模块统一生成结构化提示：
  - 明确告知前端已渲染
  - 指向完整数据的位置（structuredContent 路径或 data:// 资源）
  - 劝阻重复调用
"""

from typing import Any, Dict, Optional


def build_ui_hint(
    ui_uri: str,
    items_path: Optional[str] = None,
    items_count: Optional[int] = None,
    truncated: bool = False,
    extra_stats: Optional[str] = None,
    data_resource_uri: Optional[str] = None,
) -> str:
    """生成 UI 渲染型工具的结构化提示文本。

    Args:
        ui_uri: ui:// 资源 URI，例如 "ui://findata/kline-chart"
        items_path: structuredContent 中主数据字段路径，例如 "daily_data.items"
        items_count: 主数据条数
        truncated: 主数据是否被截断
        extra_stats: 关键统计一行文本（可选）
        data_resource_uri: data:// 大结果资源 URI（可选）

    Returns:
        多行提示字符串，前面不带空行（调用方自行拼接）
    """
    lines = [f"📊 已渲染到前端: {ui_uri}"]
    if items_path:
        info = ""
        if items_count is not None:
            trunc = "true" if truncated else "false"
            info = f" (items_count={items_count}, truncated={trunc})"
        lines.append(f"📦 完整数据: structuredContent.{items_path}{info}")
    if extra_stats:
        lines.append(f"📈 {extra_stats}")
    if data_resource_uri:
        lines.append(f"💾 大结果数据资源: {data_resource_uri}")
    lines.append(
        "ℹ️  此工具为 UI 渲染型，已展示给用户。如需其他维度请更换工具或参数而非重复调用相同参数。"
    )
    return "\n".join(lines)


def append_hint_to_summary(
    summary: str,
    ui_uri: str,
    **kwargs: Any,
) -> str:
    """给 ToolResult 的 text 摘要追加 UI 提示。"""
    return f"{summary}\n\n{build_ui_hint(ui_uri, **kwargs)}"


def attach_hint_to_dict(
    result: Dict[str, Any],
    ui_uri: str,
    **kwargs: Any,
) -> Dict[str, Any]:
    """给 dict 返回结果追加 _llm_hint 字段（不动 structuredContent 其他字段）。"""
    if not isinstance(result, dict):
        return result
    result["_llm_hint"] = build_ui_hint(ui_uri, **kwargs)
    return result
