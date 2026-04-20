#!/usr/bin/env python3
"""
完整的Tushare数据收集器
基于Tushare Pro API，集成所有必要的股票数据接口
"""

import tushare as ts
import pandas as pd
import numpy as np
import os
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import logging

import logging

def setup_logger(name):
    """创建简单的logger"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

import os

class Settings:
    """简单的配置类"""
    def __init__(self):
        self.TUSHARE_TOKEN = os.getenv('TUSHARE_TOKEN')

settings = Settings()

def normalize_stock_code(stock_code: str) -> str:
    """标准化股票代码为Tushare格式"""
    code = stock_code.strip()
    if '.' in code:
        return code
    if code.startswith('6'):
        return f"{code}.SH"
    elif code.startswith('8') or code.startswith('4'):
        return f"{code}.BJ"
    else:
        return f"{code}.SZ"


logger = setup_logger(__name__)


class TushareDataCollector:
    """
    完整的Tushare数据收集器
    集成基础数据、行情数据、财务数据、技术指标等
    """
    
    def __init__(self, token: Optional[str] = None):
        """
        初始化Tushare数据收集器
        
        Args:
            token: Tushare Pro API token
        """
        # 尝试从多个来源获取token
        
        self.token = token or settings.TUSHARE_TOKEN or os.getenv('TUSHARE_TOKEN')
        self.pro = None
        
        # 初始化Tushare Pro
        if self.token:
            try:
                ts.set_token(self.token)
                self.pro = ts.pro_api(self.token)
                logger.info("✅ Tushare Pro API 初始化成功")
                
                # 测试连接
                test_df = self.pro.stock_basic(list_status='L', limit=1)
                if not test_df.empty:
                    logger.info("🔗 Tushare Pro API 连接测试成功")
                else:
                    logger.warning("⚠️ Tushare Pro API 连接测试返回空数据")
                    
            except Exception as e:
                logger.error(f"❌ Tushare Pro API 初始化失败: {e}")
                logger.info("📦 回退到免费版Tushare接口")
                self.pro = None
        else:
            logger.warning("⚠️ 未提供Tushare Pro token，请设置环境变量 TUSHARE_TOKEN")
            logger.info("📦 使用免费版Tushare接口（功能受限）")
    
    async def collect_comprehensive_data(self, stock_code: str) -> Dict[str, Any]:
        """
        收集股票的核心数据 - 优化版本，减少API调用
        
        Args:
            stock_code: 股票代码 (如 '000001')
            
        Returns:
            包含核心数据的字典
        """
        logger.info(f"🚀 开始收集 {stock_code} 的核心数据（优化版本）")
        
        # 标准化股票代码
        ts_code = self._normalize_stock_code(stock_code)
        
        comprehensive_data = {
            "stock_code": stock_code,
            "ts_code": ts_code,
            "collection_time": datetime.now().isoformat(),
            "data_source": "tushare_pro" if self.pro else "tushare_free",
            "api_status": "pro" if self.pro else "free"
        }
        
        try:
            # 🔧 只收集核心必要数据，减少API调用
            
            # 1. 实时行情数据（最重要）
            logger.info("📊 收集实时行情数据")
            realtime_data = await self._get_realtime_data(stock_code)
            comprehensive_data["realtime_data"] = realtime_data
            
            # 添加短暂延迟，避免API频率限制
            await asyncio.sleep(0.2)
            
            # 2. 历史行情数据（关键技术分析数据）
            logger.info("📈 收集历史行情关键指标")
            daily_data = await self._get_daily_data(ts_code, days=60)  # 减少到60天
            comprehensive_data["daily_data"] = daily_data
            
            # 添加延迟
            await asyncio.sleep(0.2)
            
            # 3. 基础信息（如果实时数据中没有）
            if not realtime_data or realtime_data.get("error"):
                logger.info("📋 收集基础信息")
                basic_info = await self._get_basic_info(ts_code)
                comprehensive_data["basic_info"] = basic_info
                await asyncio.sleep(0.2)
            else:
                logger.info("✅ 跳过基础信息（已从实时数据获取）")
                comprehensive_data["basic_info"] = {"source": "realtime_data"}
            
            # 4. 财务数据（简化版本）
            logger.info("💰 收集核心财务指标")
            financial_data = await self._get_simplified_financial_data(ts_code)
            comprehensive_data["financial_data"] = financial_data
            
            # 🔧 删除不必要的数据收集，避免API限制
            # - 技术指标（可以从历史数据计算）
            # - 估值数据（可以从基本面计算）  
            # - 资金流向（非核心）
            # - 分红送股（非核心）
            
            logger.info("✅ 核心数据收集完成，跳过非必要数据以避免API限制")
            
            logger.info(f"✅ {stock_code} 综合数据收集完成")
            return comprehensive_data
            
        except Exception as e:
            logger.error(f"❌ 收集 {stock_code} 数据失败: {e}")
            comprehensive_data["error"] = str(e)
            return comprehensive_data
    
    def _normalize_stock_code(self, stock_code: str) -> str:
        """
        标准化股票代码为Tushare格式 - 使用统一的转换函数
        
        Args:
            stock_code: 原始股票代码
            
        Returns:
            标准化后的股票代码
        """
        
        return normalize_stock_code(stock_code)
    
    async def _get_basic_info(self, ts_code: str) -> Dict[str, Any]:
        """获取股票基础信息"""
        try:
            if self.pro:
                # 使用Pro API
                df = self.pro.stock_basic(
                    ts_code=ts_code, 
                    fields='ts_code,symbol,name,area,industry,fullname,enname,market,exchange,curr_type,list_status,list_date,delist_date,is_hs'
                )
                
                if not df.empty:
                    basic_info = df.iloc[0].to_dict()
                    
                    # 获取公司基本信息
                    company_df = self.pro.stock_company(ts_code=ts_code)
                    if not company_df.empty:
                        company_info = company_df.iloc[0].to_dict()
                        basic_info.update({
                            'chairman': company_info.get('chairman', ''),
                            'manager': company_info.get('manager', ''),
                            'secretary': company_info.get('secretary', ''),
                            'reg_capital': company_info.get('reg_capital', ''),
                            'setup_date': company_info.get('setup_date', ''),
                            'province': company_info.get('province', ''),
                            'city': company_info.get('city', ''),
                            'introduction': company_info.get('introduction', '')
                        })
                    
                    return basic_info
            else:
                # 使用免费API（已废弃，但作为备用）
                stock_code = ts_code.split('.')[0]
                try:
                    df = ts.get_stock_basics()
                    if df is not None and stock_code in df.index:
                        basic_info = df.loc[stock_code].to_dict()
                        basic_info['ts_code'] = ts_code
                        basic_info['symbol'] = stock_code
                        return basic_info
                except Exception as e:
                    logger.warning(f"免费API获取基础信息失败: {e}")
                    
        except Exception as e:
            logger.error(f"获取基础信息失败: {e}")
            
        return {"ts_code": ts_code, "error": "无法获取基础信息"}
    
    async def _get_realtime_data(self, stock_code: str) -> Dict[str, Any]:
        """获取实时行情数据 - 优化非工作日处理"""
        try:
            if self.pro:
                # Pro版本没有直接的实时数据接口，使用最新的日线数据
                ts_code = self._normalize_stock_code(stock_code)
                
                # 🔧 优化：使用多重降级策略获取数据
                df = None
                data_source = "unknown"
                
                # 策略1：尝试获取今日数据
                try:
                    today = datetime.now().strftime('%Y%m%d')
                    df = self.pro.daily(ts_code=ts_code, trade_date=today)
                    if not df.empty:
                        data_source = f"today_{today}"
                        logger.info(f"✅ 获取到今日数据: {today}")
                except Exception as e:
                    logger.warning(f"获取今日数据失败: {e}")
                
                # 策略2：如果今日无数据，获取最近交易日数据  
                if df is None or df.empty:
                    try:
                        df = self.pro.daily(ts_code=ts_code, limit=1)
                        if not df.empty:
                            trade_date = df.iloc[0]['trade_date']
                            data_source = f"latest_{trade_date}"
                            logger.info(f"✅ 使用最近交易日数据: {trade_date}")
                    except Exception as e:
                        logger.warning(f"获取最近交易日数据失败: {e}")
                
                # 策略3：如果还是失败，尝试获取最近5个交易日的数据
                if df is None or df.empty:
                    try:
                        end_date = datetime.now().strftime('%Y%m%d')
                        start_date = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')
                        df = self.pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                        if not df.empty:
                            # 取最新的一条记录
                            df = df.sort_values('trade_date').tail(1)
                            trade_date = df.iloc[0]['trade_date']
                            data_source = f"recent_{trade_date}"
                            logger.info(f"✅ 使用近期数据: {trade_date}")
                    except Exception as e:
                        logger.warning(f"获取近期数据失败: {e}")
                
                if df is not None and not df.empty:
                    latest_data = df.iloc[0].to_dict()
                    
                    # 🔧 添加数据来源和时效性信息
                    current_time = datetime.now()
                    trade_date_str = latest_data.get('trade_date', '')
                    
                    # 判断数据新鲜度
                    is_fresh = False
                    days_old = 0
                    if trade_date_str:
                        try:
                            trade_date = datetime.strptime(str(trade_date_str), '%Y%m%d')
                            days_old = (current_time - trade_date).days
                            is_fresh = days_old <= 1  # 1天内的数据认为是新鲜的
                        except:
                            pass
                    
                    # 转换为实时数据格式
                    realtime_info = {
                        'code': stock_code,
                        'name': stock_code,  # 会在基础信息中补充
                        'price': latest_data.get('close', 0),
                        'open': latest_data.get('open', 0),
                        'high': latest_data.get('high', 0),
                        'low': latest_data.get('low', 0),
                        'pre_close': latest_data.get('pre_close', 0),
                        'volume': latest_data.get('vol', 0),
                        'amount': latest_data.get('amount', 0),
                        'changepercent': latest_data.get('pct_chg', 0),
                        'trade_date': trade_date_str,
                        'turnover_rate': latest_data.get('turnover_rate', 0),
                        # 🔧 新增：数据质量标识
                        'data_source': data_source,
                        'data_freshness': 'fresh' if is_fresh else 'stale',
                        'days_old': days_old,
                        'is_trading_day': is_fresh,
                        'last_updated': current_time.isoformat()
                    }
                    
                    return realtime_info
            else:
                # 使用免费API获取实时数据
                df = ts.get_realtime_quotes(stock_code)
                
                if not df.empty:
                    realtime_info = df.iloc[0].to_dict()
                    
                    # 数据类型转换
                    numeric_fields = ['price', 'open', 'high', 'low', 'pre_close', 
                                    'volume', 'amount', 'bid', 'ask', 'b1_v', 'b1_p',
                                    'a1_v', 'a1_p', 'b2_v', 'b2_p', 'a2_v', 'a2_p',
                                    'b3_v', 'b3_p', 'a3_v', 'a3_p', 'b4_v', 'b4_p',
                                    'a4_v', 'a4_p', 'b5_v', 'b5_p', 'a5_v', 'a5_p']
                    
                    for field in numeric_fields:
                        if field in realtime_info:
                            try:
                                realtime_info[field] = float(realtime_info[field])
                            except (ValueError, TypeError):
                                realtime_info[field] = 0.0
                    
                    return realtime_info
                
        except Exception as e:
            logger.error(f"获取实时数据失败: {e}")
            
        return {"error": "无法获取实时数据"}
    
    async def _get_daily_data(self, ts_code: str, days: int = 250) -> Dict[str, Any]:
        """获取历史日线数据 - 优化版本，只保留关键统计信息"""
        try:
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
            
            if self.pro:
                # 使用Pro API
                df = self.pro.daily(
                    ts_code=ts_code, 
                    start_date=start_date, 
                    end_date=end_date,
                    fields='ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount'
                )
                
                if not df.empty:
                    df = df.sort_values('trade_date')
                    
                    # 只保留关键统计信息，不保留完整的日频序列
                    latest_data = df.iloc[-1].to_dict() if not df.empty else {}
                    
                    # 计算关键统计指标
                    price_stats = {
                        "max_price_250d": df['high'].max(),
                        "min_price_250d": df['low'].min(),
                        "avg_price_250d": df['close'].mean(),
                        "price_volatility_250d": df['pct_chg'].std(),
                        "max_single_day_gain": df['pct_chg'].max(),
                        "max_single_day_loss": df['pct_chg'].min(),
                        "positive_days_ratio": (df['pct_chg'] > 0).sum() / len(df),
                        "avg_volume_250d": df['vol'].mean(),
                        "max_volume_250d": df['vol'].max(),
                        "total_amount_250d": df['amount'].sum()
                    }
                    
                    # 计算趋势信息
                    trend_stats = {
                        "trend_250d": "上升" if df['close'].iloc[-1] > df['close'].iloc[0] else "下降",
                        "price_change_250d": ((df['close'].iloc[-1] / df['close'].iloc[0]) - 1) * 100,
                        "recent_30d_change": ((df['close'].iloc[-1] / df['close'].iloc[-30]) - 1) * 100 if len(df) >= 30 else 0,
                        "recent_7d_change": ((df['close'].iloc[-1] / df['close'].iloc[-7]) - 1) * 100 if len(df) >= 7 else 0
                    }
                    
                    return {
                        "latest_data": latest_data,
                        "price_statistics": price_stats,
                        "trend_statistics": trend_stats,
                        "data_count": len(df),
                        "start_date": start_date,
                        "end_date": end_date,
                        "data_quality": "complete" if len(df) > 200 else "partial"
                    }
            else:
                # 使用免费API
                stock_code = ts_code.split('.')[0]
                start_str = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
                end_str = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"
                
                df = ts.get_hist_data(stock_code, start=start_str, end=end_str)
                
                if df is not None and not df.empty:
                    df = df.sort_index()
                    
                    # 只保留关键统计信息
                    latest_data = df.iloc[-1].to_dict() if not df.empty else {}
                    
                    # 计算关键统计指标（免费版）
                    price_stats = {
                        "max_price_250d": df['high'].max(),
                        "min_price_250d": df['low'].min(),
                        "avg_price_250d": df['close'].mean(),
                        "price_volatility_250d": df['p_change'].std() if 'p_change' in df.columns else 0,
                        "avg_volume_250d": df['volume'].mean() if 'volume' in df.columns else 0,
                    }
                    
                    return {
                        "latest_data": latest_data,
                        "price_statistics": price_stats,
                        "data_count": len(df),
                        "start_date": start_date,
                        "end_date": end_date,
                        "data_quality": "basic"
                    }
                    
        except Exception as e:
            logger.error(f"获取历史数据失败: {e}")
            
        return {"error": "无法获取历史数据"}
    
    async def _get_simplified_financial_data(self, ts_code: str) -> Dict[str, Any]:
        """获取简化的财务数据 - 减少API调用"""
        try:
            financial_data = {}
            
            if self.pro:
                # 🔧 只获取最重要的财务指标，减少API调用
                logger.info("📊 获取核心财务指标（简化版本）")
                
                # 添加延迟
                await asyncio.sleep(0.3)
                
                # 只获取最新的年报或季报数据
                try:
                    # 获取最近一年的利润表核心数据
                    income_df = self.pro.income(ts_code=ts_code, limit=1, fields='ts_code,end_date,total_revenue,total_profit,n_income')
                    if not income_df.empty:
                        latest_income = income_df.iloc[0].to_dict()
                        financial_data["income_core"] = {
                            "total_revenue": latest_income.get('total_revenue', 0),
                            "total_profit": latest_income.get('total_profit', 0),
                            "net_income": latest_income.get('n_income', 0),
                            "end_date": latest_income.get('end_date', '')
                        }
                        logger.info("✅ 核心利润表数据获取成功")
                    
                    # 添加延迟
                    await asyncio.sleep(0.3)
                    
                    # 获取资产负债表核心数据
                    balance_df = self.pro.balancesheet(ts_code=ts_code, limit=1, fields='ts_code,end_date,total_assets,total_hldr_eqy_exc_min_int')
                    if not balance_df.empty:
                        latest_balance = balance_df.iloc[0].to_dict()
                        financial_data["balance_core"] = {
                            "total_assets": latest_balance.get('total_assets', 0),
                            "total_equity": latest_balance.get('total_hldr_eqy_exc_min_int', 0),
                            "end_date": latest_balance.get('end_date', '')
                        }
                        logger.info("✅ 核心资产负债表数据获取成功")
                        
                except Exception as e:
                    logger.warning(f"⚠️ 获取核心财务数据失败: {e}")
                    financial_data["error"] = f"简化财务数据获取失败: {str(e)}"
            else:
                # 免费版本只提供基本说明
                financial_data = {
                    "note": "免费版本不支持财务数据",
                    "suggestion": "请升级Tushare Pro以获取财务数据"
                }
                
            return financial_data
            
        except Exception as e:
            logger.error(f"获取简化财务数据失败: {e}")
            return {"error": f"财务数据获取异常: {str(e)}"}
    
    async def _get_financial_data(self, ts_code: str) -> Dict[str, Any]:
        """获取财务数据"""
        try:
            financial_data = {}
            
            if self.pro:
                # 获取最新财务数据
                current_year = datetime.now().year
                
                # 利润表
                income_df = self.pro.income(ts_code=ts_code, limit=8)  # 最近8个季度
                if not income_df.empty:
                    financial_data["income_statement"] = income_df.to_dict('records')
                
                # 资产负债表
                balancesheet_df = self.pro.balancesheet(ts_code=ts_code, limit=8)
                if not balancesheet_df.empty:
                    financial_data["balance_sheet"] = balancesheet_df.to_dict('records')
                
                # 现金流量表
                cashflow_df = self.pro.cashflow(ts_code=ts_code, limit=8)
                if not cashflow_df.empty:
                    financial_data["cash_flow"] = cashflow_df.to_dict('records')
                
                # 财务指标
                fina_indicator_df = self.pro.fina_indicator(ts_code=ts_code, limit=8)
                if not fina_indicator_df.empty:
                    financial_data["financial_indicators"] = fina_indicator_df.to_dict('records')
                
                # 主要财务指标
                fina_mainbz_df = self.pro.fina_mainbz(ts_code=ts_code, limit=4)
                if not fina_mainbz_df.empty:
                    financial_data["main_business"] = fina_mainbz_df.to_dict('records')
                
                return financial_data
            else:
                # 使用免费API的财务数据
                stock_code = ts_code.split('.')[0]
                current_year = datetime.now().year
                
                # 获取基本财务数据
                try:
                    # 获取业绩报告
                    for quarter in [4, 3, 2, 1]:  # 从最新季度开始尝试
                        try:
                            profit_df = ts.get_profit_data(year=current_year, quarter=quarter)
                            if profit_df is not None and stock_code in profit_df['code'].values:
                                profit_data = profit_df[profit_df['code'] == stock_code].iloc[0].to_dict()
                                financial_data["profit_data"] = profit_data
                                break
                        except:
                            continue
                    
                    # 获取营运能力
                    for quarter in [4, 3, 2, 1]:
                        try:
                            operation_df = ts.get_operation_data(year=current_year, quarter=quarter)
                            if operation_df is not None and stock_code in operation_df['code'].values:
                                operation_data = operation_df[operation_df['code'] == stock_code].iloc[0].to_dict()
                                financial_data["operation_data"] = operation_data
                                break
                        except:
                            continue
                    
                    # 获取成长能力
                    for quarter in [4, 3, 2, 1]:
                        try:
                            growth_df = ts.get_growth_data(year=current_year, quarter=quarter)
                            if growth_df is not None and stock_code in growth_df['code'].values:
                                growth_data = growth_df[growth_df['code'] == stock_code].iloc[0].to_dict()
                                financial_data["growth_data"] = growth_data
                                break
                        except:
                            continue
                    
                    # 获取偿债能力
                    for quarter in [4, 3, 2, 1]:
                        try:
                            debtpaying_df = ts.get_debtpaying_data(year=current_year, quarter=quarter)
                            if debtpaying_df is not None and stock_code in debtpaying_df['code'].values:
                                debtpaying_data = debtpaying_df[debtpaying_df['code'] == stock_code].iloc[0].to_dict()
                                financial_data["debtpaying_data"] = debtpaying_data
                                break
                        except:
                            continue
                        
                except Exception as e:
                    logger.warning(f"获取部分财务数据失败: {e}")
                    
                return financial_data
                
        except Exception as e:
            logger.error(f"获取财务数据失败: {e}")
            
        return {"error": "无法获取财务数据"}
    
    async def _get_technical_indicators(self, stock_code: str) -> Dict[str, Any]:
        """获取技术指标数据 - 使用动态时间范围"""
        try:
            ts_code = self._normalize_stock_code(stock_code)
            
            # 获取历史数据用于计算技术指标
            if self.pro:
                # 🔧 修复：使用动态时间范围而不是硬编码
                from datetime import datetime, timedelta
                
                # 获取当前时间
                current_time = datetime.now()
                
                # 计算开始时间：向前推2年，确保有足够的历史数据计算技术指标
                start_time = current_time - timedelta(days=730)  # 2年
                
                # 计算结束时间：当前时间
                end_time = current_time
                
                # 格式化为YYYYMMDD格式
                start_date = start_time.strftime('%Y%m%d')
                end_date = end_time.strftime('%Y%m%d')
                
                # 获取足够的历史数据（至少100天）
                df = self.pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                
                if df.empty:
                    return {"error": "无法获取历史数据"}
                
                # 按日期排序
                df = df.sort_values('trade_date')
                df.reset_index(drop=True, inplace=True)
                
                # 计算所有技术指标
                technical_data = {}
                
                # 1. 趋势指标
                technical_data.update(self._calculate_trend_indicators(df))
                
                # 2. 动量指标
                technical_data.update(self._calculate_momentum_indicators(df))
                
                # 3. 能量指标
                technical_data.update(self._calculate_volume_indicators(df))
                
                # 4. 波动率指标
                technical_data.update(self._calculate_volatility_indicators(df))
                
                # 5. 风险指标
                technical_data.update(self._calculate_risk_indicators(df))
                
                # 6. 相对强弱指标
                technical_data.update(self._calculate_strength_indicators(df))
                
                return technical_data
                
            else:
                # 免费版本的技术指标（基础版本）
                try:
                    # 🔧 修复：使用动态时间范围而不是硬编码
                    from datetime import datetime, timedelta
                    
                    # 获取当前时间
                    current_time = datetime.now()
                    
                    # 计算开始时间：向前推2年，确保有足够的历史数据
                    start_time = current_time - timedelta(days=730)  # 2年
                    
                    # 格式化为YYYY-MM-DD格式（免费API使用的格式）
                    start_date = start_time.strftime('%Y-%m-%d')
                    
                    df = ts.get_hist_data(stock_code, start=start_date)
                    if df is not None and not df.empty:
                        df = df.sort_index()
                        return self._calculate_basic_technical_indicators(df)
                except Exception as e:
                    logger.warning(f"免费API获取技术指标失败: {e}")
                    
        except Exception as e:
            logger.error(f"获取技术指标失败: {e}")
            
        return {"error": "无法获取技术指标"}
    
    def _calculate_trend_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """计算趋势指标"""
        indicators = {}
        
        try:
            close_prices = df['close'].values
            high_prices = df['high'].values
            low_prices = df['low'].values
            
            # 移动平均线
            indicators['ma_5'] = np.mean(close_prices[-5:]) if len(close_prices) >= 5 else None
            indicators['ma_10'] = np.mean(close_prices[-10:]) if len(close_prices) >= 10 else None
            indicators['ma_20'] = np.mean(close_prices[-20:]) if len(close_prices) >= 20 else None
            indicators['ma_60'] = np.mean(close_prices[-60:]) if len(close_prices) >= 60 else None
            
            # MACD指标
            if len(close_prices) >= 34:
                macd_data = self._calculate_macd(pd.Series(close_prices))
                indicators.update(macd_data)
            
            # 布林带
            if len(close_prices) >= 20:
                bb_data = self._calculate_bollinger_bands(pd.Series(close_prices))
                indicators.update(bb_data)
            
            # DMI指标
            if len(df) >= 14:
                dmi_data = self._calculate_dmi(df)
                indicators.update(dmi_data)
            
        except Exception as e:
            logger.error(f"计算趋势指标失败: {e}")
            
        return indicators
    
    def _calculate_momentum_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """计算动量指标"""
        indicators = {}
        
        try:
            close_prices = df['close'].values
            high_prices = df['high'].values
            low_prices = df['low'].values
            
            # RSI指标
            if len(close_prices) >= 14:
                indicators['rsi_14'] = self._calculate_rsi(pd.Series(close_prices), 14)
                indicators['rsi_6'] = self._calculate_rsi(pd.Series(close_prices), 6)
            
            # KDJ指标
            if len(df) >= 9:
                kdj_data = self._calculate_kdj(df)
                indicators.update(kdj_data)
            
            # 威廉指标
            if len(df) >= 14:
                indicators['williams_14'] = self._calculate_williams(df, 14)
            
            # CCI指标
            if len(df) >= 20:
                indicators['cci_20'] = self._calculate_cci(df, 20)
            
            # ROC指标
            if len(close_prices) >= 12:
                indicators['roc_12'] = self._calculate_roc(pd.Series(close_prices), 12)
            
            # TRIX指标
            if len(close_prices) >= 20:
                indicators['trix'] = self._calculate_trix(pd.Series(close_prices))
            
        except Exception as e:
            logger.error(f"计算动量指标失败: {e}")
            
        return indicators
    
    def _calculate_volume_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """计算能量指标"""
        indicators = {}
        
        try:
            close_prices = df['close'].values
            volumes = df['vol'].values
            
            # OBV指标
            if len(df) >= 10:
                indicators['obv'] = self._calculate_obv(df)
            
            # SOBV指标
            if len(df) >= 20:
                indicators['sobv'] = self._calculate_sobv(df)
            
            # EMV指标
            if len(df) >= 14:
                indicators['emv'] = self._calculate_emv(df)
            
            # 量比
            if len(volumes) >= 5:
                indicators['volume_ratio'] = self._calculate_volume_ratio(df)
            
            # 成交量移动平均
            if len(volumes) >= 20:
                indicators['vol_ma_20'] = np.mean(volumes[-20:])
            
        except Exception as e:
            logger.error(f"计算能量指标失败: {e}")
            
        return indicators
    
    def _calculate_volatility_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """计算波动率指标"""
        indicators = {}
        
        try:
            close_prices = df['close'].values
            
            # 历史波动率
            if len(close_prices) >= 20:
                returns = np.diff(np.log(close_prices))
                indicators['volatility_20'] = np.std(returns[-20:]) * np.sqrt(252)  # 年化波动率
            
            # ATR指标
            if len(df) >= 14:
                indicators['atr_14'] = self._calculate_atr(df, 14)
            
        except Exception as e:
            logger.error(f"计算波动率指标失败: {e}")
            
        return indicators
    
    def _calculate_risk_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """计算风险指标"""
        indicators = {}
        
        try:
            close_prices = df['close'].values
            
            if len(close_prices) >= 60:
                returns = np.diff(np.log(close_prices))
                
                # Beta系数（相对于市场）
                indicators['beta'] = self._calculate_beta(df)
                
                # 最大回撤
                indicators['max_drawdown'] = self._calculate_max_drawdown(close_prices)
                
                # 夏普比率
                indicators['sharpe_ratio'] = self._calculate_sharpe_ratio(returns)
                
                # VaR（95%置信度）
                indicators['var_95'] = self._calculate_var(returns, 0.95)
                
                # 下行风险
                indicators['downside_risk'] = self._calculate_downside_risk(returns)
                
                # 风险调整收益
                indicators['risk_adjusted_return'] = self._calculate_risk_adjusted_return(returns)
                
        except Exception as e:
            logger.error(f"计算风险指标失败: {e}")
            
        return indicators
    
    def _calculate_strength_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """计算相对强弱指标"""
        indicators = {}
        
        try:
            close_prices = df['close'].values
            
            # 相对强弱（相对于大盘）
            indicators['relative_strength'] = self._calculate_relative_strength(df)
            
            # 价格强度
            if len(close_prices) >= 20:
                indicators['price_strength'] = (close_prices[-1] / close_prices[-20] - 1) * 100
            
        except Exception as e:
            logger.error(f"计算强弱指标失败: {e}")
            
        return indicators
    
    def _calculate_basic_technical_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """计算基础技术指标（用于免费API）"""
        indicators = {}
        
        try:
            close_prices = df['close'].values
            
            # 移动平均线
            indicators['ma_5'] = np.mean(close_prices[-5:]) if len(close_prices) >= 5 else None
            indicators['ma_10'] = np.mean(close_prices[-10:]) if len(close_prices) >= 10 else None
            indicators['ma_20'] = np.mean(close_prices[-20:]) if len(close_prices) >= 20 else None
            indicators['ma_60'] = np.mean(close_prices[-60:]) if len(close_prices) >= 60 else None
            
            # MACD指标
            if len(close_prices) >= 34:
                macd_data = self._calculate_macd(pd.Series(close_prices))
                indicators.update(macd_data)
            
            # 布林带
            if len(close_prices) >= 20:
                bb_data = self._calculate_bollinger_bands(pd.Series(close_prices))
                indicators.update(bb_data)
            
            # RSI指标
            if len(close_prices) >= 14:
                indicators['rsi_14'] = self._calculate_rsi(pd.Series(close_prices), 14)
            
            # 威廉指标
            if len(close_prices) >= 14:
                indicators['williams_14'] = self._calculate_williams(df, 14)
            
            # 量比
            if len(df['vol'].values) >= 5:
                indicators['volume_ratio'] = self._calculate_volume_ratio(df)
            
        except Exception as e:
            logger.error(f"计算基础技术指标失败: {e}")
            
        return indicators
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
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
    
    def _calculate_macd(self, prices: pd.Series) -> Dict[str, float]:
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
    
    def _calculate_bollinger_bands(self, prices: pd.Series, period: int = 20) -> Dict[str, float]:
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
    
    def _calculate_volume_ratio(self, df: pd.DataFrame) -> float:
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
    
    def _calculate_pe_percentile(self, ts_code: str) -> float:
        """计算PE历史分位数"""
        try:
            if self.pro:
                # 获取历史PE数据
                df = self.pro.daily_basic(ts_code=ts_code, limit=250)
                if not df.empty and 'pe' in df.columns:
                    current_pe = df['pe'].iloc[0]
                    pe_percentile = (df['pe'] < current_pe).sum() / len(df) * 100
                    return float(pe_percentile)
        except:
            pass
        return 0.0
    
    def _calculate_pb_percentile(self, ts_code: str) -> float:
        """计算PB历史分位数"""
        try:
            if self.pro:
                # 获取历史PB数据
                df = self.pro.daily_basic(ts_code=ts_code, limit=250)
                if not df.empty and 'pb' in df.columns:
                    current_pb = df['pb'].iloc[0]
                    pb_percentile = (df['pb'] < current_pb).sum() / len(df) * 100
                    return float(pb_percentile)
        except:
            pass
        return 0.0
    
    def _calculate_dividend_yield(self, ts_code: str) -> float:
        """计算股息率"""
        try:
            if self.pro:
                # 获取分红数据
                dividend_df = self.pro.dividend(ts_code=ts_code, limit=1)
                daily_df = self.pro.daily(ts_code=ts_code, limit=1)
                
                if not dividend_df.empty and not daily_df.empty:
                    dividend = dividend_df['cash_div'].iloc[0]
                    price = daily_df['close'].iloc[0]
                    return float(dividend / price * 100) if price > 0 else 0.0
        except:
            pass
        return 0.0

    def _calculate_kdj(self, df: pd.DataFrame, period: int = 9) -> Dict[str, float]:
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
            logger.error(f"计算KDJ指标失败: {e}")
            return {'kdj_k': None, 'kdj_d': None, 'kdj_j': None}
    
    def _calculate_williams(self, df: pd.DataFrame, period: int = 14) -> float:
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
            logger.error(f"计算威廉指标失败: {e}")
            return None
    
    def _calculate_cci(self, df: pd.DataFrame, period: int = 20) -> float:
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
            logger.error(f"计算CCI指标失败: {e}")
            return None
    
    def _calculate_roc(self, prices: pd.Series, period: int = 12) -> float:
        """计算ROC指标"""
        try:
            if len(prices) < period + 1:
                return None
                
            current_price = prices.iloc[-1]
            past_price = prices.iloc[-period-1]
            
            roc = (current_price - past_price) / past_price * 100
            
            return roc
            
        except Exception as e:
            logger.error(f"计算ROC指标失败: {e}")
            return None
    
    def _calculate_trix(self, prices: pd.Series, period: int = 14) -> float:
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
            logger.error(f"计算TRIX指标失败: {e}")
            return None
    
    def _calculate_obv(self, df: pd.DataFrame) -> float:
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
            logger.error(f"计算OBV指标失败: {e}")
            return None
    
    def _calculate_sobv(self, df: pd.DataFrame, period: int = 20) -> float:
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
            logger.error(f"计算SOBV指标失败: {e}")
            return None
    
    def _calculate_emv(self, df: pd.DataFrame, period: int = 14) -> float:
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
            logger.error(f"计算EMV指标失败: {e}")
            return None
    
    def _calculate_dmi(self, df: pd.DataFrame, period: int = 14) -> Dict[str, float]:
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
            logger.error(f"计算DMI指标失败: {e}")
            return {'dmi_pdi': None, 'dmi_mdi': None, 'dmi_adx': None}
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
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
            logger.error(f"计算ATR指标失败: {e}")
            return None
    
    def _calculate_beta(self, df: pd.DataFrame) -> float:
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
            logger.error(f"计算Beta系数失败: {e}")
            return None
    
    def _calculate_max_drawdown(self, prices: np.ndarray) -> float:
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
            logger.error(f"计算最大回撤失败: {e}")
            return None
    
    def _calculate_sharpe_ratio(self, returns: np.ndarray, risk_free_rate: float = 0.03) -> float:
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
            logger.error(f"计算夏普比率失败: {e}")
            return None
    
    def _calculate_var(self, returns: np.ndarray, confidence_level: float = 0.95) -> float:
        """计算VaR"""
        try:
            if len(returns) < 10:
                return None
                
            # 计算VaR
            var = np.percentile(returns, (1 - confidence_level) * 100)
            
            return abs(var)
            
        except Exception as e:
            logger.error(f"计算VaR失败: {e}")
            return None
    
    def _calculate_downside_risk(self, returns: np.ndarray, target_return: float = 0) -> float:
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
            logger.error(f"计算下行风险失败: {e}")
            return None
    
    def _calculate_risk_adjusted_return(self, returns: np.ndarray) -> float:
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
            logger.error(f"计算风险调整收益失败: {e}")
            return None
    
    def _calculate_relative_strength(self, df: pd.DataFrame) -> float:
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
            logger.error(f"计算相对强弱失败: {e}")
            return None
    
    async def _get_valuation_data(self, ts_code: str) -> Dict[str, Any]:
        """获取估值数据"""
        try:
            if self.pro:
                # 获取每日指标（包含PE、PB等）
                df = self.pro.daily_basic(ts_code=ts_code, limit=1)
                
                if not df.empty:
                    valuation_data = df.iloc[0].to_dict()
                    
                    # 计算更多估值指标
                    valuation_data.update({
                        "pe_percentile": self._calculate_pe_percentile(ts_code),
                        "pb_percentile": self._calculate_pb_percentile(ts_code),
                        "dividend_yield": self._calculate_dividend_yield(ts_code)
                    })
                    
                    return valuation_data
                    
        except Exception as e:
            logger.error(f"获取估值数据失败: {e}")
            
        return {"error": "无法获取估值数据"}
    
    async def _get_money_flow_data(self, ts_code: str) -> Dict[str, Any]:
        """获取资金流向数据"""
        try:
            if self.pro:
                # 获取资金流向数据
                df = self.pro.moneyflow(ts_code=ts_code, limit=20)
                
                if not df.empty:
                    return {
                        "latest_flow": df.iloc[0].to_dict() if not df.empty else {},
                        "flow_history": df.head(10).to_dict('records'),
                        "net_flow_summary": {
                            "net_mf_vol": df['net_mf_vol'].sum(),
                            "net_mf_amount": df['net_mf_amount'].sum()
                        }
                    }
                    
        except Exception as e:
            logger.error(f"获取资金流向数据失败: {e}")
            
        return {"error": "无法获取资金流向数据"}
    
    async def _get_dividend_data(self, ts_code: str) -> Dict[str, Any]:
        """获取分红送股数据"""
        try:
            if self.pro:
                # 获取分红送股数据
                df = self.pro.dividend(ts_code=ts_code, limit=10)
                
                if not df.empty:
                    return {
                        "dividend_history": df.to_dict('records'),
                        "latest_dividend": df.iloc[0].to_dict() if not df.empty else {},
                        "dividend_summary": {
                            "total_dividends": df['cash_div'].sum(),
                            "dividend_years": len(df)
                        }
                    }
            else:
                # 使用免费API
                stock_code = ts_code.split('.')[0]
                # 免费版本的分红数据接口可能不可用
                
        except Exception as e:
            logger.error(f"获取分红数据失败: {e}")
            
        return {"error": "无法获取分红数据"}

# 全局实例 - 尝试从环境变量获取token
tushare_collector = TushareDataCollector() 