"""
测试缓存模块

测试 TushareCache 的核心功能
"""

import pytest
import asyncio
from datetime import datetime
import sys
from pathlib import Path

# 添加父目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cache import TushareCache


class TestTushareCache:
    """测试 TushareCache 类"""
    
    def test_cache_initialization(self):
        """测试缓存初始化"""
        cache = TushareCache()
        
        assert cache._cache == {}
        assert cache._stats["total_calls"] == 0
        assert cache._stats["hits"] == 0
        assert cache._stats["misses"] == 0
        
        # 测试自定义 TTL
        custom_ttl = {"realtime": 30, "daily": 1800}
        cache_custom = TushareCache(ttl_config=custom_ttl)
        assert cache_custom._ttl["realtime"] == 30
        assert cache_custom._ttl["daily"] == 1800
    
    @pytest.mark.asyncio
    async def test_cached_call_miss(self):
        """测试缓存未命中"""
        cache = TushareCache()
        
        # 模拟一个同步函数
        def mock_api_call(x, y):
            return x + y
        
        result = await cache.cached_call(
            mock_api_call,
            cache_type="daily",
            5,
            10
        )
        
        assert result == 15
        assert cache._stats["total_calls"] == 1
        assert cache._stats["misses"] == 1
        assert cache._stats["hits"] == 0
    
    @pytest.mark.asyncio
    async def test_cached_call_hit(self):
        """测试缓存命中"""
        cache = TushareCache()
        
        # 模拟一个同步函数
        call_count = {"count": 0}
        
        def mock_api_call(x):
            call_count["count"] += 1
            return x * 2
        
        # 第一次调用 - 缓存未命中
        result1 = await cache.cached_call(
            mock_api_call,
            cache_type="daily",
            5
        )
        assert result1 == 10
        assert call_count["count"] == 1
        
        # 第二次调用 - 缓存命中
        result2 = await cache.cached_call(
            mock_api_call,
            cache_type="daily",
            5
        )
        assert result2 == 10
        assert call_count["count"] == 1  # 函数没有被再次调用
        assert cache._stats["hits"] == 1
    
    def test_cache_key_generation(self):
        """测试缓存键生成"""
        cache = TushareCache()
        
        def test_func():
            pass
        
        # 测试不同参数生成不同的键
        key1 = cache._generate_cache_key(test_func, (1, 2), {})
        key2 = cache._generate_cache_key(test_func, (1, 3), {})
        key3 = cache._generate_cache_key(test_func, (1, 2), {"a": 1})
        
        assert key1 != key2
        assert key1 != key3
        assert key2 != key3
        
        # 测试相同参数生成相同的键
        key4 = cache._generate_cache_key(test_func, (1, 2), {})
        assert key1 == key4
    
    def test_clear_cache(self):
        """测试清除缓存"""
        cache = TushareCache()
        
        # 添加一些缓存数据
        cache._cache["key1"] = {"data": "value1", "time": datetime.now(), "type": "daily"}
        cache._cache["key2"] = {"data": "value2", "time": datetime.now(), "type": "daily"}
        cache._cache["test_key"] = {"data": "value3", "time": datetime.now(), "type": "realtime"}
        
        assert len(cache._cache) == 3
        
        # 清除所有缓存
        cache.clear()
        assert len(cache._cache) == 0
        
        # 重新添加数据
        cache._cache["key1"] = {"data": "value1", "time": datetime.now(), "type": "daily"}
        cache._cache["test_key"] = {"data": "value3", "time": datetime.now(), "type": "realtime"}
        
        # 按模式清除
        cache.clear(pattern="test")
        assert len(cache._cache) == 1
        assert "key1" in cache._cache
        assert "test_key" not in cache._cache
    
    def test_get_stats(self):
        """测试获取统计信息"""
        cache = TushareCache()
        
        # 初始状态
        stats = cache.get_stats()
        assert stats["total_calls"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate"] == "0.00%"
        assert stats["cache_size"] == 0
        
        # 模拟一些调用
        cache._stats["total_calls"] = 10
        cache._stats["hits"] = 7
        cache._stats["misses"] = 3
        cache._cache["key1"] = {"data": "value"}
        
        stats = cache.get_stats()
        assert stats["total_calls"] == 10
        assert stats["hits"] == 7
        assert stats["misses"] == 3
        assert stats["hit_rate"] == "70.00%"
        assert stats["cache_size"] == 1
    
    def test_cache_repr(self):
        """测试缓存的字符串表示"""
        cache = TushareCache()
        repr_str = repr(cache)
        
        assert "TushareCache" in repr_str
        assert "size=0" in repr_str
        assert "hit_rate=0.00%" in repr_str
        assert "total_calls=0" in repr_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

