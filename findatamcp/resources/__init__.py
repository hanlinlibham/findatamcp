"""
MCP Resources 模块

提供金融实体数据作为可读取的资源
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from ..database import EntityDatabase

__all__ = ['register_entity_resources']

