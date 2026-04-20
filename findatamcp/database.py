"""
数据库查询模块

提供金融实体数据库的查询接口（通过后端 API）
"""

import httpx
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class EntityDatabase:
    """
    金融实体数据库查询
    
    通过后端 API 访问本地金融实体数据库（全部A股+基金）
    """
    
    def __init__(self, backend_url: str):
        """
        初始化数据库查询客户端
        
        Args:
            backend_url: 后端 API 地址
        """
        self.backend_url = backend_url
        self._timeout = 5.0
    
    async def search_entities(
        self, 
        keyword: str, 
        entity_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        搜索金融实体
        
        Args:
            keyword: 搜索关键词（支持代码、名称、拼音）
            entity_type: 实体类型（'stock', 'fund' 等），None 表示全部
            limit: 返回数量限制
            
        Returns:
            实体列表
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    f"{self.backend_url}/api/entities/search",
                    params={
                        "keyword": keyword,
                        "type": entity_type,
                        "limit": limit
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("entities", [])
                else:
                    logger.error(f"Entity search failed: {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"Entity search error: {e}")
            return []
    
    async def get_entity_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """
        根据代码精确获取实体
        
        Args:
            code: 实体代码（如 '600519', '000001'）
            
        Returns:
            实体信息字典，未找到返回 None
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    f"{self.backend_url}/api/entities/by-code/{code}"
                )
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    return None
                else:
                    logger.error(f"Get entity by code failed: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.error(f"Get entity by code error: {e}")
            return None
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        获取数据库统计信息
        
        Returns:
            统计信息字典（股票数量、基金数量等）
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    f"{self.backend_url}/api/entities/stats"
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Get stats failed: {response.status_code}")
                    return {"error": "Failed to get stats"}
                    
        except Exception as e:
            logger.error(f"Get stats error: {e}")
            return {"error": str(e)}
    
    def __repr__(self) -> str:
        return f"EntityDatabase(backend={self.backend_url})"

