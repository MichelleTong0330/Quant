"""
《A股行业动量的精细结构》复现代码
黄金律模型 + 随机森林对比

流程：
  1. 下载申万行业指数日行情（akshare，带本地缓存）
  2. 计算因子：M0（日内动量）、M1（隔夜反转）、Ret20（传统动量基准）
  3. 黄金律回测：排名打分法，月度分组
  4. 随机森林回测：用M0/M1/Ret20预测下月收益排名
  5. 画图保存
"""

import akshare as ak
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
from sklearn.ensemble import RandomForestRegressor
import warnings
import time
import os

warnings.filterwarnings("ignore")


# ── 中文字体（Mac自动检测）────────────────────────────────────
_available = {f.name for f in fm.fontManager.ttflist}
_cn_fonts  = ["PingFang SC", "Heiti SC", "STHeiti", "Arial Unicode MS", "SimHei"]
_font      = next((f for f in _cn_fonts if f in _available), "DejaVu Sans")
plt.rcParams["font.family"]        = [_font, "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


# ════════════════════════════════════════════════════════════════
# 【配置区】—— 所有参数都在这里
# ════════════════════════════════════════════════════════════════

START_DATE = "20050101"
END_DATE   = "20100101"
LOOKBACK   = 25
CACHE_DIR  = "./data_cache"
RESULT_DIR = "/Users/tongxin/Desktop/复现集/黄金律结果"

SW_INDUSTRIES = {
    "801010": "农林牧渔", "801020": "采掘",    "801030": "化工",
    "801040": "钢铁",     "801050": "有色金属", "801080": "电子",
    "801110": "家用电器", "801120": "食品饮料", "801130": "纺织服装",
    "801140": "轻工制造", "801150": "医药生物", "801160": "公用事业",
    "801170": "交通运输", "801180": "房地产",   "801200": "商业贸易",
    "801210": "休闲服务", "801230": "综合",     "801710": "建筑材料",
    "801720": "建筑装饰", "801730": "电气设备", "801740": "国防军工",
    "801750": "计算机",   "801760": "传媒",     "801770": "通信",
    "801780": "银行",     "801790": "非银金融", "801880": "汽车",
    "801890": "机械设备",
}

os.makedirs(CACHE_DIR,  exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)


# ════════════════════════════════════════════════════════════════
# 【第一步】数据获取
# ════════════════════════════════════════════════════════════════

def get_index_daily(code: str, name: str) -> pd.DataFrame:
    # 下载申万行业指数日行情，有缓存则直接读取。
    cache_path = f"{CACHE_DIR}/index_{code}.csv"
    if os.path.exists(cache_path):
        return pd.read_csv(cache_path, parse_dates=["date"]) #后面代码里大量要按日期筛选、排序、分组，所以必须是真正的日期类型才行
    try:
        df = ak.index_hist_sw(symbol=code, period="day")
        df = df.rename(columns={"日期": "date", "开盘": "open", "收盘": "close"})
        df["date"] = pd.to_datetime(df["date"])
        df = df[["date", "open", "close"]].sort_values("date").reset_index(drop=True)
        df.to_csv(cache_path, index=False)
        time.sleep(0.3)
        return df
    except Exception as e:
        print(f"  [警告] {name}({code}) 下载失败: {e}")
        return pd.DataFrame()


def get_hs300() -> pd.Series:
    """
    下载沪深300月度收益率，作为多头组合的业绩基准。
    用 ak.stock_zh_index_daily(symbol="sh000300") 获取日行情，
    再压缩成月度收益（取每月最后一个交易日收盘价，计算环比涨跌幅）。
    返回：pd.Series，index=月末时间戳，value=当月涨跌幅
    """
    cache_path = f"{CACHE_DIR}/hs300.csv"
    if os.path.exists(cache_path):
        df = pd.read_csv(cache_path, parse_dates=["date"])
    else:
        try:
            df = ak.stock_zh_index_daily(symbol="sh000300")
            df = df.rename(columns={"date": "date", "close": "close"})
            df["date"] = pd.to_datetime(df["date"])
            df = df[["date", "close"]].sort_values("date").reset_index(drop=True)
            df.to_csv(cache_path, index=False)
        except Exception as e:
            print(f"  [警告] 沪深300下载失败: {e}")
            return pd.Series(dtype=float)

    df = df.set_index("date").sort_index()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    # 日数据 → 月数据：取每月最后一个交易日，计算环比涨跌幅
    mc = df["close"].groupby(df["close"].index.to_period("M")).last()
    mc.index = mc.index.to_timestamp("M")
    return mc.pct_change().rename("HS300")


# ════════════════════════════════════════════════════════════════
# 【第二步】因子计算
# ════════════════════════════════════════════════════════════════

def calc_factors(index_data: dict) -> dict:
    """
    对每个行业计算三个因子：
      M0：过去20日日内收益（今收/今开-1）之和，呈动量效应
      M1：过去20日隔夜收益（今开/昨收-1）之和，呈反转效应
      Ret20：过去20日总涨跌幅，传统动量基准
    同时过滤单日涨跌幅超过±20%的异常日（停牌复牌等）。
    """
    print("\n[因子计算] 计算M0、M1、Ret20...")
    results = {}
    for code, name in SW_INDUSTRIES.items():
        if name not in index_data:
            continue
        df = index_data[name].copy().set_index("date").sort_index()
        df["open"]  = pd.to_numeric(df["open"],  errors="coerce")
        df["close"] = pd.to_numeric(df["close"], errors="coerce")

        df["intra"]     = df["close"] / df["open"] - 1
        df["overnight"] = df["open"] / df["close"].shift(1) - 1

        # 过滤异常交易日
        DAILY_LIMIT = 0.20
        df.loc[df["intra"].abs()     > DAILY_LIMIT, "intra"]     = np.nan
        df.loc[df["overnight"].abs() > DAILY_LIMIT, "overnight"] = np.nan

        # 滚动求和，窗口内至少15个有效值才计算
        df["M0"]    = df["intra"].rolling(LOOKBACK, min_periods=15).sum()
        df["M1"]    = df["overnight"].rolling(LOOKBACK, min_periods=15).sum()
        df["Ret20"] = df["close"].pct_change(LOOKBACK)

        results[name] = df[["M0", "M1", "Ret20"]]

    print(f"  完成，共 {len(results)} 个行业")
    return results


# ════════════════════════════════════════════════════════════════
# 【辅助函数】构造月度收益宽表
# ════════════════════════════════════════════════════════════════

def build_monthly_ret(index_data: dict) -> pd.DataFrame:
    """
    从日行情构造月度收益宽表。
    取每月实际最后一个交易日收盘价，计算环比涨跌幅。
    行=月份，列=行业名，值=该行业该月涨跌幅。
    """
    monthly_ret = {}
    for name, df in index_data.items():
        df = df.set_index("date").sort_index()
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        # groupby取每月实际最后一个交易日，避免日历月末非交易日问题
        mc = df["close"].groupby(df["close"].index.to_period("M")).last()
        mc.index = mc.index.to_timestamp("M")
        monthly_ret[name] = mc.pct_change()
    return pd.DataFrame(monthly_ret).dropna(how="all")


# ════════════════════════════════════════════════════════════════
# 【第三步】黄金律回测
# ════════════════════════════════════════════════════════════════

def run_backtest(index_data: dict, factor_data: dict) -> dict:
    """
    黄金律模型月度回测（含多头费后评估）。

    时间逻辑：用T月底的因子预测T+1月的收益。
    打分方式：总得分 = rank(M0) + (N+1 - rank(M1))
    分组：按总得分分5组，G5最高，G1最低，多空=G5-G1

    ── 费用假设（可在此修改）───────────────────────────────────
    COST_PER_TRADE：单边交易成本
      = 佣金0.03% + 印花税0.05%(卖方单边) + 冲击成本约0.05%
      ≈ 0.10%（买入端） / 0.13%（卖出端）
      保守取双边合计 0.20%（行业指数ETF，流动性好，冲击成本低）
    COST_ROUNDTRIP：换入一个仓位的完整成本 = 卖出旧仓 + 买入新仓
    ────────────────────────────────────────────────────────────
    """
    COST_ROUNDTRIP = 0.0020   # 0.20% 双边，每换一个仓位扣一次

    print("\n[黄金律回测] 开始...")
    ret_df = build_monthly_ret(index_data)

    # 取每月底的M0和M1值
    m0_dict, m1_dict = {}, {}
    for name, df in factor_data.items():
        m0 = df["M0"].groupby(df["M0"].index.to_period("M")).last()
        m0.index = m0.index.to_timestamp("M")
        m0_dict[name] = m0
        m1 = df["M1"].groupby(df["M1"].index.to_period("M")).last()
        m1.index = m1.index.to_timestamp("M")
        m1_dict[name] = m1

    m0_df = pd.DataFrame(m0_dict).dropna(how="all")
    m1_df = pd.DataFrame(m1_dict).dropna(how="all")

    # 三表对齐
    common = m0_df.index.intersection(m1_df.index).intersection(ret_df.index)
    m0_df  = m0_df.loc[common]
    m1_df  = m1_df.loc[common]
    ret_df = ret_df.loc[common]

    n_groups = 5
    group_returns = {g: [] for g in range(1, n_groups + 1)}
    dates = []

    # ── 多头费后专项追踪 ──────────────────────────────────────
    g5_gross_rets   = []   # G5 费前月收益
    g5_net_rets     = []   # G5 费后月收益
    turnovers       = []   # 每月换手率（新增仓位数 / 总仓位数）
    g5_members_prev = set()

    for i in range(1, len(m0_df)):
        this_month = m0_df.index[i]
        last_month = m0_df.index[i - 1]

        m0_cross = m0_df.loc[last_month].dropna()
        m1_cross = m1_df.loc[last_month].dropna()
        rets     = ret_df.loc[this_month]

        valid = m0_cross.index.intersection(m1_cross.index)
        m0_cross = m0_cross.loc[valid]
        m1_cross = m1_cross.loc[valid]
        if len(m0_cross) < n_groups:
            continue

        # 截面Winsorize
        for s in [m0_cross, m1_cross]:
            s.clip(lower=s.quantile(0.025), upper=s.quantile(0.975), inplace=True)

        n = len(m0_cross)
        scores = m0_cross.rank(method="first") + (n + 1 - m1_cross.rank(method="first"))
        ranked = scores.rank(method="first")

        for g in range(1, n_groups + 1):
            members    = ranked[(ranked > (g-1)/n_groups*n) & (ranked <= g/n_groups*n)].index
            valid_rets = rets.loc[members.intersection(rets.index)].dropna()
            group_returns[g].append(valid_rets.mean() if len(valid_rets) > 0 else np.nan)

            # ── G5 费后计算 ──────────────────────────────────
            if g == n_groups:
                g5_now   = set(members)
                n_pos    = len(g5_now)  # 本期持仓数

                # 换手率 = 新增行业数 / 本期持仓数
                # 新进来的行业 → 需要买入（同时卖出对应数量的旧仓）
                n_new    = len(g5_now - g5_members_prev)
                turnover = n_new / n_pos if n_pos > 0 else 0.0

                # 费用 = 换手率 × 双边成本
                cost     = turnover * COST_ROUNDTRIP
                gross    = valid_rets.mean() if len(valid_rets) > 0 else np.nan
                net      = (gross - cost) if not np.isnan(gross) else np.nan

                g5_gross_rets.append(gross)
                g5_net_rets.append(net)
                turnovers.append(turnover)
                g5_members_prev = g5_now

        dates.append(this_month)

    group_ret_df = pd.DataFrame(group_returns, index=dates)
    group_ret_df.columns = [f"G{g}" for g in range(1, n_groups + 1)]
    group_ret_df["LS"] = group_ret_df["G5"] - group_ret_df["G1"]
    nav = (1 + group_ret_df.fillna(0)).cumprod()
    ls  = group_ret_df["LS"].dropna()
    stats = {
        "年化收益":   ls.mean() * 12,
        "年化波动":   ls.std()  * np.sqrt(12),
        "信息比率IR": (ls.mean() / ls.std()) * np.sqrt(12) if ls.std() > 0 else np.nan,
        "月度胜率":   (ls > 0).mean(),
    }

    # ── 多头费后统计 ─────────────────────────────────────────
    g5_gross = pd.Series(g5_gross_rets, index=dates)
    g5_net   = pd.Series(g5_net_rets,   index=dates)
    to_s     = pd.Series(turnovers,     index=dates)

    def _long_stats(s: pd.Series, label: str) -> dict:
        ann_ret = s.mean() * 12
        ann_vol = s.std()  * np.sqrt(12)
        sr      = ann_ret / ann_vol if ann_vol > 0 else np.nan
        nav_    = (1 + s.fillna(0)).cumprod()
        dd      = (nav_ / nav_.cummax() - 1)
        return {
            f"{label}_年化收益":   ann_ret,
            f"{label}_年化波动":   ann_vol,
            f"{label}_夏普":       sr,
            f"{label}_月度胜率":   (s > 0).mean(),
            f"{label}_最大回撤":   dd.min(),
        }

    long_stats_gross = _long_stats(g5_gross, "多头费前")
    long_stats_net   = _long_stats(g5_net,   "多头费后")

    # 换手率分析
    turnover_stats = {
        "平均月换手率":   to_s.mean(),
        "月换手率中位数": to_s.median(),
        "年化双边换手率": to_s.mean() * 12,
        "单月最高换手率": to_s.max(),
        "月均费用拖累":   to_s.mean() * COST_ROUNDTRIP,
        "年化费用拖累":   to_s.mean() * COST_ROUNDTRIP * 12,
    }

    # Ret20基准（逻辑相同，只换因子，直接数值排序）
    ret20_dict = {}
    for name, df in factor_data.items():
        r = df["Ret20"].groupby(df["Ret20"].index.to_period("M")).last()
        r.index = r.index.to_timestamp("M")
        ret20_dict[name] = r
    ret20_df = pd.DataFrame(ret20_dict).dropna(how="all")
    common20 = ret20_df.index.intersection(ret_df.index)
    ret20_df = ret20_df.loc[common20]
    ret_df20 = ret_df.loc[common20]

    r20_group = {g: [] for g in range(1, n_groups + 1)}
    r20_dates = []
    for i in range(1, len(ret20_df)):
        this_month = ret20_df.index[i]
        last_month = ret20_df.index[i - 1]
        sc = ret20_df.loc[last_month].dropna()
        rt = ret_df20.loc[this_month]
        if len(sc) < n_groups:
            continue
        sc = sc.clip(lower=sc.quantile(0.025), upper=sc.quantile(0.975))
        rk = sc.rank(method="first")
        n  = len(rk)
        for g in range(1, n_groups + 1):
            mem   = rk[(rk > (g-1)/n_groups*n) & (rk <= g/n_groups*n)].index
            vr    = rt.loc[mem.intersection(rt.index)].dropna()
            r20_group[g].append(vr.mean() if len(vr) > 0 else np.nan)
        r20_dates.append(this_month)

    r20_ret_df = pd.DataFrame(r20_group, index=r20_dates)
    r20_ret_df.columns = [f"G{g}" for g in range(1, n_groups + 1)]
    r20_ret_df["LS"] = r20_ret_df["G5"] - r20_ret_df["G1"]
    r20_nav = (1 + r20_ret_df.fillna(0)).cumprod()
    ls_r = r20_ret_df["LS"].dropna()
    ret20_stats = {
        "年化收益":   ls_r.mean() * 12,
        "年化波动":   ls_r.std()  * np.sqrt(12),
        "信息比率IR": (ls_r.mean() / ls_r.std()) * np.sqrt(12) if ls_r.std() > 0 else np.nan,
        "月度胜率":   (ls_r > 0).mean(),
    }

    # 多头净值曲线（费前 & 费后）
    g5_nav_gross = (1 + g5_gross.fillna(0)).cumprod()
    g5_nav_net   = (1 + g5_net.fillna(0)).cumprod()

    # 沪深300基准（对齐到G5的时间范围）
    hs300_monthly = get_hs300()
    hs300_aligned = hs300_monthly.reindex(g5_gross.index)
    hs300_nav     = (1 + hs300_aligned.fillna(0)).cumprod()

    # 超额收益 = G5费后 - 沪深300（同一时间段逐月相减）
    excess        = g5_net - hs300_aligned
    excess_stats  = _long_stats(excess, "超额收益")

    return {
        "nav": nav, "monthly_ret": group_ret_df, "stats": stats,
        "ret20_nav": r20_nav, "ret20_ret": r20_ret_df, "ret20_stats": ret20_stats,
        # 多头费后新增字段
        "g5_nav_gross":   g5_nav_gross,
        "g5_nav_net":     g5_nav_net,
        "g5_gross":       g5_gross,
        "g5_net":         g5_net,
        "turnovers":      to_s,
        "long_gross":     long_stats_gross,
        "long_net":       long_stats_net,
        "turnover_stats": turnover_stats,
        "cost_rate":      COST_ROUNDTRIP,
        # 沪深300基准新增字段
        "hs300_nav":      hs300_nav,
        "hs300_monthly":  hs300_aligned,
        "excess_stats":   excess_stats,
    }


# ════════════════════════════════════════════════════════════════
# 【第四步】随机森林回测
# ════════════════════════════════════════════════════════════════

# def run_ml_backtest(index_data: dict, factor_data: dict) -> dict:
#     """
#     随机森林月度回测。

#     特征：每个行业每月底的 M0、M1、Ret20
#     标签：下月该行业收益的截面排名（在训练集内计算，避免泄露）
#     训练：滚动扩展窗口，前36个月作为最小训练集
#     月度收益宽表：完全独立于训练数据，单独从index_data构造，彻底避免泄露
#     """
#     print("\n[随机森林回测] 开始...")

#     # ── 第1步：构造特征表 ──────────────────────────────────────
#     records = []
#     for name, df in factor_data.items():
#         m0 = df["M0"].groupby(df["M0"].index.to_period("M")).last()
#         m0.index = m0.index.to_timestamp("M")
#         m1 = df["M1"].groupby(df["M1"].index.to_period("M")).last()
#         m1.index = m1.index.to_timestamp("M")
#         ret20 = df["Ret20"].groupby(df["Ret20"].index.to_period("M")).last()
#         ret20.index = ret20.index.to_timestamp("M")

#         # 当月收益（只用于构造下月标签，不作为特征）
#         raw = index_data[name].set_index("date").sort_index()
#         raw["close"] = pd.to_numeric(raw["close"], errors="coerce")
#         mc = raw["close"].groupby(raw["close"].index.to_period("M")).last()
#         mc.index = mc.index.to_timestamp("M")
#         ret = mc.pct_change()

#         aligned = pd.DataFrame({"M0": m0, "M1": m1, "Ret20": ret20, "ret": ret}).dropna()
#         aligned["industry"] = name
#         records.append(aligned)

#     all_data = pd.concat(records).sort_index()
#     all_data = all_data.reset_index().rename(columns={"index": "date"})

#     # ── 第2步：构造标签（下月收益，排名在循环内计算）─────────────
#     all_data = all_data.sort_values(["industry", "date"])
#     all_data["next_ret"] = all_data.groupby("industry")["ret"].shift(-1)
#     all_data = all_data.dropna(subset=["next_ret", "M0", "M1", "Ret20"])
#     all_data = all_data.sort_values("date").reset_index(drop=True)

#     # ── 第3步：月度收益宽表（完全独立，不依赖all_data）────────────
#     # 这是关键：评估组合收益用的宽表和训练数据完全隔离
#     # 避免模型通过ret列间接接触到测试月数据
#     monthly_ret_wide = build_monthly_ret(index_data)

#     # ── 第4步：滚动扩展窗口训练和预测 ─────────────────────────────
#     FEATURES   = ["M0", "M1", "Ret20"]
#     MIN_MONTHS = 36

#     all_months       = sorted(all_data["date"].unique())
#     ml_group_returns = {g: [] for g in range(1, 6)}
#     ml_dates         = []

#     for t in range(MIN_MONTHS, len(all_months) - 1):
#         train_end     = all_months[t]
#         predict_month = all_months[t + 1]

#         # 训练集：train_end之前所有历史数据
#         train   = all_data[all_data["date"] <= train_end].copy()
#         # 预测集：train_end这个月的因子值（用来预测下月）
#         predict = all_data[all_data["date"] == train_end].copy()

#         if len(train) < 100 or len(predict) < 5:
#             continue

#         # 标签：在训练集内部按月计算next_ret的截面排名
#         # 不涉及任何测试集数据
#         train["next_ret_rank"] = train.groupby("date")["next_ret"].rank(method="first")

#         X_train = train[FEATURES].values
#         y_train = train["next_ret_rank"].values
#         X_pred  = predict[FEATURES].values

#         model = RandomForestRegressor(
#             n_estimators=100,
#             max_depth=1,        # 限制深度防止过拟合（样本量小时重要）
#             min_samples_leaf=5,
#             random_state=42,
#             n_jobs=-1
#         )
#         # 验证实验：随机打乱标签
#         # 如果IR仍然很高，说明存在结构性泄露
#         # y_train = y_train.copy()
#         # import random
#         # random.shuffle(y_train)
#         model.fit(X_train, y_train)
#         predict = predict.copy()
#         predict["pred_rank"] = model.predict(X_pred)

#         if predict_month not in monthly_ret_wide.index:
#             continue

#         # 按预测排名分5组，计算各组下月实际收益
#         predict_sorted = predict.sort_values("pred_rank")
#         n = len(predict_sorted)
#         for g in range(1, 6):
#             low     = int((g - 1) / 5 * n)
#             high    = int(g / 5 * n)
#             members = predict_sorted.iloc[low:high]["industry"].tolist()
#             gr      = monthly_ret_wide.loc[predict_month, members].dropna()
#             ml_group_returns[g].append(gr.mean() if len(gr) > 0 else np.nan)

#         ml_dates.append(predict_month)

#     # ── 第5步：整理结果 ────────────────────────────────────────
#     ml_ret_df = pd.DataFrame(ml_group_returns, index=ml_dates)
#     ml_ret_df.columns = [f"G{g}" for g in range(1, 6)]
#     ml_ret_df["LS"]   = ml_ret_df["G5"] - ml_ret_df["G1"]
#     ml_nav = (1 + ml_ret_df.fillna(0)).cumprod()
#     ls_ml  = ml_ret_df["LS"].dropna()
#     ml_stats = {
#         "年化收益":   ls_ml.mean() * 12,
#         "年化波动":   ls_ml.std()  * np.sqrt(12),
#         "信息比率IR": (ls_ml.mean() / ls_ml.std()) * np.sqrt(12) if ls_ml.std() > 0 else np.nan,
#         "月度胜率":   (ls_ml > 0).mean(),
#     }

#     return {"nav": ml_nav, "monthly_ret": ml_ret_df, "stats": ml_stats}


# ════════════════════════════════════════════════════════════════
# 【第五步】可视化
# ════════════════════════════════════════════════════════════════

def plot_results(result: dict):
    """
    四张图：
      左上：黄金律五分组净值
      右上：Ret20基准五分组净值
      左下：G5多头 费前 vs 费后净值曲线 + 月换手率（副轴）
      右下：绩效对比表（含多头费前/费后）
    """
    fig = plt.figure(figsize=(20, 10))
    fig.suptitle("《A股行业动量的精细结构》复现 · 含费用分析", fontsize=14, fontweight="bold")
    fig.text(0.5, 0.95, f"回测区间：{START_DATE} → {END_DATE}  |  单边成本假设：{result['cost_rate']*100:.2f}%",
             ha="center", fontsize=10, color="gray")

    ax0 = fig.add_subplot(2, 2, 1)
    ax1 = fig.add_subplot(2, 2, 2)
    ax2 = fig.add_subplot(2, 2, 3)
    ax3 = fig.add_subplot(2, 2, 4)

    colors = ["#d62728", "#ff7f0e", "#bcbd22", "#2ca02c", "#1f77b4"]

    # ── 图1：黄金律五分组 ─────────────────────────────────────
    for i, col in enumerate([f"G{g}" for g in range(1, 6)]):
        if col in result["nav"].columns:
            ax0.plot(result["nav"].index, result["nav"][col],
                     color=colors[i], label=f"第{i+1}组", linewidth=1.2)
    ax0.plot(result["nav"].index, result["nav"]["LS"],
             color="black", linestyle="--", label="多空对冲", linewidth=1.5)
    ax0.set_title("黄金律模型：五分组净值")
    ax0.legend(fontsize=7); ax0.grid(alpha=0.3)
    ax0.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # ── 图2：Ret20基准 ────────────────────────────────────────
    for i, col in enumerate([f"G{g}" for g in range(1, 6)]):
        if col in result["ret20_nav"].columns:
            ax1.plot(result["ret20_nav"].index, result["ret20_nav"][col],
                     color=colors[i], label=f"第{i+1}组", linewidth=1.2)
    ax1.plot(result["ret20_nav"].index, result["ret20_nav"]["LS"],
             color="black", linestyle="--", label="多空对冲", linewidth=1.5)
    ax1.set_title("Ret20基准：五分组净值（研报IR≈0.47）")
    ax1.legend(fontsize=7); ax1.grid(alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # ── 图3：多头费前 vs 费后 vs 沪深300净值 + 换手率 ────────────
    ax2.plot(result["g5_nav_gross"].index, result["g5_nav_gross"],
             color="#1f77b4", linewidth=1.5, label="G5 费前")
    ax2.plot(result["g5_nav_net"].index, result["g5_nav_net"],
             color="#d62728", linewidth=1.5, linestyle="--", label="G5 费后")
    ax2.plot(result["hs300_nav"].index, result["hs300_nav"],
             color="#2ca02c", linewidth=1.5, linestyle=":", label="沪深300")
    ax2.set_title("G5多头 vs 沪深300基准")
    ax2.legend(loc="upper left", fontsize=8); ax2.grid(alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    ax2r = ax2.twinx()
    ax2r.bar(result["turnovers"].index, result["turnovers"].values * 100,
             color="gray", alpha=0.25, width=20, label="月换手率%")
    ax2r.set_ylabel("月换手率 (%)", fontsize=8, color="gray")
    ax2r.tick_params(axis="y", colors="gray")
    ax2r.legend(loc="upper right", fontsize=7)

    # ── 图4：绩效对比表（含超额收益列） ──────────────────────────
    ax3.axis("off")
    g  = result["long_gross"]
    n  = result["long_net"]
    ex = result["excess_stats"]
    ts = result["turnover_stats"]
    s  = result["stats"]
    sr = result["ret20_stats"]

    table_data = [
        ["指标",        "G5费前多头",                       "G5费后多头",
                        "超额(费后-HS300)",                 "LS多空(黄金律)"],
        ["年化收益",    f"{g['多头费前_年化收益']:.2%}",     f"{n['多头费后_年化收益']:.2%}",
                        f"{ex['超额收益_年化收益']:.2%}",   f"{s['年化收益']:.2%}"],
        ["年化波动",    f"{g['多头费前_年化波动']:.2%}",     f"{n['多头费后_年化波动']:.2%}",
                        f"{ex['超额收益_年化波动']:.2%}",   f"{s['年化波动']:.2%}"],
        ["夏普/IR",     f"{g['多头费前_夏普']:.2f}",         f"{n['多头费后_夏普']:.2f}",
                        f"{ex['超额收益_夏普']:.2f}",       f"{s['信息比率IR']:.2f}"],
        ["月度胜率",    f"{g['多头费前_月度胜率']:.2%}",     f"{n['多头费后_月度胜率']:.2%}",
                        f"{ex['超额收益_月度胜率']:.2%}",   f"{s['月度胜率']:.2%}"],
        ["最大回撤",    f"{g['多头费前_最大回撤']:.2%}",     f"{n['多头费后_最大回撤']:.2%}",
                        f"{ex['超额收益_最大回撤']:.2%}",   "—"],
        ["─" * 8,       "─" * 10,  "─" * 10,  "─" * 10,  "─" * 10],
        ["平均月换手",  f"{ts['平均月换手率']:.1%}",         "—",  "—",  "—"],
        ["年化费用拖累",f"{ts['年化费用拖累']:.2%}",         "—",  "—",  "—"],
    ]

    tbl = ax3.table(cellText=table_data, loc="center", cellLoc="center")
    tbl.auto_set_font_size(False); tbl.set_fontsize(8.5); tbl.scale(1.0, 1.7)
    for (r, c), cell in tbl.get_celld().items():
        if r == 0:
            cell.set_facecolor("#2c5f8a"); cell.set_text_props(color="white", fontweight="bold")
        elif r == 6:
            cell.set_facecolor("#f0f0f0")
        elif r % 2 == 0:
            cell.set_facecolor("#eaf1f8")
    ax3.set_title("绩效对比（含超额收益分析）", pad=10)

    plt.tight_layout(rect=[0, 0, 1, 0.90])

    counter_path = f"{RESULT_DIR}/counter.txt"
    n = 1
    if os.path.exists(counter_path):
        with open(counter_path, "r") as f:
            n = int(f.read()) + 1
    with open(counter_path, "w") as f:
        f.write(str(n))

    save_path = f"{RESULT_DIR}/黄金律{n}.png"
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"\n图表已保存至 {save_path}")
    plt.show()


# ════════════════════════════════════════════════════════════════
# 【主流程】
# ════════════════════════════════════════════════════════════════

def main():
    print("=" * 55)
    print("  《A股行业动量的精细结构》复现")
    print(f"  回测区间: {START_DATE} → {END_DATE}")
    print(f"  因子回溯: {LOOKBACK} 个交易日")
    print("=" * 55)

    # 第一步：下载数据
    print("\n[Step 1] 下载申万行业指数日行情...")
    index_data = {}
    for code, name in SW_INDUSTRIES.items():
        df = get_index_daily(code, name)
        if not df.empty:
            df = df[(df["date"] >= START_DATE) & (df["date"] <= END_DATE)]
            if not df.empty:
                index_data[name] = df
    print(f"  成功获取 {len(index_data)}/28 个行业")
    if len(index_data) < 10:
        print("[错误] 数据不足，请检查网络后重试")
        return

    # 第二步：计算因子
    factor_data = calc_factors(index_data)

    # 第三步：黄金律回测
    result = run_backtest(index_data, factor_data)
    print("\n[结果] 黄金律模型（多空）：")
    for k, v in result["stats"].items():
        print(f"  {k}: {v:.4f}")
    print("\n[结果] Ret20基准：")
    for k, v in result["ret20_stats"].items():
        print(f"  {k}: {v:.4f}")
    print("\n[结果] 黄金律各组平均月收益（应单调递增）：")
    print(result["monthly_ret"].mean().to_string())

    # ── 费后专项打印 ──────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  G5 多头费前/费后分析")
    print("=" * 55)
    print("\n[换手率统计]")
    for k, v in result["turnover_stats"].items():
        print(f"  {k}: {v:.2%}")
    print("\n[G5 多头费前]")
    for k, v in result["long_gross"].items():
        print(f"  {k}: {v:.4f}")
    print("\n[G5 多头费后]")
    for k, v in result["long_net"].items():
        print(f"  {k}: {v:.4f}")

    # # 第四步：随机森林回测
    # ml_result = run_ml_backtest(index_data, factor_data)
    # print("\n[结果] 随机森林模型：")
    # for k, v in ml_result["stats"].items():
    #     print(f"  {k}: {v:.4f}")
    # print("\n[结果] 随机森林各组平均月收益（应单调递增）：")
    # print(ml_result["monthly_ret"].mean().to_string())

    print("\n[G5 超额收益（费后 - 沪深300）]")
    for k, v in result["excess_stats"].items():
        print(f"  {k}: {v:.4f}")

    # 第五步：画图保存
    plot_results(result)

    print("\n✅ 复现完成！")


if __name__ == "__main__":
    main()
