"""计算结果缓存

存储计算过程中产生的副产品数据，支持后续按需查询和派生计算。

设计思路：
1. analyze_price_correlation 计算相关性时，时间序列是副产品
2. 将副产品存储到缓存中，生成唯一的资源 ID
3. 通过资源 URI 可以查询存储的数据，并进行派生计算

资源 URI 格式：
- stock://calc_metrics/{calc_id}?{stock_a}_{stock_b}
- 例如：stock://calc_metrics/abc123?600519.SH_000858.SZ
"""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
import numpy as np
import pandas as pd


@dataclass
class CalcMetricsData:
    """计算指标数据（副产品）"""
    calc_id: str
    stock_codes: List[str]
    start_date: str
    end_date: str
    # 核心副产品：时间序列数据
    time_series: Dict[str, List[Dict[str, Any]]]  # {stock_code: [{date, close}, ...]}
    # 相关性矩阵（主产品）
    correlation_matrix: Dict[str, Dict[str, float]]
    # 元数据
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expires_at: str = field(default_factory=lambda: (datetime.now() + timedelta(hours=24)).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CalcMetricsData":
        return cls(**data)


class CalcMetricsCache:
    """计算指标缓存"""
    
    def __init__(self, max_size: int = 100):
        self._cache: Dict[str, CalcMetricsData] = {}
        self._max_size = max_size
    
    def _generate_calc_id(self, stock_codes: List[str], start_date: str, end_date: str) -> str:
        """生成计算 ID（基于输入参数的哈希）"""
        # 排序股票代码以确保一致性
        sorted_codes = sorted(stock_codes)
        key_str = f"{','.join(sorted_codes)}_{start_date}_{end_date}"
        return hashlib.md5(key_str.encode()).hexdigest()[:12]
    
    def store(
        self,
        stock_codes: List[str],
        start_date: str,
        end_date: str,
        time_series: Dict[str, List[Dict[str, Any]]],
        correlation_matrix: Dict[str, Dict[str, float]]
    ) -> str:
        """
        存储计算副产品
        
        Returns:
            calc_id: 计算 ID，用于构建资源 URI
        """
        calc_id = self._generate_calc_id(stock_codes, start_date, end_date)
        
        # 如果缓存满了，清理过期项
        if len(self._cache) >= self._max_size:
            self._cleanup_expired()
        
        # 存储数据
        self._cache[calc_id] = CalcMetricsData(
            calc_id=calc_id,
            stock_codes=stock_codes,
            start_date=start_date,
            end_date=end_date,
            time_series=time_series,
            correlation_matrix=correlation_matrix
        )
        
        return calc_id
    
    def get(self, calc_id: str) -> Optional[CalcMetricsData]:
        """获取存储的计算数据"""
        data = self._cache.get(calc_id)
        if data:
            # 检查是否过期
            if datetime.fromisoformat(data.expires_at) < datetime.now():
                del self._cache[calc_id]
                return None
        return data
    
    def get_pair_data(self, calc_id: str, stock_a: str, stock_b: str) -> Optional[Dict[str, Any]]:
        """
        获取指定股票对的数据
        
        Args:
            calc_id: 计算 ID
            stock_a: 股票A代码
            stock_b: 股票B代码
            
        Returns:
            包含时间序列和派生计算的数据
        """
        data = self.get(calc_id)
        if not data:
            return None
        
        # 查找匹配的股票代码
        ts_a = data.time_series.get(stock_a)
        ts_b = data.time_series.get(stock_b)
        
        if not ts_a or not ts_b:
            return None
        
        # 获取相关性
        correlation = None
        if stock_a in data.correlation_matrix:
            correlation = data.correlation_matrix[stock_a].get(stock_b)
        
        # 计算派生指标
        derived_metrics = self._calculate_derived_metrics(ts_a, ts_b)
        
        return {
            "calc_id": calc_id,
            "stock_a": stock_a,
            "stock_b": stock_b,
            "correlation": correlation,
            "time_series": {
                stock_a: ts_a,
                stock_b: ts_b
            },
            "derived_metrics": derived_metrics,
            "data_points": len(ts_a),
            "date_range": {
                "start": data.start_date,
                "end": data.end_date
            }
        }
    
    def _calculate_derived_metrics(
        self,
        ts_a: List[Dict[str, Any]],
        ts_b: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        计算派生指标（基于已有的时间序列数据）
        
        - 波动率
        - 最大回撤
        - 月度对比
        - 累计收益率
        """
        try:
            # 转换为 DataFrame
            df_a = pd.DataFrame(ts_a)
            df_b = pd.DataFrame(ts_b)
            
            if df_a.empty or df_b.empty:
                return {}
            
            # 确保有 close 列
            prices_a = df_a['close'].values
            prices_b = df_b['close'].values
            
            # 计算收益率
            returns_a = np.diff(prices_a) / prices_a[:-1]
            returns_b = np.diff(prices_b) / prices_b[:-1]
            
            metrics = {}
            
            # === 波动率（年化）===
            metrics["volatility"] = {
                "stock_a": float(np.std(returns_a) * np.sqrt(252) * 100) if len(returns_a) > 0 else None,
                "stock_b": float(np.std(returns_b) * np.sqrt(252) * 100) if len(returns_b) > 0 else None,
                "unit": "%"
            }
            
            # === 最大回撤 ===
            def calc_max_drawdown(prices):
                peak = np.maximum.accumulate(prices)
                drawdown = (peak - prices) / peak
                return float(np.max(drawdown) * 100)
            
            metrics["max_drawdown"] = {
                "stock_a": calc_max_drawdown(prices_a) if len(prices_a) > 0 else None,
                "stock_b": calc_max_drawdown(prices_b) if len(prices_b) > 0 else None,
                "unit": "%"
            }
            
            # === 累计收益率 ===
            metrics["total_return"] = {
                "stock_a": float((prices_a[-1] / prices_a[0] - 1) * 100) if len(prices_a) > 0 else None,
                "stock_b": float((prices_b[-1] / prices_b[0] - 1) * 100) if len(prices_b) > 0 else None,
                "unit": "%"
            }
            
            # === 月度收益对比 ===
            if 'date' in df_a.columns:
                df_a['date'] = pd.to_datetime(df_a['date'], format='%Y%m%d')
                df_a['month'] = df_a['date'].dt.to_period('M')
                monthly_a = df_a.groupby('month')['close'].agg(['first', 'last'])
                monthly_a['return'] = (monthly_a['last'] / monthly_a['first'] - 1) * 100
                
                df_b['date'] = pd.to_datetime(df_b['date'], format='%Y%m%d')
                df_b['month'] = df_b['date'].dt.to_period('M')
                monthly_b = df_b.groupby('month')['close'].agg(['first', 'last'])
                monthly_b['return'] = (monthly_b['last'] / monthly_b['first'] - 1) * 100
                
                # 取最近6个月
                recent_months = sorted(set(monthly_a.index) & set(monthly_b.index))[-6:]
                
                metrics["monthly_comparison"] = [
                    {
                        "month": str(m),
                        "stock_a": round(float(monthly_a.loc[m, 'return']), 2),
                        "stock_b": round(float(monthly_b.loc[m, 'return']), 2)
                    }
                    for m in recent_months
                ]
            
            # === 夏普比率（假设无风险利率 3%）===
            rf_daily = 0.03 / 252
            if len(returns_a) > 0:
                sharpe_a = (np.mean(returns_a) - rf_daily) / np.std(returns_a) * np.sqrt(252)
                metrics["sharpe_ratio"] = metrics.get("sharpe_ratio", {})
                metrics["sharpe_ratio"]["stock_a"] = float(sharpe_a)
            if len(returns_b) > 0:
                sharpe_b = (np.mean(returns_b) - rf_daily) / np.std(returns_b) * np.sqrt(252)
                metrics["sharpe_ratio"] = metrics.get("sharpe_ratio", {})
                metrics["sharpe_ratio"]["stock_b"] = float(sharpe_b)
            
            return metrics
            
        except Exception as e:
            return {"error": str(e)}
    
    def _cleanup_expired(self):
        """清理过期的缓存项"""
        now = datetime.now()
        expired_keys = [
            k for k, v in self._cache.items()
            if datetime.fromisoformat(v.expires_at) < now
        ]
        for k in expired_keys:
            del self._cache[k]


# 全局缓存实例
calc_metrics_cache = CalcMetricsCache()

