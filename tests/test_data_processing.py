"""
测试数据处理模块

测试 data_processing 的工具函数
"""

import pytest
from datetime import datetime
import sys
from pathlib import Path

# 添加父目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.data_processing import normalize_stock_code, format_date, parse_tushare_date


class TestNormalizeStockCode:
    """测试股票代码标准化"""
    
    def test_normalize_sh_stock(self):
        """测试上海股票代码"""
        assert normalize_stock_code("600519") == "600519.SH"
        assert normalize_stock_code("601398") == "601398.SH"
        assert normalize_stock_code("688001") == "688001.SH"  # 科创板
    
    def test_normalize_sz_stock(self):
        """测试深圳股票代码"""
        assert normalize_stock_code("000001") == "000001.SZ"
        assert normalize_stock_code("000858") == "000858.SZ"
        assert normalize_stock_code("300001") == "300001.SZ"  # 创业板
    
    def test_normalize_bj_stock(self):
        """测试北京股票代码"""
        assert normalize_stock_code("430001") == "430001.BJ"
        assert normalize_stock_code("830001") == "830001.BJ"
    
    def test_normalize_with_suffix(self):
        """测试已有后缀的代码"""
        assert normalize_stock_code("600519.SH") == "600519.SH"
        assert normalize_stock_code("000001.SZ") == "000001.SZ"
        assert normalize_stock_code("430001.BJ") == "430001.BJ"
    
    def test_normalize_with_spaces(self):
        """测试带空格的代码"""
        assert normalize_stock_code("  600519  ") == "600519.SH"
        assert normalize_stock_code(" 000001 ") == "000001.SZ"


class TestFormatDate:
    """测试日期格式化"""
    
    def test_format_date_string(self):
        """测试字符串日期格式化"""
        assert format_date("2023-12-20") == "20231220"
        assert format_date("2023/12/20") == "20231220"
        assert format_date("20231220") == "20231220"
    
    def test_format_date_datetime(self):
        """测试 datetime 对象格式化"""
        dt = datetime(2023, 12, 20)
        assert format_date(dt) == "20231220"
    
    def test_format_date_custom_format(self):
        """测试自定义格式"""
        dt = datetime(2023, 12, 20)
        assert format_date(dt, format="%Y-%m-%d") == "2023-12-20"
        assert format_date(dt, format="%Y%m%d") == "20231220"
    
    def test_format_date_invalid_type(self):
        """测试无效类型"""
        with pytest.raises(ValueError):
            format_date(12345)
        
        with pytest.raises(ValueError):
            format_date(None)


class TestParseTushareDate:
    """测试 Tushare 日期解析"""
    
    def test_parse_tushare_date(self):
        """测试解析 Tushare 日期字符串"""
        dt = parse_tushare_date("20231220")
        
        assert isinstance(dt, datetime)
        assert dt.year == 2023
        assert dt.month == 12
        assert dt.day == 20
    
    def test_parse_tushare_date_invalid(self):
        """测试无效日期字符串"""
        with pytest.raises(ValueError):
            parse_tushare_date("2023-12-20")
        
        with pytest.raises(ValueError):
            parse_tushare_date("invalid")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

