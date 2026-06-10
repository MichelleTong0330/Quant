import akshare as ak
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.decomposition import PCA
import warnings
import os
from sklearn.linear_model import LinearRegression

warnings.filterwarnings("ignore")

# 配置区
MOM_WINDOW = 12
START_DATE = "20070101"
END_DATE ="20240131"
PCA_WINDOW = 100
TOP_N = 5
CACHE_DIR = "./data_cache_residual"
RESULT_DIR = "./results_residual"
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)

COMMODITIES = {
    "CU0": "铜", "AL0": "铝", "AU0": "黄金",
    "SC0": "原油", "MA0": "甲醇",
    "M0": "豆粕", "P0": "棕榈油",
    "I0": "铁矿石", "RB0": "螺纹钢"
}

sw_info = ak.sw_index_first_info()
SW_INDUSTRIES = {row["行业代码"][:6]:row["行业名称"] for _, row in sw_info.iterrows()}

def get_sw_daily(code: str, name:str) -> pd.DataFrame:
   cache_path = f"{CACHE_DIR}/sw_index{code}.csv" 
   if os.path.exists(cache_path):
      return pd.read_csv(cache_path, parse_dates=["date"])
   try:
        # monthly_ret = {}
        df = ak.index_hist_sw(symbol = code, period = "day")
        df = df.rename(columns={"日期":"date", "收盘": "close"})
        df = df[["date", "close"]]
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        df["close"] = pd.to_numeric(df["close"], errors = "coerce")
        df.to_csv(cache_path, index=True)
        print(df)
        return pd.read_csv(cache_path, parse_dates=["date"], index_col=0)
   except Exception as e:
        print(f"  [警告] {name}({code}) 下载失败: {e}")
        return pd.DataFrame()
   
index_data = {}
for code, name in SW_INDUSTRIES.items():
    df = get_sw_daily(code, name)
    if not df.empty:
        index_data[name] = df

def get_bond_yields() -> pd.DataFrame:
    cache_path = f"{CACHE_DIR}/bond_yield.csv" 
    if os.path.exists(cache_path):
        return pd.read_csv(cache_path, parse_dates=["date"])
    try:
        df = ak.bond_zh_us_rate()
        df = df.rename(columns={"日期":"date","中国国债收益率2年": "CH_YIELDS_2Y","中国国债收益率5年": "CH_YIELDS_5Y","中国国债收益率10年": "CH_YIELDS_10Y","中国国债收益率30年": "CH_YIELDS_30Y" })
        df = df[["date","CH_YIELDS_2Y","CH_YIELDS_5Y","CH_YIELDS_10Y","CH_YIELDS_30Y"]]
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        df = df.set_index("date")
        df = df.groupby(df.index.to_period("M")).last()
        df.index = df.index.to_timestamp("M")
        df["CH_YIELDS_2Y"] = pd.to_numeric(df["CH_YIELDS_2Y"], errors = "coerce")
        df["CH_YIELDS_5Y"] = pd.to_numeric(df["CH_YIELDS_5Y"], errors = "coerce")
        df["CH_YIELDS_10Y"] = pd.to_numeric(df["CH_YIELDS_10Y"], errors = "coerce")
        df["CH_YIELDS_30Y"] = pd.to_numeric(df["CH_YIELDS_30Y"], errors = "coerce")
        df.to_csv(cache_path,index=True)
        return pd.read_csv(cache_path, parse_dates=True, index_col=0)
    except Exception as e:
        print(f"[警告]下载失败: {e}")
        return pd.DataFrame()

print(len(index_data))
print(get_bond_yields())
# print(ak.futures_main_sina(symbol="CU0", start_date="20070101", end_date="20240131").head())
# print(ak.futures_display_main_sina())

def get_commodity_data() -> pd.DataFrame:
    cache_path = f"{CACHE_DIR}/commodity_data.csv" 
    
    if os.path.exists(cache_path):
        return pd.read_csv(cache_path, parse_dates=["date"], index_col="date")
    try:
        all_commodities = {}
        for symbol, name in COMMODITIES.items():
             df = ak.futures_main_sina(symbol=symbol, start_date=START_DATE, end_date=END_DATE)
             df = df.rename(columns={"日期":"date","收盘价": "close"})
             df = df[["date", "close"]]
             df["date"] = pd.to_datetime(df["date"])
             df = df.sort_values("date").reset_index(drop=True)
             df["close"] = pd.to_numeric(df["close"], errors = "coerce")
             if not df.empty:
                 mc = df.groupby(df["date"].dt.to_period("M"))["close"].last()
                 mc.index = mc.index.to_timestamp("M")
                 all_commodities[name] = mc  # 存Series
        result = pd.DataFrame(all_commodities)
        result.index.name = "date"
        result.to_csv(cache_path,index=True)
        return pd.read_csv(cache_path, parse_dates=["date"], index_col="date")
    except Exception as e:
        print(f"[警告]下载失败: {e}")
        return pd.DataFrame()
    
# print(get_commodity_data())

def build_stock_yoy(index_data: dict) -> pd.DataFrame:
    yoy_data = {}
    for name, df in index_data.items():
        df = df.set_index("date")
        monthly_close = df["close"].resample("ME").last()
        yoy = monthly_close.pct_change(12)
        yoy = np.log(1+yoy)
        yoy_data[name] = yoy
    return pd.DataFrame(yoy_data)
# print(build_stock_yoy(index_data))

print("数据预处理...")
print(type(get_commodity_data().index))
print(get_commodity_data().index[:3])


def build_commodity_yoy(comm_data: pd.DataFrame) -> pd.DataFrame:
    comm_yoy = comm_data.pct_change(12)
    comm_yoy = np.log(1 + comm_yoy)
    return comm_yoy.dropna(how="all")
# print(build_bond_yoy(get_bond_yields()))

def build_bond_yoy(bond_data: pd.DataFrame) -> pd.DataFrame:
    bond_data = bond_data.set_index("date")   # 加这一行
    bond_data.index = pd.to_datetime(bond_data.index)  # 确保是DatetimeIndex
    bond_data = bond_data.drop(columns=["Unnamed: 0"], errors="ignore")  # 删掉多余列
    bond_yoy = bond_data.diff(12)
    return bond_yoy.dropna(how="all")

# print(build_commodity_yoy(get_commodity_data()))
stock_yoy = build_stock_yoy(index_data)
bond_yoy = build_bond_yoy(get_bond_yields())
comm_yoy = build_commodity_yoy(get_commodity_data())

# print(stock_yoy.shape)
# print(bond_yoy.shape)
# print(comm_yoy.shape)

def run_pca(data: pd.DataFrame, n_components: int) -> np.ndarray:
    data = data.dropna(how="all")
    pca = PCA(n_components=n_components)
    return pca.fit_transform(data.fillna(0))

def build_stock_mom(index_data: dict) -> pd.DataFrame:
   mom_data = {}
   for name, df in index_data.items():
        df = df.set_index("date")
        monthly_close = df["close"].resample("ME").last()
        mom = monthly_close.pct_change(1)
        mom = np.log(1+mom)
        mom_data[name] = mom
   return pd.DataFrame(mom_data)

def build_bond_mom(bond_data: pd.DataFrame) -> pd.DataFrame:
    bond_data = bond_data.copy()
    bond_data = bond_data.set_index("date")
    bond_data.index = pd.to_datetime(bond_data.index)
    bond_data = bond_data.drop(columns=["Unnamed: 0"], errors="ignore")
    return bond_data.diff(1).dropna(how="all")

def build_commodity_mom(comm_data: pd.DataFrame) -> pd.DataFrame:
    comm_mom = comm_data.pct_change(1)
    comm_mom = np.log(1 + comm_mom)
    return comm_mom.dropna(how="all")

# def rolling_pca_factors(data: pd.DataFrame, all_mom, window: int, n_components: int) -> pd.DataFrame:
#     factor ={}
#     for i in range(window, len(data)+1):
#         window_data = data.iloc[i-window:i].dropna(how="all").fillna(0)
#         pca = PCA(n_components=n_components)
#         pca.fit(window_data)
#         factor_values = pca.components_ @ all_mom.iloc[i-1].values
#         factor[data.index[i-1]] = factor_values
#     factor_df = pd.DataFrame(factor).T
#     return factor_df

def rolling_pca_factors(stock_yoy, bond_yoy, comm_yoy, window: int) -> pd.DataFrame:
    # 三类同比序列对齐
    idx = stock_yoy.index.intersection(bond_yoy.index).intersection(comm_yoy.index)
    stock_yoy = stock_yoy.loc[idx]
    bond_yoy  = bond_yoy.loc[idx]
    comm_yoy  = comm_yoy.loc[idx]

    factor = {}
    for i in range(window, len(idx) + 1):
        t     = idx[i - 1]
        s_raw = stock_yoy.iloc[i - window: i].fillna(0).values
        b_raw = bond_yoy.iloc[i - window: i].fillna(0).values
        c_raw = comm_yoy.iloc[i - window: i].fillna(0).values

        # 每类资产分别做PCA，得到窗口内因子的同比序列
        F_s = s_raw @ PCA(n_components=3).fit(s_raw).components_.T  # (100, 3)
        F_b = b_raw @ PCA(n_components=2).fit(b_raw).components_.T  # (100, 2)
        F_c = c_raw @ PCA(n_components=2).fit(c_raw).components_.T  # (100, 2)

        # 拼成(100, 7)，取最后两行做diff得到当期月频环比因子值
        F_all = np.hstack([F_s, F_b, F_c])          # (100, 7)
        factor[t] = F_all[-1] - F_all[-2]           # 当期环比 = 最后一行 - 倒数第二行

    factor_df = pd.DataFrame(factor).T
    factor_df.index.name = "date"
    return factor_df

def rolling_ols_residuals(factor_df, stock_mom, window):
    # 确保日期对齐
    common_dates = factor_df.index.intersection(stock_mom.index)
    factor_df = factor_df.loc[common_dates]
    stock_mom = stock_mom.loc[common_dates]

    residuals = {}
    for i in range(window, len(factor_df)+1):
        t = common_dates[i-1]
        X = factor_df.iloc[i-window:i].fillna(0).values
        y = stock_mom.iloc[i-window:i].fillna(0).values
        model = LinearRegression().fit(X, y)
        pred = model.predict(X)
        resid = (y - pred)[-1] # 取最后一个月的残差
        residuals[t] = resid
    residuals_df = pd.DataFrame(residuals, index=stock_mom.columns).T
    residuals_df.index.name = "date"
    return residuals_df

def calc_improved_momentum(residuals_df, lookback=12):
    scores = {}
    for i in range(lookback, len(residuals_df)+1):
        t            = residuals_df.index[i - 1]
        window_resid = residuals_df.iloc[i-lookback:i]
        vol = window_resid.std(axis=1)
        high_vol_mom = vol.idxmax()
        adjusted = window_resid.copy()
        adjusted.loc[high_vol_mom] *= -1        
        scores[t]    = window_resid.sum(axis=0)
    score_df = pd.DataFrame(scores).T
    score_df.index.name = "date"
    return score_df


def backet(scores, stock_mom, top_n= TOP_N):
    portfolio_returns = []
    date = []
    for i in range(len(scores)-1):
        date.append(scores.index[i])
        top_stocks = scores.iloc[i].nlargest(top_n).index
        ret = stock_mom.loc[scores.index[i+1], top_stocks].mean()
        portfolio_returns.append(ret)
    return pd.Series(portfolio_returns, index=date)




all_yoy = pd.concat([stock_yoy, bond_yoy, comm_yoy], axis=1)
stock_yoy = stock_yoy.loc[all_yoy.index]
stock_mom = build_stock_mom(index_data)
bond_mom = build_bond_mom(get_bond_yields())
bond_mom = bond_mom.drop(columns=["date"], errors="ignore")
comm_mom = build_commodity_mom(get_commodity_data())
all_mom = pd.concat([stock_mom, bond_mom, comm_mom], axis=1)
all_mom = all_mom.loc[all_yoy.index]

print(all_yoy.shape)
print(all_mom.shape)
print(bond_mom.columns.tolist())


factor_df = rolling_pca_factors(stock_yoy, bond_yoy, comm_yoy, PCA_WINDOW)
print(f"stock_yoy: {stock_yoy.shape}")
print(f"bond_yoy: {bond_yoy.shape}")
print(f"comm_yoy: {comm_yoy.shape}")
print(f"factor_df: {factor_df.shape}")
print(f"factor_df时间范围: {factor_df.index[0]} ~ {factor_df.index[-1]}")
stock_mom = stock_mom.loc[factor_df.index]
residuals_df = rolling_ols_residuals(factor_df, stock_mom, PCA_WINDOW)
scores = calc_improved_momentum(residuals_df)
portfolio_returns = backet(scores, stock_mom, TOP_N)
print(factor_df.index[:3])
print(stock_mom.index[:3])





nav = (1 + portfolio_returns).cumprod()
benchmark = stock_mom.mean(axis=1)
bench_nav = (1 + benchmark).cumprod()
common_index = nav.index.intersection(bench_nav.index)

start = "2016-04-30"
end = "2023-12-31"
port_trimmed = portfolio_returns.loc[start:end]
bench_trimmed = benchmark.loc[start:end]

common = port_trimmed.index.intersection(bench_trimmed.index)
port_trimmed = port_trimmed.loc[common]
bench_trimmed = bench_trimmed.loc[common]

print(f"port_trimmed 长度: {len(port_trimmed)}")
print(f"portfolio_returns 时间范围: {portfolio_returns.index[0]} ~ {portfolio_returns.index[-1]}")
print(f"scores 时间范围: {scores.index[0]} ~ {scores.index[-1]}")

nav_trimmed = (1 + port_trimmed).cumprod()
bench_nav_trimmed = (1 + bench_trimmed).cumprod()

n_months = len(port_trimmed)
annual_return = (nav_trimmed.iloc[-1] / nav_trimmed.iloc[0]) ** (12 / n_months) - 1
bench_annual = (bench_nav_trimmed.iloc[-1] / bench_nav_trimmed.iloc[0]) ** (12 / n_months) - 1

rolling_max = nav_trimmed.cummax()
drawdown = (nav_trimmed - rolling_max) / rolling_max
max_drawdown = drawdown.min()

win = (port_trimmed.values > bench_trimmed.values).sum()
win_rate = win / len(port_trimmed)

print(f"策略年化收益率: {annual_return:.2%}")
print(f"基准年化收益率: {bench_annual:.2%}")
print(f"年化超额收益: {annual_return - bench_annual:.2%}")
print(f"最大回撤: {max_drawdown:.2%}")
sharpe = (port_trimmed.mean() * 12) / (port_trimmed.std() * np.sqrt(12))
print(f"夏普比率: {sharpe:.2f}")
print(f"月度胜率: {win_rate:.2%}")

plt.plot(nav[common_index], label="改进残差动量")
plt.plot(bench_nav[common_index], label="等权基准")
plt.legend()
plt.show()