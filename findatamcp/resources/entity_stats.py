"""金融实体统计资源

提供金融实体的统计信息和查询资源：
- entity://stats: 实体统计信息
- entity://search/{query}: 搜索实体
- entity://code/{name}: 根据名称查询代码
- entity://markets: 市场信息
"""

import json
from typing import Dict, Any
from fastmcp import FastMCP

from ..database import EntityDatabase
from ..config import config


def register_entity_resources(mcp: FastMCP, db: EntityDatabase):
    """注册金融实体资源"""

    @mcp.resource("entity://stats")
    async def get_entity_stats_resource() -> str:
        """
        金融实体统计信息（作为Resource）

        提供股票、基金的数量统计等信息
        """
        try:
            stats = await db.get_stats()
            return json.dumps({
                "uri": "entity://stats",
                "mimeType": "application/json",
                "description": "金融实体统计信息",
                "data": stats
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": f"无法获取统计信息: {str(e)}"})

    @mcp.resource("entity://search/{query}")
    async def search_entity_resource(query: str) -> str:
        """
        搜索金融实体（动态Resource）

        示例：
        - entity://search/贵州茅台 → 查询贵州茅台的代码
        - entity://search/平安银行 → 查询平安银行的代码
        - entity://search/payh → 拼音搜索

        LLM可以通过读取这个Resource来查找股票代码
        """
        try:
            entities = await db.search_entities(
                keyword=query,
                limit=10
            )

            return json.dumps({
                "uri": f"entity://search/{query}",
                "mimeType": "application/json",
                "description": f"搜索金融实体：{query}",
                "data": entities
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": f"搜索异常: {str(e)}"})

    @mcp.resource("entity://code/{name}")
    async def get_code_by_name_resource(name: str) -> str:
        """
        根据名称查询代码（动态Resource）

        示例：
        - entity://code/贵州茅台 → 600519.SH
        - entity://code/平安银行 → 000001.SZ

        这是一个便捷的Resource，LLM可以快速查询"贵州茅台的代码是多少"
        """
        try:
            entities = await db.search_entities(
                keyword=name,
                limit=1
            )

            if entities:
                entity = entities[0]
                return json.dumps({
                    "uri": f"entity://code/{name}",
                    "mimeType": "application/json",
                    "description": f"根据名称查询代码：{name}",
                    "code": entity.get("code"),
                    "name": entity.get("name"),
                    "data": entity
                }, ensure_ascii=False, indent=2)
            else:
                return json.dumps({
                    "uri": f"entity://code/{name}",
                    "error": f"未找到名为 {name} 的实体"
                })
        except Exception as e:
            return json.dumps({"error": f"查询异常: {str(e)}"})

    @mcp.resource("entity://markets")
    async def get_markets_info_resource() -> str:
        """
        市场信息（作为Resource）

        提供可用的市场列表和说明
        """
        markets_info = {
            "uri": "entity://markets",
            "mimeType": "application/json",
            "description": "中国证券市场信息",
            "markets": [
                {
                    "code": "SH",
                    "name": "上海证券交易所",
                    "description": "主板、科创板",
                    "stock_prefix": "6"
                },
                {
                    "code": "SZ",
                    "name": "深圳证券交易所",
                    "description": "主板、中小板、创业板",
                    "stock_prefix": "0,3"
                },
                {
                    "code": "BJ",
                    "name": "北京证券交易所",
                    "description": "新三板精选层",
                    "stock_prefix": "8"
                }
            ]
        }

        return json.dumps(markets_info, ensure_ascii=False, indent=2)