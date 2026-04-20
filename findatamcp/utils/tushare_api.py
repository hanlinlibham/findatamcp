"""
Tushare API 包装器（精简版）

替代原来的 tushare_collector_full.py，只保留核心功能
"""

import tushare as ts
import re
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class TushareAPI:
    """
    Tushare API 包装器
    
    提供 Tushare Pro API 的统一访问接口，处理初始化和错误
    """
    
    def __init__(self, token: Optional[str] = None):
        """
        初始化 Tushare API
        
        Args:
            token: Tushare Pro API token
        """
        self.token = token
        self.pro = None
        self._is_pro = False
        
        if self.token:
            try:
                ts.set_token(self.token)
                self.pro = ts.pro_api(self.token)
                
                # 测试连接
                test_df = self.pro.stock_basic(list_status='L', limit=1)
                if not test_df.empty:
                    self._is_pro = True
                    logger.info("✅ Tushare Pro API initialized successfully")
                else:
                    logger.warning("⚠️ Tushare Pro API test returned empty data")
                    
            except Exception as e:
                logger.error(f"❌ Tushare Pro API init failed: {e}")
                logger.info("📦 Falling back to free Tushare API")
                self.pro = None
        else:
            logger.warning("⚠️ No Tushare Pro token provided")
            logger.info("📦 Using free Tushare API (limited features)")
    
    def is_available(self) -> bool:
        """检查 Tushare Pro API 是否可用"""
        return self.pro is not None and self._is_pro
    
    def normalize_stock_code(self, code: str) -> str:
        """
        标准化股票代码为 Tushare 格式

        Args:
            code: 股票代码，如 '000001'、'000001.SZ'、'00700.HK'、'AAPL'

        Returns:
            标准化后的代码，如 '000001.SZ'、'00700.HK'、'AAPL'
        """
        code = code.strip()

        # 港股：.HK 结尾，直接返回
        if code.upper().endswith('.HK'):
            return code.upper()

        # 美股：全字母 1-5 位，直接返回（美股无后缀）
        base = code.split('.')[0] if '.' in code else code
        if base.isalpha() and 1 <= len(base) <= 5:
            return code.upper()

        # 如果已经包含市场后缀，直接返回（A 股 / 指数）
        if '.' in code:
            return code

        # A 股裸码：根据代码前缀判断市场
        if code.startswith('6'):
            return f"{code}.SH"  # 上海主板
        elif code.startswith('8') or code.startswith('4'):
            return f"{code}.BJ"  # 北京交易所
        else:
            return f"{code}.SZ"  # 深圳（包括创业板、中小板）
    
    def get_api_type(self) -> str:
        """获取当前使用的 API 类型"""
        if self._is_pro:
            return "Tushare Pro"
        else:
            return "Tushare Free"
    
    def get_market(self, code: str) -> str:
        """
        判断代码所属市场，返回 "HK" / "US" / "A"

        规则：
        - *.HK → 港股
        - 全字母 1-5 位（或 字母.字母 如 BRK.A）→ 美股
        - 其余 → A 股（含指数）
        """
        code = code.strip()
        if code.upper().endswith('.HK'):
            return "HK"
        # 美股：全字母（1-5位），或 字母.字母 如 BRK.A
        base = code.split('.')[0] if '.' in code else code
        if base.isalpha() and 1 <= len(base) <= 5:
            return "US"
        return "A"

    def is_index_code(self, code: str) -> bool:
        """
        判断代码是否为指数代码（纯静态规则，不需要 API 调用）

        规则：
        - *.SI → 申万指数
        - *.CI → 中信指数
        - 399xxx.SZ → 深证指数系列
        - 000xxx.SH → 上证指数系列（上交所股票从 600 起，无 000 开头）
        - 9xxxxx.SH → 上证其他指数
        """
        code = code.strip().upper()
        if code.endswith('.SI') or code.endswith('.CI'):
            return True
        # 399xxx.SZ — 深证指数
        if re.match(r'^399\d{3}\.SZ$', code):
            return True
        # 000xxx.SH — 上证指数
        if re.match(r'^000\d{3}\.SH$', code):
            return True
        # 9xxxxx.SH — 上证其他指数
        if re.match(r'^9\d{5}\.SH$', code):
            return True
        return False

    def is_fund_code(self, code: str) -> bool:
        """
        判断代码是否为基金代码（纯静态规则，不需要 API 调用）

        规则：
        - *.OF → 场外基金
        - 5xxxxx.SH → 上交所 ETF
        - 1xxxxx.SZ → 深交所 ETF
        - 15xxxx.SZ → 深交所 ETF/LOF
        - 16xxxx.SZ → 深交所 LOF
        """
        code = code.strip().upper()
        # 场外基金
        if code.endswith('.OF'):
            return True
        # 上交所 ETF: 510xxx, 511xxx, 512xxx, 513xxx, 515xxx, 516xxx, 518xxx, 560xxx, 561xxx, 588xxx
        if re.match(r'^5[0-9]{5}\.SH$', code):
            return True
        # 深交所 ETF/LOF: 1xxxxx.SZ, 15xxxx.SZ, 16xxxx.SZ
        if re.match(r'^1[0-9]{5}\.SZ$', code):
            return True
        return False

    def get_index_daily_func(self, code: str):
        """
        根据指数代码返回对应的日线 API 函数

        - *.SI → sw_daily（申万行业指数）
        - *.CI → ci_daily（中信行业指数）
        - 其余指数 → index_daily
        """
        code = code.strip().upper()
        if code.endswith('.SI'):
            return self.pro.sw_daily
        if code.endswith('.CI'):
            return self.pro.ci_daily
        return self.pro.index_daily

    def __repr__(self) -> str:
        return f"TushareAPI(type={self.get_api_type()}, available={self.is_available()})"


async def fetch_daily_data(cache, api: 'TushareAPI', ts_code: str, cache_type: str = "daily", **kwargs):
    """
    统一日线数据获取：自动路由港股/美股/指数/A股 API，标准化列名

    - 港股：hk_daily，列名与 A 股一致
    - 美股：us_daily，pct_change → pct_chg，补齐 pre_close/change
    - 申万指数：sw_daily，pct_change → pct_chg，补齐 pre_close/change
    - 其他指数：index_daily / ci_daily
    - A 股：daily
    """
    market = api.get_market(ts_code)

    if market == "HK":
        return await cache.cached_call(api.pro.hk_daily, cache_type=cache_type, ts_code=ts_code, **kwargs)

    if market == "US":
        df = await cache.cached_call(api.pro.us_daily, cache_type=cache_type, ts_code=ts_code, **kwargs)
        if df is not None and not df.empty:
            if 'pct_change' in df.columns and 'pct_chg' not in df.columns:
                df = df.rename(columns={'pct_change': 'pct_chg'})
            for col in ['pre_close', 'change']:
                if col not in df.columns:
                    df[col] = None
        return df

    # A 股：走现有 fund/index/stock 路由
    if api.is_fund_code(ts_code):
        return await cache.cached_call(api.pro.fund_daily, cache_type=cache_type, ts_code=ts_code, **kwargs)
    elif api.is_index_code(ts_code):
        func = api.get_index_daily_func(ts_code)
        df = await cache.cached_call(func, cache_type=cache_type, ts_code=ts_code, **kwargs)
        if df is not None and not df.empty:
            # sw_daily 列名标准化
            if 'pct_change' in df.columns and 'pct_chg' not in df.columns:
                df = df.rename(columns={'pct_change': 'pct_chg'})
            for col in ['pre_close', 'change']:
                if col not in df.columns:
                    df[col] = None
        return df
    else:
        return await cache.cached_call(api.pro.daily, cache_type=cache_type, ts_code=ts_code, **kwargs)

