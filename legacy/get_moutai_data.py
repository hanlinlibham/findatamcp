#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""获取贵州茅台近一个月净值走势"""

import tushare as ts
import pandas as pd
from datetime import datetime, timedelta

# 读取token
with open('/home/tushare_mcp/tushare_mcp/tusharetoken.txt', 'r') as f:
    token = f.read().strip()

# 初始化pro接口
pro = ts.pro_api(token)

# 贵州茅台代码
ts_code = '600519.SH'

# 获取近45天数据（确保覆盖一个月交易日）
end_date = datetime.now().strftime('%Y%m%d')
start_date = (datetime.now() - timedelta(days=45)).strftime('%Y%m%d')

df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)

if not df.empty:
    df = df.sort_values('trade_date')
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    
    # 只保留近一个月（最近22个交易日）
    df = df.tail(22)
    
    print("\n📊 贵州茅台 (600519) 近一个月净值走势")
    start_str = df.iloc[0]["trade_date"].strftime("%Y-%m-%d")
    end_str = df.iloc[-1]["trade_date"].strftime("%Y-%m-%d")
    print(f"数据区间: {start_str} 至 {end_str}")
    print(f"交易日数: {len(df)} 天")
    print("=" * 75)
    print(f"{'日期':<12} {'开盘价':<10} {'最高价':<10} {'最低价':<10} {'收盘价':<10} {'涨跌幅':<10}")
    print("-" * 75)
    
    for _, row in df.iterrows():
        pct_chg = row['pct_chg'] if pd.notna(row['pct_chg']) else 0
        pct_str = f"{pct_chg:+.2f}%"
        date_str = row["trade_date"].strftime("%Y-%m-%d")
        print(f"{date_str:<12} {row['open']:<10.2f} {row['high']:<10.2f} {row['low']:<10.2f} {row['close']:<10.2f} {pct_str:<10}")
    
    print("=" * 75)
    start_price = df.iloc[0]['close']
    end_price = df.iloc[-1]['close']
    total_change = ((end_price / start_price) - 1) * 100
    max_price = df['high'].max()
    min_price = df['low'].min()
    
    print("\n📈 统计摘要:")
    print(f"  期初收盘价: ¥{start_price:.2f}")
    print(f"  期末收盘价: ¥{end_price:.2f}")
    print(f"  区间涨跌: {total_change:+.2f}%")
    print(f"  最高价: ¥{max_price:.2f}")
    print(f"  最低价: ¥{min_price:.2f}")
    print(f"  平均收盘价: ¥{df['close'].mean():.2f}")
    
    # 输出CSV格式
    print("\n📄 CSV格式数据:")
    print("trade_date,open,high,low,close,pct_chg")
    for _, row in df.iterrows():
        print(f"{row['trade_date'].strftime('%Y-%m-%d')},{row['open']},{row['high']},{row['low']},{row['close']},{row['pct_chg']}")
else:
    print("未获取到数据")
