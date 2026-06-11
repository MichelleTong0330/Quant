import pandas as pd
import numpy as np

def rolling_all_normalize(df: pd.DataFrame) -> pd.DataFrame:
    # 1. 转换为宽表：Index为日期，Columns为股票
    # 这样每一行代表一个交易日的所有股票因子值
    pivot_df = df.pivot(index='date', columns='ticker', values='factor')
    
    # 2. 计算横截面的全样本均值和标准差
    # axis=1 表示对该行（当日所有股票）求均值
    daily_mean = pivot_df.mean(axis=1)
    daily_std = pivot_df.std(axis=1)
    
    # 3. 计算过去 5 个交易日的滚动均值和标准差（不包含当日，需 shift）
    # rolling(5) 会计算 T-4 到 T 的均值，shift(1) 将其移动到 T+1 使用
    roll_mean = daily_mean.rolling(window=5).mean().shift(1)
    roll_std = daily_std.rolling(window=5).mean().shift(1) # 按照逻辑，通常std也是取 rolling mean
    
    # 4. 执行标准化：利用 Pandas 的广播机制（Broadcasting）
    # (宽表 - 滚动均值序列) / 滚动标准差序列
    norm_pivot = pivot_df.sub(roll_mean, axis=0).div(roll_std, axis=0)
    
    # 5. 还原为长表格式并剔除因 rolling 产生的 NaN
    result = norm_pivot.stack(dropna=False).reset_index(name='factor')
    
    # 保持与原输入列名顺序一致
    return result[['date', 'ticker', 'factor']].dropna(subset=['factor'])

# 使用示例
# df = pd.read_csv('factorA.csv')
# df_normalized = rolling_all_normalize(df)