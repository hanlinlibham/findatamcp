"""
MCP 服务器主入口（模块化版本）

这是新的主入口文件，展示重构后的架构。
当前状态：部分工具已模块化，其余工具仍使用原始入口
"""

import logging
import sys
import os
from pathlib import Path
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

# ✅ 加载 .env 文件中的环境变量
try:
    from dotenv import load_dotenv
    # 加载项目根目录下的 .env 文件
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    # 如果没有安装 python-dotenv，从系统环境变量读取
    pass

# 添加父目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastmcp import FastMCP
import uvicorn

from src.config import config

# ── Session 过期友好提示中间件 ──
import json as _json
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import Response as StarletteResponse
from starlette.middleware import Middleware

class SessionExpiredMiddleware:
    """
    仅拦截带 Mcp-Session-Id 的 POST /mcp 请求的 404 响应，
    替换 "Session not found" 为包含重连指引的错误消息。
    其他所有请求（SSE、GET、非 MCP 路径）直接放行。
    """
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 只拦截 POST 请求且带 session header 的
        method = scope.get("method", "")
        headers = dict(scope.get("headers", []))
        has_session = b"mcp-session-id" in headers

        if method != "POST" or not has_session:
            await self.app(scope, receive, send)
            return

        # 对带 session 的 POST 请求，捕获响应检查是否 404
        status_code = None
        saved_start = None
        body_chunks = []

        async def intercept_send(message):
            nonlocal status_code, saved_start
            if message["type"] == "http.response.start":
                status_code = message["status"]
                if status_code == 404:
                    saved_start = message  # 暂存，等 body 到齐再决定
                else:
                    await send(message)
            elif message["type"] == "http.response.body":
                if status_code == 404:
                    body_chunks.append(message.get("body", b""))
                    if not message.get("more_body", False):
                        full_body = b"".join(body_chunks)
                        try:
                            data = _json.loads(full_body)
                            if (isinstance(data, dict)
                                and "Session not found" in data.get("error", {}).get("message", "")):
                                data["error"]["message"] = (
                                    "Session expired or invalid. "
                                    "Please reconnect: send a new initialize request "
                                    "WITHOUT the Mcp-Session-Id header to create a fresh session."
                                )
                                data["error"]["data"] = {
                                    "reason": "session_expired",
                                    "action": "reconnect",
                                    "hint": "Remove Mcp-Session-Id header and POST initialize to /mcp",
                                }
                                full_body = _json.dumps(data).encode()
                        except Exception:
                            pass
                        # 更新 content-length 并发送响应
                        patched_headers = [
                            (k, v) if k != b"content-length" else (k, str(len(full_body)).encode())
                            for k, v in saved_start.get("headers", [])
                        ]
                        await send({
                            "type": "http.response.start",
                            "status": saved_start["status"],
                            "headers": patched_headers,
                        })
                        await send({"type": "http.response.body", "body": full_body})
                else:
                    await send(message)

        await self.app(scope, receive, intercept_send)


from src.cache import cache
from src.entity_store import EntityStore
from src.utils.tushare_api import TushareAPI

# 导入工具注册函数
from src.tools.market_data import register_market_tools
from src.tools.financial_data import register_financial_tools
from src.tools.performance_data import register_performance_tools
from src.tools.market_flow import register_market_flow_tools
from src.tools.search import register_search_tools
from src.tools.analysis import register_analysis_tools
from src.tools.sector import register_sector_tools
# P0-1: 市场统计工具
from src.tools.market_statistics import register_market_statistics_tools
# P1-5: 工具元数据
from src.tools.meta import register_meta_tools
# 宏观经济数据工具
from src.tools.macro_data import register_macro_tools
# 指数数据工具
from src.tools.index_data import register_index_tools
# 基金数据工具
from src.tools.fund_data import register_fund_tools

# 导入 Resources 和 Prompts 注册函数
from src.resources.entity_stats import register_entity_resources
from src.resources.large_data import register_large_data_resources
from src.resources.stock_data import register_stock_data_resources
from src.resources.ui_apps import register_ui_app_resources
from src.prompts.stock_analysis import register_stock_prompts
from src.routes.data_download import register_data_routes
from src.cache.data_file_store import data_file_store

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_mcp_server() -> FastMCP:
    """
    创建 MCP 服务器实例（模块化版本）
    
    Returns:
        FastMCP 实例
    """
    
    # 验证配置
    config.validate()
    
    # 定义 lifespan：启动时开启数据文件清理循环
    @asynccontextmanager
    async def server_lifespan(app: FastMCP) -> AsyncIterator[None]:
        await data_file_store.start_cleanup_loop()
        logger.info("DataFileStore cleanup loop started")
        yield

    # 创建 MCP 实例
    mcp = FastMCP(
        name="ablemind-findata",
        instructions=(
            "专业A股金融数据服务。工具按分类组织：市场统计、行情数据、行业板块、量化分析、财务数据、搜索、宏观数据、指数数据。\n"
            "调用 get_tool_manifest 查看完整工具清单。"
        ),
        lifespan=server_lifespan,
    )
    
    # 初始化组件
    api = TushareAPI(config.TUSHARE_TOKEN)
    db = EntityStore()
    
    # 启动时加载实体数据（A 股 + ETF）
    import asyncio
    try:
        _count = asyncio.get_event_loop().run_until_complete(db.load(api))
        logger.info(f"   - EntityStore loaded {_count} entities")
    except RuntimeError:
        # 如果没有 event loop（不太可能），延迟加载
        logger.warning("EntityStore deferred loading (no event loop)")
    
    logger.info(f"✅ Initialized components:")
    logger.info(f"   - TushareAPI: {api}")
    logger.info(f"   - Cache: {cache}")
    logger.info(f"   - EntityStore: {db}")
    
    # 注册工具（模块化）
    logger.info("📦 Registering tools...")

    # 注册所有工具
    register_market_tools(mcp, api)
    register_financial_tools(mcp, api)
    register_performance_tools(mcp, api)
    register_market_flow_tools(mcp, api)
    register_search_tools(mcp, api, db)
    register_analysis_tools(mcp, api)
    register_sector_tools(mcp, api)
    # P0-1: 市场统计工具（3个新工具）
    register_market_statistics_tools(mcp, api)
    # P1-5: 工具元数据
    register_meta_tools(mcp, api)
    # 宏观经济数据工具（7个工具）
    register_macro_tools(mcp, api)
    # 指数数据工具（3个工具）
    register_index_tools(mcp, api)
    # 基金数据工具（3个工具）
    register_fund_tools(mcp, api)

    # 注册 Resources
    register_entity_resources(mcp, db)
    register_large_data_resources(mcp)
    register_stock_data_resources(mcp, api)
    register_ui_app_resources(mcp)

    # 注册 Prompts
    register_stock_prompts(mcp)

    # 注册数据下载路由
    register_data_routes(mcp)

    logger.info("✅ MCP Server initialized (all tools visible)")

    return mcp


def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("🚀 Starting AbleMind FinData MCP Server (Modular Version)")
    logger.info("=" * 80)
    logger.info(f"📊 Configuration:")
    logger.info(f"   - Host: {config.HOST}")
    logger.info(f"   - Port: {config.PORT}")
    logger.info(f"   - Transport: {config.TRANSPORT}")
    logger.info(f"   - Backend API: {config.BACKEND_API_URL}")
    logger.info(f"   - Cache: {'Enabled' if config.CACHE_ENABLED else 'Disabled'}")
    logger.info("=" * 80)
    
    try:
        # 创建服务器
        mcp = create_mcp_server()
        
        logger.info("🌐 Starting HTTP server...")
        logger.info(f"   URL: http://{config.HOST}:{config.PORT}")
        logger.info("=" * 80)
        
        # 启动服务器 - 使用 http_app + 中间件 + uvicorn
        app = mcp.http_app(
            transport=config.TRANSPORT,
            middleware=[Middleware(SessionExpiredMiddleware)],
        )
        uvicorn.run(app, host=config.HOST, port=config.PORT)
        
    except KeyboardInterrupt:
        logger.info("\n⚠️  Server interrupted by user")
    except Exception as e:
        logger.error(f"❌ Server failed to start: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

