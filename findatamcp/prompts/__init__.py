"""
MCP Prompts 模块

提供可重用的提示模板
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

__all__ = ['register_stock_prompts']

