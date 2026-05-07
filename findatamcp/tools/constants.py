"""工具共享常量"""

from mcp.types import ToolAnnotations

READONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

INCLUDE_UI_DESCRIPTION = (
    "是否在响应中附带前端图表渲染所需的结构化数据"
    "（data 数组 + daily_data.items / 各类 series 字段）。"
    "默认 False 仅返回精简文本+表格,适合纯文本 chat / CLI 场景。"
    "当 host 支持 iframe 渲染（如 ablemind 等带 UI extension 的客户端）,"
    "建议传 True 以启用 K线/资金流/估值曲线等交互图表。"
)
