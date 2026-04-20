"""大数据资源模块

为超过 200 行的工具结果提供独立数据资源，避免完整表格直接塞进上下文。
"""

import json
import logging

from fastmcp import FastMCP

from ..cache.data_file_store import data_file_store
from ..utils.large_data_handler import build_data_resource_uri

logger = logging.getLogger(__name__)


def register_large_data_resources(mcp: FastMCP):
    """注册通用大数据资源。"""

    @mcp.resource("data://table/{data_id}")
    async def get_large_table_resource(data_id: str) -> str:
        """读取工具产生的大表格数据。"""
        meta = data_file_store.get(data_id)
        uri = build_data_resource_uri(data_id)

        if meta is None:
            return json.dumps(
                {
                    "uri": uri,
                    "error": "数据资源不存在或已过期",
                    "hint": "请重新调用原始工具以生成新的数据资源。",
                },
                ensure_ascii=False,
            )

        with open(meta.json_path, "r", encoding="utf-8") as f:
            rows = json.load(f)

        return json.dumps(
            {
                "uri": uri,
                "tool_name": meta.tool_name,
                "query_params": meta.query_params,
                "total_rows": meta.total_rows,
                "columns": meta.columns,
                "schema": meta.schema,
                "download_urls": data_file_store.get_download_urls(data_id),
                "created_at": meta.created_at,
                "expires_at": meta.expires_at,
                "data": rows,
            },
            ensure_ascii=False,
            default=str,
        )
