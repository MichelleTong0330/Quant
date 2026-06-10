"""
华泰金工《行业残差动量定价能力初探》— 国内行业轮动复现
数据：akshare（免费）
架构：一个大循环同时完成 PCA + OLS，与研报逻辑严格对应
"""

import os, warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
import akshare as ak

warnings.filterwarnings("ignore")

# ═══════════════════════════════════════════════════════════
# Block 1  配置
# ═══════════════════════════════════════════════════════════
START_DATE   = "20070101"
END_DATE     = "20240131"
PCA_WINDOW   = 100   # 滚动窗口（朱格拉周期）
MOM_LOOKBACK = 12    # 残差动量回看窗口
TOP_N        = 5     # 每月选行业数
CACHE        = "./cache"
os.makedirs(CACHE, exist_ok=True)

SW_INDUSTRIES = {
    "801010":"农林牧渔","801020":"采掘",    "801030":"化工",
    "801040":"钢铁",    "801050":"有色金属","801080":"电子",
    "801110":"家用电器","801120":"食品饮料","801130":"纺织服装",
    "801140":"轻工制造","801150":"医药生物","801160":"公用事业",
    "801170":"交通运输","801180":"房地产",  "801200":"商业贸易",
    "801210":"休闲服务","801230":"综合",    "801710":"建筑材料",
    "801720":"建筑装饰","801730":"电气设备","801740":"国防军工",
    "801750":"计算机",  "801760":"传媒",    "801770":"通信",
    "801780":"银行",    "801790":"非银金融","801880":"汽车",
    "801890":"机械设备","801950":"煤炭",    "801960":"石油石化",
    "801970":"环保",
}

COMMODITY_SYMBOLS = {
    "CU0":"铜","AL0":"铝","AU0":"黄金",
    "SC0":"原油","M0":"豆粕","RB0":"螺纹钢",
    "I0":"铁矿石","P0":"棕榈油",
}


# ═══════════════════════════════════════════════════════════
# Block 2  数据获取（带缓存）
# ═══════════════════════════════════════════════════════════

def get_sw_monthly_close() -> pd.DataFrame:
    """申万一级行业指数月频收盘价，index=月末日期，columns=行业名"""
    cache = f"{CACHE}/sw_monthly.csv"
    if os.path.exists(cache):
        return pd.read_csv(cache, index_col=0, parse_dates=True)

    closes = {}
    for code, name in SW_INDUSTRIES.items():
        try:
            df = ak.index_hist_sw(symbol=code, period="day")
            df = df.rename(columns={"日期":"date","收盘":"close"})
            df["date"]  = pd.to_datetime(df["date"])
            df["close"] = pd.to_numeric(df["close"], errors="coerce")
            df = df.set_index("date").sort_index()
            closes[name] = df["close"].resample("ME").last()
            print(f"  OK {name}")
        except Exception as e:
            print(f"  SKIP {name}: {e}")

    result = pd.DataFrame(closes)
    result.index.name = "date"
    result.to_csv(cache)
    return result


def get_bond_monthly() -> pd.DataFrame:
    """中国国债收益率月频水平值，index=月末日期"""
    cache = f"{CACHE}/bond_monthly.csv"
    if os.path.exists(cache):
        return pd.read_csv(cache, index_col=0, parse_dates=True)

    df = ak.bond_zh_us_rate()
    df = df.rename(columns={
        "日期":"date",
        "中国国债收益率2年":"CH_2Y","中国国债收益率5年":"CH_5Y",
        "中国国债收益率10年":"CH_10Y","中国国债收益率30年":"CH_30Y",
    })
    df["date"] = pd.to_datetime(df["date"])
    df = df[["date","CH_2Y","CH_5Y","CH_10Y","CH_30Y"]]
    for col in ["CH_2Y","CH_5Y","CH_10Y","CH_30Y"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.set_index("date").sort_index()
    result = df.resample("ME").last()
    result.index.name = "date"
    result.to_csv(cache)
    return result


def get_commodity_monthly() -> pd.DataFrame:
    """主力合约月频收盘价，index=月末日期，columns=品种名"""
    cache = f"{CACHE}/commodity_monthly.csv"
    if os.path.exists(cache):
        return pd.read_csv(cache, index_col=0, parse_dates=True)

    closes = {}
    for symbol, name in COMMODITY_SYMBOLS.items():
        try:
            df = ak.futures_main_sina(symbol=symbol,
                                      start_date=START_DATE, end_date=END_DATE)
            df = df.rename(columns={"日期":"date","收盘价":"close"})
            df["date"]  = pd.to_datetime(df["date"])
            df["close"] = pd.to_numeric(df["close"], errors="coerce")
            df = df.set_index("date").sort_index()
            closes[name] = df["close"].resample("ME").last()
            print(f"  OK {name}")
        except Exception as e:
            print(f"  SKIP {name}: {e}")

    result = pd.DataFrame(closes)
    result.index.name = "date"
    result.to_csv(cache)
    return result


# ═══════════════════════════════════════════════════════════
# Block 3  预处理
# ═══════════════════════════════════════════════════════════

def to_log_yoy(price: pd.DataFrame) -> pd.DataFrame:
    """价格水平 → 对数同比"""
    return np.log(price).diff(12).dropna(how="all")

def to_bond_diff(bond: pd.DataFrame) -> pd.DataFrame:
    """利率水平 → 同比差分"""
    return bond.diff(12).dropna(how="all")

def to_log_mom(price: pd.DataFrame) -> pd.DataFrame:
    """价格水平 → 月频对数收益率"""
    return np.log(price).diff(1)


# ═══════════════════════════════════════════════════════════
# Block 4 & 5  核心大循环：PCA + OLS → 残差序列
#
# 研报逻辑（国内6变量模型）：
#   在每个100个月滚动窗口内 ——
#   ① 对国内股/债/商同比序列分别 StandardScaler + PCA
#   ② 用载荷矩阵将同比序列投影回因子空间，得到窗口内因子序列 X(100×7)
#      股PC1/2/3，债PC1/2，商PC1/2  → 共7列
#   ③ 对每个行业月频对数收益率 Y(100×31) 对 X 做 OLS
#   ④ 取残差矩阵最后一行 → 当期各行业残差
# ═══════════════════════════════════════════════════════════

def build_residuals(
    stock_yoy: pd.DataFrame,
    bond_yoy:  pd.DataFrame,
    comm_yoy:  pd.DataFrame,
    stock_mom: pd.DataFrame,
    window:    int,
) -> pd.DataFrame:
    """
    一个大循环同时完成 PCA + OLS，输出残差序列。
    index = 月末日期，columns = 行业名称
    """
    # 三类同比序列对齐
    idx = (stock_yoy.index
           .intersection(bond_yoy.index)
           .intersection(comm_yoy.index))
    stock_yoy = stock_yoy.loc[idx]
    bond_yoy  = bond_yoy.loc[idx]
    comm_yoy  = comm_yoy.loc[idx]
    # 行业收益率对齐到同一时间轴
    stock_mom = stock_mom.reindex(idx)

    records = {}

    for i in range(window, len(idx) + 1):
        t = idx[i - 1]

        # ── 窗口内同比数据 ──────────────────────────────────
        s_raw = stock_yoy.iloc[i - window: i].fillna(0).values  # (100,31)
        b_raw = bond_yoy.iloc[i - window: i].fillna(0).values   # (100,4)
        c_raw = comm_yoy.iloc[i - window: i].fillna(0).values   # (100,8)

        # ── 标准化 ──────────────────────────────────────────
        s_sc = StandardScaler().fit_transform(s_raw)
        b_sc = StandardScaler().fit_transform(b_raw)
        c_sc = StandardScaler().fit_transform(c_raw)

        # ── PCA → 因子序列 X ────────────────────────────────
        # 投影：X = 标准化数据 @ 载荷矩阵.T，形状 (100, n_components)
        F_s = s_sc @ PCA(n_components=3).fit(s_sc).components_.T  # (100,3)
        F_b = b_sc @ PCA(n_components=2).fit(b_sc).components_.T  # (100,2)
        F_c = c_sc @ PCA(n_components=2).fit(c_sc).components_.T  # (100,2)
        X   = np.hstack([F_s, F_b, F_c])                          # (100,7)

        # ── OLS：行业月频收益率 ~ 公共因子 ─────────────────
        Y     = stock_mom.iloc[i - window: i].fillna(0).values    # (100,31)
        model = LinearRegression(fit_intercept=True).fit(X, Y)
        resid = Y - model.predict(X)                               # (100,31)

        # ── 只取当期（窗口最后一行）残差 ───────────────────
        records[t] = resid[-1]

    resid_df = pd.DataFrame(records, index=stock_yoy.columns).T
    resid_df.index.name = "date"
    return resid_df


# ═══════════════════════════════════════════════════════════
# Block 6  改进残差动量信号
# ═══════════════════════════════════════════════════════════

def calc_improved_momentum(resid_df: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """
    ① 取过去12个月残差矩阵
    ② 找截面波动率最高的月份，该月残差 × -1（反转效应）
    ③ 12个月残差求和 → 各行业得分
    """
    records = {}
    for i in range(lookback, len(resid_df) + 1):
        t   = resid_df.index[i - 1]
        win = resid_df.iloc[i - lookback: i].copy()   # (12, 31)
        high_vol_month = win.std(axis=1).idxmax()      # 截面波动率最高月
        win.loc[high_vol_month] *= -1
        records[t] = win.sum(axis=0)

    score_df = pd.DataFrame(records).T
    score_df.index.name = "date"
    return score_df


# ═══════════════════════════════════════════════════════════
# Block 7  回测 & 绩效
# ═══════════════════════════════════════════════════════════

def backtest(score_df: pd.DataFrame, stock_mom: pd.DataFrame, top_n: int) -> pd.Series:
    """月末信号 → 次月等权持有 top_n 行业"""
    idx = score_df.index.intersection(stock_mom.index)
    score_df  = score_df.loc[idx]
    stock_mom = stock_mom.loc[idx]

    returns, dates = [], []
    for i in range(len(score_df) - 1):
        top = score_df.iloc[i].nlargest(top_n).index
        ret = stock_mom.iloc[i + 1][top].mean()
        returns.append(ret)
        dates.append(score_df.index[i])

    return pd.Series(returns, index=dates, name="改进残差动量")


def performance(ret: pd.Series, label: str):
    ann_ret = ret.mean() * 12
    ann_vol = ret.std()  * np.sqrt(12)
    sharpe  = ann_ret / ann_vol if ann_vol > 0 else np.nan
    nav     = (1 + ret).cumprod()
    max_dd  = (nav / nav.cummax() - 1).min()
    print(f"\n{'─'*28} {label}")
    print(f"  年化收益: {ann_ret:.2%}")
    print(f"  年化波动: {ann_vol:.2%}")
    print(f"  夏普比率: {sharpe:.2f}")
    print(f"  最大回撤: {max_dd:.2%}")


def plot_nav(port: pd.Series, bench: pd.Series):
    nav_p = (1 + port).cumprod()
    nav_b = (1 + bench).cumprod()
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    axes[0].plot(nav_p, label="改进残差动量", lw=1.5)
    axes[0].plot(nav_b, label="等权基准",     lw=1.2, ls="--")
    axes[0].set_title("净值曲线")
    axes[0].legend()
    axes[1].plot(nav_p / nav_b, color="seagreen", lw=1.2)
    axes[1].axhline(1, color="gray", ls="--", lw=0.8)
    axes[1].set_title("超额净值（组合 / 基准）")
    plt.tight_layout()
    out = f"{CACHE}/nav.png"
    plt.savefig(out, dpi=150)
    plt.show()
    print(f"图表已保存：{out}")


# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("【Step 1】获取数据")
    sw_close   = get_sw_monthly_close()
    bond_raw   = get_bond_monthly()
    comm_close = get_commodity_monthly()
    print(f"  申万: {sw_close.shape}  债: {bond_raw.shape}  商品: {comm_close.shape}")

    print("\n【Step 2】预处理")
    stock_yoy = to_log_yoy(sw_close)
    bond_yoy  = to_bond_diff(bond_raw)
    comm_yoy  = to_log_yoy(comm_close)
    stock_mom = to_log_mom(sw_close)
    print(f"  stock_yoy:{stock_yoy.shape}  bond_yoy:{bond_yoy.shape}  comm_yoy:{comm_yoy.shape}")

    print("\n【Step 3+4】滚动PCA + OLS → 残差序列（100个月窗口，耗时约数分钟）")
    resid_df = build_residuals(stock_yoy, bond_yoy, comm_yoy, stock_mom, PCA_WINDOW)
    print(f"  resid_df: {resid_df.shape}  nan数: {resid_df.isna().sum().sum()}")

    print("\n【Step 5】改进残差动量信号")
    score_df = calc_improved_momentum(resid_df, MOM_LOOKBACK)
    print(f"  score_df: {score_df.shape}  nan数: {score_df.isna().sum().sum()}")

    print("\n【Step 6】回测")
    port_ret   = backtest(score_df, stock_mom, TOP_N)
    bench_ret  = stock_mom.reindex(port_ret.index).mean(axis=1)
    bench_ret.name = "等权基准"

    performance(port_ret,  "改进残差动量")
    performance(bench_ret, "等权基准")
    excess = pd.Series(port_ret.values - bench_ret.values,
                       index=port_ret.index, name="超额收益")
    performance(excess, "超额收益")

    plot_nav(port_ret, bench_ret)