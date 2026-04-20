"""
配置管理模块

集中管理所有配置项，支持环境变量和默认值
"""

import os
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class Config:
    """MCP 服务器配置"""
    
    def __init__(self):
        # Tushare 配置
        self.TUSHARE_TOKEN = self._get_tushare_token()
        
        # 后端 API 配置
        self.BACKEND_API_URL = os.getenv('BACKEND_API_URL', 'http://localhost:8004')
        
        # 服务器配置
        self.HOST = os.getenv('MCP_SERVER_HOST', os.getenv('MCP_HOST', '0.0.0.0'))
        self.PORT = int(os.getenv('MCP_SERVER_PORT', os.getenv('MCP_PORT', '8006')))
        self.TRANSPORT = os.getenv('MCP_TRANSPORT', 'streamable-http')
        
        # 缓存配置
        self.CACHE_ENABLED = os.getenv('CACHE_ENABLED', 'true').lower() == 'true'
        self.CACHE_TTL_REALTIME = int(os.getenv('CACHE_TTL_REALTIME', '60'))
        self.CACHE_TTL_DAILY = int(os.getenv('CACHE_TTL_DAILY', '3600'))
        self.CACHE_TTL_FINANCIAL = int(os.getenv('CACHE_TTL_FINANCIAL', '86400'))
        self.CACHE_TTL_BASIC = int(os.getenv('CACHE_TTL_BASIC', '86400'))
        
        # 日志配置
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
        
    def _get_tushare_token(self) -> Optional[str]:
        """获取 Tushare Token（支持多种来源）"""
        # 1. 环境变量
        token = os.getenv('TUSHARE_TOKEN')
        if token:
            return token
        
        # 2. .env 文件（已由环境变量加载）
        
        # 3. tusharetoken.txt 文件
        token_file = os.path.join(os.path.dirname(__file__), '..', 'tusharetoken.txt')
        if os.path.exists(token_file):
            try:
                with open(token_file, 'r') as f:
                    token = f.read().strip()
                    if token:
                        return token
            except Exception as e:
                logger.warning(f"Failed to read tusharetoken.txt: {e}")
        
        return None
    
    def validate(self) -> bool:
        """验证配置"""
        if not self.TUSHARE_TOKEN:
            logger.warning("⚠️ TUSHARE_TOKEN not configured. Some features may be limited.")
            return False
        
        logger.info(f"✅ Configuration validated")
        logger.info(f"   Backend API: {self.BACKEND_API_URL}")
        logger.info(f"   Server: {self.HOST}:{self.PORT}")
        logger.info(f"   Transport: {self.TRANSPORT}")
        logger.info(f"   Cache: {'Enabled' if self.CACHE_ENABLED else 'Disabled'}")
        
        return True
    
    def __repr__(self) -> str:
        return (
            f"Config(host={self.HOST}, port={self.PORT}, "
            f"transport={self.TRANSPORT}, backend={self.BACKEND_API_URL}, cache={self.CACHE_ENABLED})"
        )


# 全局配置实例
config = Config()

