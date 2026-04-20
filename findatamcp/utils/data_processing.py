"""
数据处理工具函数

提供通用的数据处理和格式化功能，包括：
- 股票代码标准化
- 日期格式化与解析
- 交易日期容错处理
"""

from datetime import datetime, timedelta
from typing import Union, Tuple, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from ..utils.tushare_api import TushareAPI

logger = logging.getLogger(__name__)


def normalize_stock_code(code: str) -> str:
    """
    标准化股票代码为 Tushare 格式
    
    Args:
        code: 股票代码，如 '000001' 或 '000001.SZ'
        
    Returns:
        标准化后的代码，如 '000001.SZ'
    """
    code = code.strip()
    
    if '.' in code:
        return code
    
    if code.startswith('6'):
        return f"{code}.SH"
    elif code.startswith('8') or code.startswith('4'):
        return f"{code}.BJ"
    else:
        return f"{code}.SZ"


def format_date(date: Union[str, datetime], format: str = "%Y%m%d") -> str:
    """
    格式化日期为 Tushare 格式
    
    Args:
        date: 日期对象或字符串
        format: 输出格式，默认 YYYYMMDD
        
    Returns:
        格式化后的日期字符串
    """
    if isinstance(date, str):
        # 移除分隔符
        date = date.replace('-', '').replace('/', '')
        return date
    elif isinstance(date, datetime):
        return date.strftime(format)
    else:
        raise ValueError(f"Unsupported date type: {type(date)}")


def parse_tushare_date(date_str: str) -> datetime:
    """
    解析 Tushare 日期字符串为 datetime 对象

    Args:
        date_str: Tushare 日期字符串，如 '20231220'

    Returns:
        datetime 对象
    """
    return datetime.strptime(date_str, "%Y%m%d")


# ============================================================
# 🔥 日期容错工具 (P0-2)
# ============================================================

async def get_latest_trading_day(cache, api: "TushareAPI") -> str:
    """
    获取最近一个交易日

    Args:
        cache: TushareCache 实例
        api: TushareAPI 实例

    Returns:
        最近交易日 (YYYYMMDD)
    """
    try:
        today = datetime.now().strftime('%Y%m%d')
        check_start = (datetime.now() - timedelta(days=15)).strftime('%Y%m%d')

        # 使用交易日历 API
        cal_df = await cache.cached_call(
            api.pro.trade_cal,
            cache_type="basic",
            exchange='SSE',
            start_date=check_start,
            end_date=today,
            is_open='1'  # 只获取开市日
        )

        if not cal_df.empty:
            cal_df = cal_df.sort_values('cal_date', ascending=False)
            return cal_df['cal_date'].iloc[0]

        # 回退到今天
        return today

    except Exception as e:
        logger.warning(f"⚠️ [get_latest_trading_day] Failed: {e}")
        return datetime.now().strftime('%Y%m%d')


async def adjust_date_to_trading_day(
    cache,
    api: "TushareAPI",
    date: str
) -> Tuple[str, str]:
    """
    将日期调整到最近一个交易日

    当指定日期不是交易日（周末、节假日）或尚未开盘时，
    自动调整到最近一个有效交易日。

    Args:
        cache: TushareCache 实例
        api: TushareAPI 实例
        date: 原始日期 (YYYYMMDD)

    Returns:
        (adjusted_date, message): 调整后的日期和说明信息
    """
    try:
        date = date.replace('-', '')  # 兼容 YYYY-MM-DD 格式
        original_date = date
        check_start = (datetime.strptime(date, '%Y%m%d') - timedelta(days=15)).strftime('%Y%m%d')

        # 使用交易日历 API
        try:
            cal_df = await cache.cached_call(
                api.pro.trade_cal,
                cache_type="basic",
                exchange='SSE',
                start_date=check_start,
                end_date=date,
                is_open='1'
            )

            if not cal_df.empty:
                cal_df = cal_df.sort_values('cal_date', ascending=False)
                latest_trading_day = cal_df['cal_date'].iloc[0]

                if latest_trading_day != original_date:
                    logger.info(f"📅 [DateAdjust] Adjusted: {original_date} -> {latest_trading_day}")
                    return latest_trading_day, f"已自动调整到最近交易日: {original_date} -> {latest_trading_day}"

        except Exception as cal_err:
            logger.warning(f"⚠️ [DateAdjust] Calendar lookup failed: {cal_err}")

        # 回退：使用样本股票检测
        try:
            df = await cache.cached_call(
                api.pro.daily,
                cache_type="daily",
                ts_code="000001.SZ",  # 平安银行作为样本
                start_date=check_start,
                end_date=date
            )

            if not df.empty:
                df = df.sort_values('trade_date', ascending=False)
                latest_date = df['trade_date'].iloc[0]

                if latest_date != original_date:
                    logger.info(f"📅 [DateAdjust] Adjusted via sample: {original_date} -> {latest_date}")
                    return latest_date, f"已自动调整到最近交易日: {original_date} -> {latest_date}"

        except Exception as fallback_err:
            logger.warning(f"⚠️ [DateAdjust] Fallback failed: {fallback_err}")

        return date, ""

    except Exception as e:
        logger.error(f"❌ [DateAdjust] Error: {e}")
        return date, ""


async def validate_date_range(
    cache,
    api: "TushareAPI",
    start_date: str,
    end_date: str
) -> Tuple[str, str, str]:
    """
    验证并调整日期范围

    确保 start_date 和 end_date 都是有效交易日，
    并且 start_date <= end_date。

    Args:
        cache: TushareCache 实例
        api: TushareAPI 实例
        start_date: 开始日期 (YYYYMMDD)
        end_date: 结束日期 (YYYYMMDD)

    Returns:
        (adjusted_start, adjusted_end, message): 调整后的日期范围和说明
    """
    start_date = start_date.replace('-', '')  # 兼容 YYYY-MM-DD 格式
    end_date = end_date.replace('-', '')
    messages = []

    # 调整结束日期
    adjusted_end, end_msg = await adjust_date_to_trading_day(cache, api, end_date)
    if end_msg:
        messages.append(f"结束日期{end_msg}")

    # 调整开始日期（向后找第一个交易日）
    try:
        check_end = (datetime.strptime(start_date, '%Y%m%d') + timedelta(days=15)).strftime('%Y%m%d')

        cal_df = await cache.cached_call(
            api.pro.trade_cal,
            cache_type="basic",
            exchange='SSE',
            start_date=start_date,
            end_date=check_end,
            is_open='1'
        )

        if not cal_df.empty:
            cal_df = cal_df.sort_values('cal_date', ascending=True)
            adjusted_start = cal_df['cal_date'].iloc[0]

            if adjusted_start != start_date:
                logger.info(f"📅 [DateAdjust] Start adjusted: {start_date} -> {adjusted_start}")
                messages.append(f"开始日期已调整: {start_date} -> {adjusted_start}")
        else:
            adjusted_start = start_date

    except Exception as e:
        logger.warning(f"⚠️ [DateAdjust] Start date adjustment failed: {e}")
        adjusted_start = start_date

    # 确保 start <= end
    if adjusted_start > adjusted_end:
        adjusted_start, adjusted_end = adjusted_end, adjusted_start
        messages.append("已自动交换开始/结束日期")

    combined_message = "; ".join(messages) if messages else ""

    return adjusted_start, adjusted_end, combined_message


async def adjust_end_date_to_latest_trading_day(
    cache,
    api: "TushareAPI",
    end_date: str,
    sample_stock: str = "000001.SZ"
) -> Tuple[str, str]:
    """
    🔥 日期容错：将结束日期调整到最近一个有数据的交易日

    这是原 analysis.py 中的函数，现在提取为公共工具。
    当用户指定的结束日期（如今天）还没有数据时（未开盘或非交易日），
    自动调整到最近一个有效交易日。

    Args:
        cache: TushareCache 实例
        api: TushareAPI 实例
        end_date: 原始结束日期 (YYYYMMDD)
        sample_stock: 用于检测的样本股票代码

    Returns:
        (adjusted_end_date, message): 调整后的日期和说明信息
    """
    return await adjust_date_to_trading_day(cache, api, end_date)

