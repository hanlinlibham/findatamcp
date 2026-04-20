"""
技术指标计算模块

从 tushare_collector_full.py 迁移的所有 _calculate_* 函数
提供纯函数形式的计算逻辑，便于在各工具模块中使用

包含：
- 趋势指标：MA, MACD, Bollinger Bands, DMI
- 动量指标：RSI, KDJ, CCI, ROC, TRIX
- 能量指标：OBV, SOBV, EMV, 量比
- 波动率指标：ATR, 历史波动率
- 风险指标：Beta, 最大回撤, Sharpe, Sortino, VaR
- 强弱指标：相对强弱
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, Tuple


def calculate_rsi(prices: pd.Series, period: int = 14) -> float:
    """计算RSI指标"""
    try:
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) if not rsi.empty else 0.0
    except:
        return 0.0


def calculate_macd(prices: pd.Series) -> Dict[str, float]:
    """计算MACD指标"""
    try:
        ema12 = prices.ewm(span=12).mean()
        ema26 = prices.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        histogram = macd - signal

        return {
            "macd": float(macd.iloc[-1]) if not macd.empty else 0.0,
            "signal": float(signal.iloc[-1]) if not signal.empty else 0.0,
            "histogram": float(histogram.iloc[-1]) if not histogram.empty else 0.0
        }
    except:
        return {"macd": 0.0, "signal": 0.0, "histogram": 0.0}


def calculate_bollinger_bands(prices: pd.Series, period: int = 20) -> Dict[str, float]:
    """计算布林带指标"""
    try:
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper_band = sma + (std * 2)
        lower_band = sma - (std * 2)

        return {
            "upper_band": float(upper_band.iloc[-1]) if not upper_band.empty else 0.0,
            "middle_band": float(sma.iloc[-1]) if not sma.empty else 0.0,
            "lower_band": float(lower_band.iloc[-1]) if not lower_band.empty else 0.0
        }
    except:
        return {"upper_band": 0.0, "middle_band": 0.0, "lower_band": 0.0}


def calculate_kdj(df: pd.DataFrame, period: int = 9) -> Dict[str, float]:
    """计算KDJ指标"""
    try:
        high_prices = df['high'].values
        low_prices = df['low'].values
        close_prices = df['close'].values

        # 计算最高价和最低价
        highest = np.array([np.max(high_prices[max(0, i-period+1):i+1]) for i in range(len(high_prices))])
        lowest = np.array([np.min(low_prices[max(0, i-period+1):i+1]) for i in range(len(low_prices))])

        # 计算RSV
        rsv = (close_prices - lowest) / (highest - lowest) * 100

        # 计算K值
        k_values = []
        k = 50  # 初始K值
        for rsv_val in rsv:
            if not np.isnan(rsv_val):
                k = (2/3) * k + (1/3) * rsv_val
            k_values.append(k)

        # 计算D值
        d_values = []
        d = 50  # 初始D值
        for k_val in k_values:
            if not np.isnan(k_val):
                d = (2/3) * d + (1/3) * k_val
            d_values.append(d)

        # 计算J值
        j_values = [3 * k - 2 * d for k, d in zip(k_values, d_values)]

        return {
            'kdj_k': k_values[-1] if k_values else None,
            'kdj_d': d_values[-1] if d_values else None,
            'kdj_j': j_values[-1] if j_values else None
        }

    except Exception as e:
        return {'kdj_k': None, 'kdj_d': None, 'kdj_j': None}


def calculate_williams(df: pd.DataFrame, period: int = 14) -> float:
    """计算威廉指标"""
    try:
        high_prices = df['high'].values
        low_prices = df['low'].values
        close_prices = df['close'].values

        if len(high_prices) < period:
            return None

        # 计算最近N期的最高价和最低价
        highest = np.max(high_prices[-period:])
        lowest = np.min(low_prices[-period:])

        # 计算威廉指标
        williams = (highest - close_prices[-1]) / (highest - lowest) * 100

        return williams

    except Exception as e:
        return None


def calculate_cci(df: pd.DataFrame, period: int = 20) -> float:
    """计算CCI指标"""
    try:
        high_prices = df['high'].values
        low_prices = df['low'].values
        close_prices = df['close'].values

        if len(high_prices) < period:
            return None

        # 计算典型价格
        typical_price = (high_prices + low_prices + close_prices) / 3

        # 计算移动平均
        ma_tp = np.mean(typical_price[-period:])

        # 计算平均绝对偏差
        mad = np.mean(np.abs(typical_price[-period:] - ma_tp))

        # 计算CCI
        cci = (typical_price[-1] - ma_tp) / (0.015 * mad)

        return cci

    except Exception as e:
        return None


def calculate_roc(prices: pd.Series, period: int = 12) -> float:
    """计算ROC指标"""
    try:
        if len(prices) < period + 1:
            return None

        current_price = prices.iloc[-1]
        past_price = prices.iloc[-period-1]

        roc = (current_price - past_price) / past_price * 100

        return roc

    except Exception as e:
        return None


def calculate_trix(prices: pd.Series, period: int = 14) -> float:
    """计算TRIX指标"""
    try:
        if len(prices) < period * 3:
            return None

        # 三重指数平滑
        ema1 = prices.ewm(span=period).mean()
        ema2 = ema1.ewm(span=period).mean()
        ema3 = ema2.ewm(span=period).mean()

        # 计算TRIX
        trix = ema3.pct_change() * 10000

        return trix.iloc[-1]

    except Exception as e:
        return None


def calculate_obv(df: pd.DataFrame) -> float:
    """计算OBV指标"""
    try:
        close_prices = df['close'].values
        volumes = df['vol'].values

        obv = 0
        for i in range(1, len(close_prices)):
            if close_prices[i] > close_prices[i-1]:
                obv += volumes[i]
            elif close_prices[i] < close_prices[i-1]:
                obv -= volumes[i]
            # 价格相等时OBV不变

        return obv

    except Exception as e:
        return None


def calculate_sobv(df: pd.DataFrame, period: int = 20) -> float:
    """计算SOBV指标"""
    try:
        close_prices = df['close'].values
        volumes = df['vol'].values

        if len(close_prices) < period:
            return None

        # 计算OBV序列
        obv_values = []
        obv = 0

        for i in range(1, len(close_prices)):
            if close_prices[i] > close_prices[i-1]:
                obv += volumes[i]
            elif close_prices[i] < close_prices[i-1]:
                obv -= volumes[i]
            obv_values.append(obv)

        # 计算SOBV（OBV的移动平均）
        sobv = np.mean(obv_values[-period:])

        return sobv

    except Exception as e:
        return None


def calculate_emv(df: pd.DataFrame, period: int = 14) -> float:
    """计算EMV指标"""
    try:
        high_prices = df['high'].values
        low_prices = df['low'].values
        volumes = df['vol'].values

        if len(high_prices) < period + 1:
            return None

        # 计算价格移动和成交量比率
        emv_values = []
        for i in range(1, len(high_prices)):
            distance_moved = (high_prices[i] + low_prices[i]) / 2 - (high_prices[i-1] + low_prices[i-1]) / 2
            high_low = high_prices[i] - low_prices[i]

            if high_low > 0 and volumes[i] > 0:
                emv = distance_moved * volumes[i] / high_low
            else:
                emv = 0

            emv_values.append(emv)

        # 计算EMV移动平均
        emv_ma = np.mean(emv_values[-period:])

        return emv_ma

    except Exception as e:
        return None


def calculate_volume_ratio(df: pd.DataFrame) -> float:
    """计算量比"""
    try:
        volume_col = 'vol' if 'vol' in df.columns else 'volume'
        if volume_col in df.columns and len(df) > 5:
            current_volume = df[volume_col].iloc[-1]
            avg_volume = df[volume_col].rolling(window=5).mean().iloc[-1]
            return float(current_volume / avg_volume) if avg_volume > 0 else 0.0
    except:
        pass
    return 0.0


def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """计算ATR指标"""
    try:
        high_prices = df['high'].values
        low_prices = df['low'].values
        close_prices = df['close'].values

        if len(high_prices) < period + 1:
            return None

        # 计算真实波幅
        tr_values = []
        for i in range(1, len(high_prices)):
            tr = max(
                high_prices[i] - low_prices[i],
                abs(high_prices[i] - close_prices[i-1]),
                abs(low_prices[i] - close_prices[i-1])
            )
            tr_values.append(tr)

        # 计算ATR
        atr = np.mean(tr_values[-period:])

        return atr

    except Exception as e:
        return None


def calculate_beta(df: pd.DataFrame) -> float:
    """计算Beta系数（简化版，相对于市场）"""
    try:
        close_prices = df['close'].values

        if len(close_prices) < 60:
            return None

        # 计算股票收益率
        returns = np.diff(np.log(close_prices))

        # 简化版本：假设市场收益率为0.1%/天
        market_returns = np.full_like(returns, 0.001)

        # 计算Beta
        covariance = np.cov(returns, market_returns)[0][1]
        market_variance = np.var(market_returns)

        beta = covariance / market_variance if market_variance > 0 else 1.0

        return beta

    except Exception as e:
        return None


def calculate_max_drawdown(prices: np.ndarray) -> float:
    """计算最大回撤"""
    try:
        if len(prices) < 2:
            return None

        # 计算累计收益
        cumulative = np.cumprod(1 + np.diff(prices) / prices[:-1])

        # 计算回撤
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max

        # 最大回撤
        max_drawdown = np.min(drawdown)

        return abs(max_drawdown)

    except Exception as e:
        return None


def calculate_sharpe_ratio(returns: np.ndarray, risk_free_rate: float = 0.03) -> float:
    """计算夏普比率"""
    try:
        if len(returns) < 2:
            return None

        # 年化收益率
        annual_return = np.mean(returns) * 252

        # 年化波动率
        annual_volatility = np.std(returns) * np.sqrt(252)

        # 夏普比率
        sharpe_ratio = (annual_return - risk_free_rate) / annual_volatility if annual_volatility > 0 else 0

        return sharpe_ratio

    except Exception as e:
        return None


def calculate_var(returns: np.ndarray, confidence_level: float = 0.95) -> float:
    """计算VaR"""
    try:
        if len(returns) < 10:
            return None

        # 计算VaR
        var = np.percentile(returns, (1 - confidence_level) * 100)

        return abs(var)

    except Exception as e:
        return None


def calculate_downside_risk(returns: np.ndarray, target_return: float = 0) -> float:
    """计算下行风险"""
    try:
        if len(returns) < 2:
            return None

        # 计算下行偏差
        downside_returns = returns[returns < target_return]

        if len(downside_returns) == 0:
            return 0

        downside_risk = np.std(downside_returns) * np.sqrt(252)

        return downside_risk

    except Exception as e:
        return None


def calculate_risk_adjusted_return(returns: np.ndarray) -> float:
    """计算风险调整收益"""
    try:
        if len(returns) < 2:
            return None

        # 年化收益率
        annual_return = np.mean(returns) * 252

        # 年化波动率
        annual_volatility = np.std(returns) * np.sqrt(252)

        # 风险调整收益
        risk_adjusted_return = annual_return / annual_volatility if annual_volatility > 0 else 0

        return risk_adjusted_return

    except Exception as e:
        return None


def calculate_relative_strength(df: pd.DataFrame) -> float:
    """计算相对强弱（相对于市场）"""
    try:
        close_prices = df['close'].values

        if len(close_prices) < 60:
            return None

        # 计算60日涨幅
        stock_return = (close_prices[-1] / close_prices[-60] - 1) * 100

        # 简化版本：假设市场60日涨幅为5%
        market_return = 5.0

        # 相对强弱
        relative_strength = stock_return - market_return

        return relative_strength

    except Exception as e:
        return None


def calculate_dmi(df: pd.DataFrame, period: int = 14) -> Dict[str, float]:
    """计算DMI指标"""
    try:
        high_prices = df['high'].values
        low_prices = df['low'].values
        close_prices = df['close'].values

        if len(high_prices) < period + 1:
            return {'dmi_pdi': None, 'dmi_mdi': None, 'dmi_adx': None}

        # 计算真实波幅（TR）
        tr_values = []
        for i in range(1, len(high_prices)):
            tr = max(
                high_prices[i] - low_prices[i],
                abs(high_prices[i] - close_prices[i-1]),
                abs(low_prices[i] - close_prices[i-1])
            )
            tr_values.append(tr)

        # 计算+DM和-DM
        pdm_values = []
        mdm_values = []
        for i in range(1, len(high_prices)):
            up_move = high_prices[i] - high_prices[i-1]
            down_move = low_prices[i-1] - low_prices[i]

            if up_move > down_move and up_move > 0:
                pdm = up_move
            else:
                pdm = 0

            if down_move > up_move and down_move > 0:
                mdm = down_move
            else:
                mdm = 0

            pdm_values.append(pdm)
            mdm_values.append(mdm)

        # 计算平滑的TR、+DM、-DM
        atr = np.mean(tr_values[-period:])
        apdm = np.mean(pdm_values[-period:])
        amdm = np.mean(mdm_values[-period:])

        # 计算+DI和-DI
        pdi = (apdm / atr) * 100 if atr > 0 else 0
        mdi = (amdm / atr) * 100 if atr > 0 else 0

        # 计算ADX
        dx = abs(pdi - mdi) / (pdi + mdi) * 100 if (pdi + mdi) > 0 else 0
        # 简化版本的ADX（实际需要更复杂的计算）
        adx = dx

        return {
            'dmi_pdi': pdi,
            'dmi_mdi': mdi,
            'dmi_adx': adx
        }

    except Exception as e:
        return {'dmi_pdi': None, 'dmi_mdi': None, 'dmi_adx': None}


# 移动平均线计算
def calculate_moving_averages(prices: pd.Series, periods: list = [5, 10, 20, 60]) -> Dict[str, float]:
    """计算多个周期的移动平均线"""
    result = {}
    for period in periods:
        if len(prices) >= period:
            ma = np.mean(prices[-period:])
            result[f'ma_{period}'] = float(ma)
        else:
            result[f'ma_{period}'] = None
    return result


# 估值指标计算（需要TushareAPI实例）
def calculate_pe_percentile(ts_code: str, api) -> float:
    """计算PE(TTM)历史分位数（3年数据）"""
    try:
        if api and hasattr(api, 'pro') and api.pro:
            df = api.pro.daily_basic(ts_code=ts_code, fields='trade_date,pe_ttm', limit=750)
            if not df.empty and 'pe_ttm' in df.columns:
                df = df.dropna(subset=['pe_ttm'])
                if len(df) > 0:
                    current_pe = df['pe_ttm'].iloc[0]
                    pe_percentile = (df['pe_ttm'] < current_pe).sum() / len(df) * 100
                    return float(pe_percentile)
    except:
        pass
    return 0.0


def calculate_pb_percentile(ts_code: str, api) -> float:
    """计算PB历史分位数（3年数据）"""
    try:
        if api and hasattr(api, 'pro') and api.pro:
            df = api.pro.daily_basic(ts_code=ts_code, fields='trade_date,pb', limit=750)
            if not df.empty and 'pb' in df.columns:
                df = df.dropna(subset=['pb'])
                if len(df) > 0:
                    current_pb = df['pb'].iloc[0]
                    pb_percentile = (df['pb'] < current_pb).sum() / len(df) * 100
                    return float(pb_percentile)
    except:
        pass
    return 0.0


def calculate_dividend_yield(ts_code: str, api) -> float:
    """计算股息率"""
    try:
        if api and hasattr(api, 'pro') and api.pro:
            # 获取分红数据
            dividend_df = api.pro.dividend(ts_code=ts_code, limit=1)
            daily_df = api.pro.daily(ts_code=ts_code, limit=1)

            if not dividend_df.empty and not daily_df.empty:
                dividend = dividend_df['cash_div'].iloc[0]
                price = daily_df['close'].iloc[0]
                return float(dividend / price * 100) if price > 0 else 0.0
    except:
        pass
    return 0.0
