"""
缓存机制模块

提供异步非阻塞的 Tushare API 调用缓存，支持分级 TTL
"""

from typing import Dict, Any, Callable, Optional
from datetime import datetime
import asyncio
import logging

logger = logging.getLogger(__name__)


class TushareCache:
    """Tushare API 调用缓存
    
    特点：
    - 异步非阻塞执行（使用 run_in_executor）
    - 分级 TTL（实时/日线/财务/基础）
    - 自动过期清理
    """
    
    def __init__(self, ttl_config: Optional[Dict[str, int]] = None):
        """
        初始化缓存
        
        Args:
            ttl_config: TTL 配置字典，格式：{"realtime": 60, "daily": 3600, ...}
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        # P2-2: 升级缓存策略
        self._ttl = ttl_config or {
            "realtime": 60,       # 实时数据缓存1分钟
            "daily": 3600,        # 日线数据缓存1小时
            "financial": 86400,   # 财务数据缓存24小时
            "basic": 172800,      # 基础信息缓存48小时（P2-2: 24h -> 48h）
            "market_stats": 1800  # 市场统计缓存30分钟（P0-1 新增）
        }
        self._stats = {
            "hits": 0,
            "misses": 0,
            "total_calls": 0
        }
    
    async def cached_call(
        self, 
        func: Callable, 
        cache_type: str = "daily", 
        *args, 
        **kwargs
    ) -> Any:
        """
        异步执行并缓存 Tushare 调用
        
        关键优化：使用 asyncio.to_thread 避免阻塞事件循环
        
        Args:
            func: Tushare API 函数（同步）
            cache_type: 缓存类型（realtime/daily/financial/basic）
            *args, **kwargs: 传递给 func 的参数
            
        Returns:
            API 调用结果
        """
        self._stats["total_calls"] += 1
        
        # 生成缓存键
        cache_key = self._generate_cache_key(func, args, kwargs)
        
        # 检查缓存
        cached_result = self._get_from_cache(cache_key, cache_type)
        if cached_result is not None:
            self._stats["hits"] += 1
            logger.debug(f"Cache hit: {cache_key[:50]}...")
            return cached_result
        
        # 缓存未命中
        self._stats["misses"] += 1
        
        # 关键优化：在线程池中执行同步的 Tushare API
        # 避免阻塞 asyncio 事件循环
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, lambda: func(*args, **kwargs))
            
            # 写入缓存
            self._put_to_cache(cache_key, result, cache_type)
            
            logger.debug(
                f"Cache miss: {cache_key[:50]}... "
                f"(cached for {self._ttl.get(cache_type, 3600)}s)"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Tushare API call failed: {e}")
            raise
    
    def _generate_cache_key(
        self,
        func: Callable,
        args: tuple,
        kwargs: dict
    ) -> str:
        """生成缓存键"""
        # 处理 functools.partial 对象和其他没有 __name__ 的可调用对象
        try:
            func_name = func.__name__
        except AttributeError:
            # 处理 functools.partial 对象或其他没有 __name__ 的可调用对象
            func_name = getattr(func, 'func', func).__name__ if hasattr(getattr(func, 'func', None), '__name__') else str(func)

        # 使用函数名 + 参数生成唯一键
        key_parts = [func_name]
        
        if args:
            key_parts.append(str(args))
        
        if kwargs:
            # 排序 kwargs 以确保一致性
            sorted_kwargs = sorted(kwargs.items())
            key_parts.append(str(sorted_kwargs))
        
        return ":".join(key_parts)
    
    def _get_from_cache(
        self, 
        cache_key: str, 
        cache_type: str
    ) -> Optional[Any]:
        """从缓存获取数据"""
        if cache_key not in self._cache:
            return None
        
        entry = self._cache[cache_key]
        age = (datetime.now() - entry['time']).total_seconds()
        ttl = self._ttl.get(cache_type, 3600)
        
        if age < ttl:
            return entry['data']
        else:
            # 过期，删除
            del self._cache[cache_key]
            return None
    
    def _put_to_cache(
        self, 
        cache_key: str, 
        data: Any, 
        cache_type: str
    ):
        """写入缓存"""
        self._cache[cache_key] = {
            'data': data,
            'time': datetime.now(),
            'type': cache_type
        }
    
    def clear(self, pattern: Optional[str] = None):
        """
        清除缓存
        
        Args:
            pattern: 可选的匹配模式，如果提供则只清除匹配的键
        """
        if pattern is None:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cleared all cache ({count} entries)")
        else:
            keys_to_delete = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_delete:
                del self._cache[key]
            logger.info(f"Cleared {len(keys_to_delete)} cache entries matching '{pattern}'")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        hit_rate = (
            self._stats["hits"] / self._stats["total_calls"] 
            if self._stats["total_calls"] > 0 
            else 0
        )
        
        return {
            "total_calls": self._stats["total_calls"],
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate": f"{hit_rate:.2%}",
            "cache_size": len(self._cache)
        }
    
    def __repr__(self) -> str:
        stats = self.get_stats()
        return (
            f"TushareCache(size={stats['cache_size']}, "
            f"hit_rate={stats['hit_rate']}, "
            f"total_calls={stats['total_calls']})"
        )


# 全局缓存实例
cache = TushareCache()

