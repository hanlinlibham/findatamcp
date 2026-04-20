"""
工具元数据与导航

提供工具发现、自省和渐进披露导航：
- get_tool_manifest: 返回所有工具的完整清单（不受 visibility 影响）
- focus_category: 聚焦到指定分类
- show_all_tools: 显示所有工具
"""

from typing import Dict, Any
from datetime import datetime
from fastmcp import FastMCP
from fastmcp.server.context import Context

from ..utils.tushare_api import TushareAPI
from .constants import READONLY_ANNOTATIONS

# 分类显示顺序（未列出的分类追加到末尾）
CATEGORY_ORDER = [
    "市场统计",
    "行情数据",
    "行业板块",
    "量化分析",
    "财务数据",
    "基金数据",
    "搜索",
    "宏观数据",
    "指数数据",
    "导航",
    "元数据",
]

CATEGORY_NAMES = {"市场统计", "行情数据", "行业板块", "量化分析", "财务数据", "基金数据", "搜索", "宏观数据", "指数数据"}


def register_meta_tools(mcp: FastMCP, api: TushareAPI):
    """注册元数据和导航工具"""

    @mcp.tool(tags={"元数据", "导航"}, annotations=READONLY_ANNOTATIONS)
    async def get_tool_manifest() -> Dict[str, Any]:
        """返回所有已注册工具的完整清单（按分类分组，不受 visibility 影响）"""
        # 使用 _list_tools 绕过 visibility，获取全部工具
        tools = await mcp._list_tools()

        # 按分类分组
        categorized: Dict[str, list] = {}
        for tool in tools:
            # 跳过导航工具自身
            if tool.name in ("get_tool_manifest", "focus_category", "show_all_tools"):
                continue

            tags = getattr(tool, "tags", None) or set()
            category = next((t for t in tags if t in CATEGORY_NAMES), next(iter(tags), "未分类"))

            description = tool.description or ""
            summary = description.split("\n")[0].strip()

            categorized.setdefault(category, []).append({
                "name": tool.name,
                "summary": summary,
            })

        # 按 CATEGORY_ORDER 排序
        order_map = {c: i for i, c in enumerate(CATEGORY_ORDER)}
        sorted_categories = sorted(
            categorized.keys(),
            key=lambda c: order_map.get(c, len(CATEGORY_ORDER)),
        )

        tools_by_category = {c: categorized[c] for c in sorted_categories}
        total = sum(len(v) for v in tools_by_category.values())

        return {
            "total_tools": total,
            "categories": sorted_categories,
            "tools_by_category": tools_by_category,
            "api_status": "pro" if api.is_available() else "free",
            "timestamp": datetime.now().isoformat(),
        }

    @mcp.tool(tags={"导航"}, annotations=READONLY_ANNOTATIONS)
    async def focus_category(category: str, ctx: Context) -> Dict[str, Any]:
        """聚焦到指定分类，只显示该分类的工具和导航工具

        Args:
            category: 分类名（市场统计/行情数据/行业板块/量化分析/财务数据/搜索/宏观数据/指数数据）
        """
        if category not in CATEGORY_NAMES:
            return {
                "success": False,
                "error": f"未知分类: {category}",
                "available": sorted(CATEGORY_NAMES),
            }

        # 1. 隐藏所有工具
        await ctx.disable_components(match_all=True, components={"tool"})
        # 2. 显示目标分类
        await ctx.enable_components(tags={category}, components={"tool"})
        # 3. 保留导航工具
        await ctx.enable_components(tags={"导航"}, components={"tool"})

        # 返回当前可见工具列表
        visible_tools = await mcp.list_tools()
        tool_names = [t.name for t in visible_tools]

        return {
            "success": True,
            "focused_category": category,
            "visible_tools": tool_names,
            "visible_count": len(tool_names),
            "hint": "调用 show_all_tools() 恢复全部工具，或 focus_category(其他分类) 切换",
        }

    @mcp.tool(tags={"导航"}, annotations=READONLY_ANNOTATIONS)
    async def show_all_tools(ctx: Context) -> Dict[str, Any]:
        """显示所有工具（取消分类聚焦）"""
        await ctx.reset_visibility()
        # 覆盖全局默认（全局默认是最小可见），显示全部
        await ctx.enable_components(match_all=True, components={"tool"})

        visible_tools = await mcp.list_tools()
        tool_names = [t.name for t in visible_tools]

        return {
            "success": True,
            "visible_tools": tool_names,
            "visible_count": len(tool_names),
            "hint": "已显示全部工具。调用 focus_category(分类名) 可聚焦到某分类。",
        }
