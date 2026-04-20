"""
AbleMind FinData MCP 服务器 - SSE 版本

使用 Server-Sent Events (SSE) 传输协议的 MCP 服务器。
SSE 适用于需要通过 HTTP 进行单向服务器推送的场景。

特点：
- ✅ SSE 传输协议，兼容标准 MCP 客户端
- ✅ 端点: /sse (事件流) 和 /messages (客户端消息)
- ✅ 完全异步，非阻塞 I/O
- ✅ 与模块化版本共享相同的工具集

运行方式：
    python src/server_sse.py

    # 或指定端口
    MCP_PORT=8006 python src/server_sse.py

环境变量：
    TUSHARE_TOKEN - 金融数据 Pro API Token（必需）
    BACKEND_API_URL - 后端API地址（默认 http://localhost:8004）
    MCP_HOST - 服务器地址（默认 0.0.0.0）
    MCP_PORT - 服务器端口（默认 8006）
"""

import logging
import sys
import os
from pathlib import Path

# 加载 .env 文件中的环境变量
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

# 添加父目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastmcp import FastMCP

from src.config import config
from src.cache import cache
from src.database import EntityDatabase
from src.utils.tushare_api import TushareAPI

# 导入工具注册函数
from src.tools.market_data import register_market_tools
from src.tools.financial_data import register_financial_tools
from src.tools.performance_data import register_performance_tools
from src.tools.market_flow import register_market_flow_tools
from src.tools.search import register_search_tools
from src.tools.analysis import register_analysis_tools
from src.tools.sector import register_sector_tools
from src.tools.market_statistics import register_market_statistics_tools
from src.tools.meta import register_meta_tools
from src.tools.macro_data import register_macro_tools

# 导入 Resources 和 Prompts 注册函数
from src.resources.entity_stats import register_entity_resources
from src.resources.large_data import register_large_data_resources
from src.resources.stock_data import register_stock_data_resources
from src.resources.ui_apps import register_ui_app_resources
from src.prompts.stock_analysis import register_stock_prompts

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_mcp_server() -> FastMCP:
    """
    创建 MCP 服务器实例（SSE 版本）

    Returns:
        FastMCP 实例
    """

    # 验证配置
    config.validate()

    # 创建 MCP 实例
    mcp = FastMCP(
        name="ablemind-findata",
        instructions="""AbleMind 金融数据服务 - SSE 版本

提供中国 A 股市场的专业金融数据服务，包含 32 个工具：
- 市场数据：股票行情、历史数据、涨跌停信息
- 财务数据：财务报表、财务指标、资产负债表
- 宏观数据：GDP、CPI、PMI、利率、汇率等
- 分析工具：技术指标、估值分析、行业对比

传输协议: SSE (Server-Sent Events)
端点: /sse (事件流), /messages (消息接收)
"""
    )

    # 初始化组件
    api = TushareAPI(config.TUSHARE_TOKEN)
    db = EntityDatabase(config.BACKEND_API_URL)

    logger.info(f"✅ Initialized components:")
    logger.info(f"   - TushareAPI: {api}")
    logger.info(f"   - Cache: {cache}")
    logger.info(f"   - Database: {db}")

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
    register_market_statistics_tools(mcp, api)
    register_meta_tools(mcp, api)
    register_macro_tools(mcp, api)

    # 注册 Resources
    register_entity_resources(mcp, db)
    register_large_data_resources(mcp)
    register_stock_data_resources(mcp, api)
    register_ui_app_resources(mcp)

    # 注册 Prompts
    register_stock_prompts(mcp)

    logger.info("✅ MCP Server initialized (SSE mode)")
    logger.info(f"   - Tools: 32")
    logger.info(f"   - Resources: 4")
    logger.info(f"   - Prompts: 4")

    return mcp


def main():
    """主函数 - SSE 版本"""
    logger.info("=" * 80)
    logger.info("🚀 Starting AbleMind FinData MCP Server (SSE Version)")
    logger.info("=" * 80)
    logger.info(f"📊 Configuration:")
    logger.info(f"   - Host: {config.HOST}")
    logger.info(f"   - Port: {config.PORT}")
    logger.info(f"   - Transport: sse")
    logger.info(f"   - Backend API: {config.BACKEND_API_URL}")
    logger.info(f"   - Cache: {'Enabled' if config.CACHE_ENABLED else 'Disabled'}")
    logger.info("=" * 80)

    try:
        # 创建服务器
        mcp = create_mcp_server()

        logger.info("🌐 Starting SSE HTTP server...")
        logger.info(f"   SSE Endpoint: http://{config.HOST}:{config.PORT}/sse")
        logger.info(f"   Messages Endpoint: http://{config.HOST}:{config.PORT}/messages")
        logger.info("=" * 80)

        # 启动服务器 - 使用 SSE 传输
        mcp.run(
            transport="sse",
            host=config.HOST,
            port=config.PORT
        )

    except KeyboardInterrupt:
        logger.info("\n⚠️  Server interrupted by user")
    except Exception as e:
        logger.error(f"❌ Server failed to start: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
