import pandas as pd
import numpy as np

def process_factors(path_a, path_b):
    # --- 数据加载 ---
    df_a = pd.read_csv(path_a, parse_dates=['date'])
    df_b = pd.read_csv(path_b, parse_dates=['date'])
    
    # 合并数据，确保对齐
    df = pd.merge(df_a, df_b, on=['date', 'ticker'], suffixes=('_A', '_B'))

    # ==========================================
    # (1) 因子标准化：去极值 (98%样本计算) -> 标准化 -> 截断 [-3, 3]
    # ==========================================
    def winsorize_and_normalize(series):
        # 找到每日 1% 和 99% 的分位数
        q_low = series.quantile(0.01)
        q_high = series.quantile(0.99)
        
        # 仅用 1%-99% 之间的样本计算统计量
        subset = series[(series >= q_low) & (series <= q_high)]
        mu = subset.mean()
        sigma = subset.std()
        
        # 标准化并截断至 [-3, 3]
        return ((series - mu) / sigma).clip(-3, 3)

    # 按日期分组处理因子 A 和 B
    df['factor_A'] = df.groupby('date')['factor_A'].transform(winsorize_and_normalize)
    df['factor_B'] = df.groupby('date')['factor_B'].transform(winsorize_and_normalize)
    
    print("--- 任务1: 因子标准化与截断完成 ---")

    # ==========================================
    # (2) 相关性分析：计算每日相关性 -> 分年分月汇总
    # ==========================================
    # 计算每日相关系数
    daily_corr = df.groupby('date').apply(lambda x: x['factor_A'].corr(x['factor_B']), include_groups=False)
    
    # 转换为 DataFrame 并提取年、月
    corr_df = daily_corr.reset_index(name='corr')
    corr_df['year'] = corr_df['date'].dt.year
    corr_df['month'] = corr_df['date'].dt.month
    
    # 透视表：Index为年，Columns为月，计算均值
    corr_pivot = corr_df.pivot_table(index='year', columns='month', values='corr', aggfunc='mean')
    
    print("\n--- 任务2: 分年分月相关性均值 ---")
    print(corr_pivot)

    # ==========================================
    # (3) 因子正交化：A 对 B 做 OLS 回归，取残差作为因子 C
    # ==========================================
    # 为了极致性能，我们手动实现 OLS 公式: Residual = Y - X * (X'X)^-1 * X'Y
    def get_residual(group):
        y = group['factor_A'].values
        # 加上截距项
        X = np.column_stack([np.ones(len(group)), group['factor_B'].values])
        
        # 最小二乘法公式求解系数: beta = (X.T @ X)^-1 @ X.T @ y
        try:
            beta = np.linalg.lstsq(X, y, rcond=None)[0]
            residual = y - X @ beta
        except:
            residual = np.nan * y # 防止矩阵奇异导致报错
        return pd.Series(residual, index=group.index)

    # 执行回归并对齐样本
    df['factor_C'] = df.groupby('date', group_keys=False).apply(get_residual)
    
    print("\n--- 任务3: 因子 C (回归残差) 计算完成 ---")
    
    return df[['date', 'ticker', 'factor_A', 'factor_B', 'factor_C']], corr_pivot

# 运行
# result_df, corr_matrix = process_factors('factorA.csv', 'factorB.csv')