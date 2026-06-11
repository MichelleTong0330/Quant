import akshare as ak
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.decomposition import PCA
import warnings
import os
from sklearn.linear_model import LinearRegression

warnings.filterwarnings("ignore")

# 修复 macOS 下 matplotlib 中文乱码
plt.rcParams["font.family"] = ["Heiti TC", "STHeiti", "Arial Unicode MS", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

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

# 研报做法：PCA 和 OLS 在同一个 100 月滚动窗口内完成
# 关键：用 yoy 数据的 PCA loadings，乘以各资产的月频 mom 序列，得到因子的月度环比值
# 而不是对 yoy 因子序列做 diff（diff 多减了一个 12 期历史项，是错的）
def rolling_residuals(stock_yoy, bond_yoy, comm_yoy,
                      stock_mom, bond_mom, comm_mom, window: int) -> pd.DataFrame:
    idx = (stock_yoy.index
           .intersection(bond_yoy.index)
           .intersection(comm_yoy.index)
           .intersection(stock_mom.index)
           .intersection(bond_mom.index)
           .intersection(comm_mom.index))
    sy = stock_yoy.loc[idx]; by = bond_yoy.loc[idx]; cy = comm_yoy.loc[idx]
    sm = stock_mom.loc[idx]; bm = bond_mom.loc[idx]; cm = comm_mom.loc[idx]

    residuals = {}
    for i in range(window, len(idx) + 1):
        t = idx[i - 1]
        # yoy 数据：用来做 PCA，得到因子方向（loadings）
        s_raw = sy.iloc[i - window: i].fillna(0).values   # (window, n_stocks)
        b_raw = by.iloc[i - window: i].fillna(0).values   # (window, 4)
        c_raw = cy.iloc[i - window: i].fillna(0).values   # (window, 9)

        # 研报国内版：股债商各提3/3/2个主成分
        pca_s = PCA(n_components=3).fit(s_raw)
        pca_b = PCA(n_components=3).fit(b_raw)  # 债券提3个，PC1市场+PC2/PC3风格
        pca_c = PCA(n_components=2).fit(c_raw)

        # mom 数据：用 yoy 的 PCA loadings 做加权求和，得到因子的月度环比序列
        sm_w = sm.iloc[i - window: i].fillna(0).values    # (window, n_stocks)
        bm_w = bm.iloc[i - window: i].fillna(0).values    # (window, 4)
        cm_w = cm.iloc[i - window: i].fillna(0).values    # (window, 9)

        F_s = sm_w @ pca_s.components_.T   # (window, 3)
        F_b = bm_w @ pca_b.components_.T   # (window, 3)
        F_c = cm_w @ pca_c.components_.T   # (window, 2)

        # 研报做法：三类 PC1 合并为一个市场因子 X1（简单相加）
        # 剩余风格因子各自独立：股 PC2/PC3，债 PC2/PC3，商 PC2 → 共 6 个 X
        market = F_s[:, 0:1] + F_b[:, 0:1] + F_c[:, 0:1]          # (window, 1)
        style  = np.hstack([F_s[:, 1:], F_b[:, 1:], F_c[:, 1:]])   # (window, 5)
        F_all  = np.hstack([market, style])                          # (window, 6)

        # OLS：各行业月收益率 ~ 6个共同因子，取最后一个月的残差
        model = LinearRegression().fit(F_all, sm_w)
        resid = sm_w - model.predict(F_all)
        residuals[t] = resid[-1]

    res_df = pd.DataFrame(residuals, index=sm.columns).T
    res_df.index.name = "date"
    return res_df

def calc_improved_momentum(residuals_df, lookback=12):
    scores = {}
    for i in range(lookback, len(residuals_df)+1):
        t            = residuals_df.index[i - 1]
        window_resid = residuals_df.iloc[i-lookback:i]
        vol = window_resid.std(axis=1)
        high_vol_mom = vol.idxmax()
        adjusted = window_resid.copy()
        adjusted.loc[high_vol_mom] *= -1
        scores[t]    = adjusted.sum(axis=0)   # 用反转后的序列求和
    score_df = pd.DataFrame(scores).T
    score_df.index.name = "date"
    return score_df


def backet(scores, stock_mom, top_n= TOP_N):
    portfolio_returns = []
    date = []
    for i in range(len(scores)-1):
        t_next = scores.index[i+1]
        date.append(t_next)  # 用持仓结束日，使 portfolio_returns 和 benchmark 对齐同一月
        top_stocks = scores.iloc[i].nlargest(top_n).index
        ret = stock_mom.loc[t_next, top_stocks].mean()
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


print(f"stock_yoy: {stock_yoy.shape}")
print(f"bond_yoy: {bond_yoy.shape}")
print(f"comm_yoy: {comm_yoy.shape}")
print("开始滚动 PCA+OLS，约需几分钟...")
residuals_df = rolling_residuals(stock_yoy, bond_yoy, comm_yoy,
                                  stock_mom, bond_mom, comm_mom, PCA_WINDOW)
print(f"residuals_df: {residuals_df.shape}")
print(f"残差时间范围: {residuals_df.index[0]} ~ {residuals_df.index[-1]}")
scores = calc_improved_momentum(residuals_df)
portfolio_returns = backet(scores, stock_mom, TOP_N)
print(f"scores 时间范围: {scores.index[0]} ~ {scores.index[-1]}")





print(f"portfolio_returns 时间范围: {portfolio_returns.index[0]} ~ {portfolio_returns.index[-1]}")

# 用实际数据起点，终点截到 2023-12-31
start = portfolio_returns.index[0].strftime("%Y-%m-%d")
end = "2023-12-31"
port_trimmed = portfolio_returns.loc[start:end]
benchmark = stock_mom.mean(axis=1)
bench_trimmed = benchmark.loc[start:end]

common = port_trimmed.index.intersection(bench_trimmed.index)
port_trimmed = port_trimmed.loc[common]
bench_trimmed = bench_trimmed.loc[common]

print(f"回测区间: {port_trimmed.index[0].date()} ~ {port_trimmed.index[-1].date()}，共 {len(port_trimmed)} 个月")

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

# ── 图1：净值曲线 ──────────────────────────────────────────
fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(nav_trimmed / nav_trimmed.iloc[0], label="改进残差动量（复现）")
ax.plot(bench_nav_trimmed / bench_nav_trimmed.iloc[0], label="等权基准（复现）")
ax.set_title("改进残差动量行业轮转 vs 等权基准")
ax.set_ylabel("累计净值（归一化）")
ax.legend()
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(f"{RESULT_DIR}/residual_momentum.png", dpi=150)
print(f"净值图已保存至 {RESULT_DIR}/residual_momentum.png")
plt.show()

# ── 图2：与研报数据对比图 ────────────────────────────────────
# 研报（华泰金工 2024-02）国内行业轮动·改进残差动量
# 披露数据：回测区间 2016-04-30~2023-12-31，年化超额收益 12.80%
excess_return = annual_return - bench_annual
bench_sharpe  = (bench_trimmed.mean() * 12) / (bench_trimmed.std() * np.sqrt(12))

# 研报仅明确披露了这几个数字，其余标 NaN
paper = {
    "年化超额收益(%)":  12.80,
    "策略年化收益(%)":  np.nan,   # 研报未直接给出绝对值
    "基准年化收益(%)":  np.nan,
    "策略夏普":         np.nan,
    "基准夏普":         np.nan,
}
ours = {
    "年化超额收益(%)":  excess_return * 100,
    "策略年化收益(%)":  annual_return * 100,
    "基准年化收益(%)":  bench_annual  * 100,
    "策略夏普":         sharpe,
    "基准夏普":         bench_sharpe,
}

labels = list(ours.keys())
x      = np.arange(len(labels))
width  = 0.35

fig2, ax2 = plt.subplots(figsize=(11, 6))
bars_o = ax2.bar(x - width/2,
                 [ours[k] for k in labels],
                 width, label="本次复现", color="#4C72B0", alpha=0.85)
bars_p = ax2.bar(x + width/2,
                 [paper[k] for k in labels],
                 width, label="研报披露", color="#DD8452", alpha=0.85)

for bar in bars_o:
    h = bar.get_height()
    if not np.isnan(h):
        ax2.text(bar.get_x() + bar.get_width()/2,
                 h + (0.2 if h >= 0 else -0.5),
                 f"{h:.2f}", ha="center", va="bottom", fontsize=8.5, color="#2c5f9e")

for bar in bars_p:
    h = bar.get_height()
    if not np.isnan(h):
        ax2.text(bar.get_x() + bar.get_width()/2,
                 h + (0.2 if h >= 0 else -0.5),
                 f"{h:.2f}", ha="center", va="bottom", fontsize=8.5, color="#9b4e1a")

ax2.set_xticks(x)
ax2.set_xticklabels(labels)
ax2.axhline(0, color="black", linewidth=0.8, linestyle="--")
ax2.set_ylabel("数值（收益率单位：%，夏普无量纲）")
ax2.set_title("复现结果 vs 研报披露数据\n"
              "（华泰金工2024-02·国内行业轮动·改进残差动量）\n"
              "注：研报仅披露年化超额收益12.80%，其他研报格空白为正常")
ax2.legend()
ax2.grid(True, axis="y", alpha=0.3)
fig2.tight_layout()
fig2.savefig(f"{RESULT_DIR}/comparison_with_paper.png", dpi=150)
print(f"对比图已保存至 {RESULT_DIR}/comparison_with_paper.png")
plt.show()