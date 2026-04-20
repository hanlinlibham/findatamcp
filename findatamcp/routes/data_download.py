"""数据文件下载端点

GET /data/{data_id}.jsonl -> 下载 JSONL 文件（行式 JSON）
GET /data/{data_id}.json  -> 下载 JSON 文件（整体数组）
GET /data/{data_id}/info  -> 查看文件元信息 + 列 schema (调试 / 消费方查询)
"""

import logging
from starlette.requests import Request
from starlette.responses import JSONResponse, FileResponse

from ..cache.data_file_store import data_file_store

logger = logging.getLogger(__name__)


def register_data_routes(mcp):
    """注册数据下载路由"""

    @mcp.custom_route("/data/{data_id}.jsonl", methods=["GET"])
    async def download_jsonl(request: Request):
        data_id = request.path_params["data_id"]
        meta = data_file_store.get(data_id)
        if meta is None:
            return JSONResponse(
                {"error": "文件不存在或已过期", "data_id": data_id},
                status_code=404,
            )
        return FileResponse(
            meta.jsonl_path,
            media_type="application/x-ndjson; charset=utf-8",
            filename=f"{meta.tool_name}_{data_id}.jsonl",
        )

    @mcp.custom_route("/data/{data_id}.json", methods=["GET"])
    async def download_json(request: Request):
        data_id = request.path_params["data_id"]
        meta = data_file_store.get(data_id)
        if meta is None:
            return JSONResponse(
                {"error": "文件不存在或已过期", "data_id": data_id},
                status_code=404,
            )
        return FileResponse(
            meta.json_path,
            media_type="application/json; charset=utf-8",
            filename=f"{meta.tool_name}_{data_id}.json",
        )

    @mcp.custom_route("/data/{data_id}/info", methods=["GET"])
    async def data_info(request: Request):
        data_id = request.path_params["data_id"]
        meta = data_file_store.get(data_id)
        if meta is None:
            return JSONResponse(
                {"error": "文件不存在或已过期", "data_id": data_id},
                status_code=404,
            )
        urls = data_file_store.get_download_urls(data_id)
        return JSONResponse({
            "data_id": meta.data_id,
            "tool_name": meta.tool_name,
            "query_params": meta.query_params,
            "total_rows": meta.total_rows,
            "columns": meta.columns,
            "schema": meta.schema,
            "download_urls": urls,
            "created_at": meta.created_at,
            "expires_at": meta.expires_at,
        })

    logger.info("Registered data download routes: /data/{id}.jsonl, /data/{id}.json, /data/{id}/info")
