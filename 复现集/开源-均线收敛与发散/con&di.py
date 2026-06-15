"""
均线收敛因子复现框架 v3
复现开源证券研报《形态识别：均线的收敛与发散》

v3 改进（相比 v2）：
  1. 数据源切换为本地 H5 文件，覆盖全市场所有 A 股（含已退市）
     数据路径：均线收敛数据/data/
       - adjclose.h5   后复权收盘价   shape: (dates, stocks)
       - volume.h5     成交量         shape: (dates, stocks)
       - amount.h5     成交额         shape: (dates, stocks)
       - turn.h5       换手率         shape: (dates, stocks)
       - calendar.h5   交易日历       (dates,)
       - meta_Dataset  股票元信息     含 code / name / industry 等字段
  2. 全市场覆盖，大幅消除幸存者偏差
  3. 行业分类直接从 meta_Dataset 读取，无需爬取

v2 功能保留：
  · 随机抽样（可选，改 N_STOCKS=None 使用全量）
  · ST/停牌/新股过滤
  · 行业市值中性化（OLS 残差）
  · PVCF 截面 z-score 合成

原 akshare 爬取代码已全部注释保留（见第一部分）。
"""

import os
import random
import time
import warnings

# import akshare as ak   # v2 爬虫依赖，本地数据模式下不再需要，保留备用
import h5py
import hdf5plugin          # 注册 Blosc 等第三方 HDF5 压缩插件（pip install hdf5plugin）
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
random.seed(42) # 随机选股做回测
np.random.seed(42) # 同上

# 中文字体（macOS: PingFang SC；Linux/Windows: SimHei 作后备）
matplotlib.rcParams['font.sans-serif'] = [
    'PingFang SC', 'Arial Unicode MS', 'STHeiti', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

# ============================================================
# 本地数据路径配置（根据实际存放位置修改 DATA_DIR）
# ============================================================
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        '均线收敛数据', 'data')
INDUSTRY_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              '均线收敛数据', 'sw_industry_map.csv')


# ============================================================
# 第一部分：数据获取
# ============================================================
# ──────────────────────────────────────────────────────────
# [v2 akshare 爬取代码，已注释保留，如需恢复取消注释即可]
# ──────────────────────────────────────────────────────────

# def get_stock_list(exclude_st: bool = True) -> list:
#     """
#     获取 A 股非 ST 股票列表。
#     注意：使用当前存活列表，仍有幸存者偏差；历史退市股票无法纳入。
#     """
#     df = ak.stock_info_a_code_name()
#     if exclude_st:
#         df = df[~df['name'].str.contains('ST', na=False)]
#     return df['code'].tolist()
#
#
# def get_daily_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
#     """拉取单只股票后复权日线数据。"""
#     try:
#         df = ak.stock_zh_a_hist(
#             symbol=symbol,
#             period="daily",
#             start_date=start_date,
#             end_date=end_date,
#             adjust="hfq",
#         )
#         df = df.rename(columns={
#             '日期': 'date',
#             '收盘': 'close',
#             '成交量': 'volume',
#             '成交额': 'amount',
#             '换手率': 'turnover',
#         })
#         df['date'] = pd.to_datetime(df['date'])
#         df['symbol'] = symbol
#         return df[['date', 'symbol', 'close', 'volume', 'amount', 'turnover']]\
#                .sort_values('date').reset_index(drop=True)
#     except Exception as e:
#         print(f"  {symbol} 获取失败: {e}")
#         return pd.DataFrame()
#
#
# def get_batch_data(symbols: list, start_date: str, end_date: str,
#                    n_stocks: int = 300) -> pd.DataFrame:
#     """
#     随机抽取 n_stocks 只股票并批量拉取。
#     随机抽样是关键：原来取前 50 只，代码排序靠前的全是深市最早上市的大市值蓝筹，
#     导致样本严重偏向大市值，TRCF（专为小市值设计）天然跑不出来。
#     """
#     sampled = random.sample(symbols, min(n_stocks, len(symbols)))
#     all_data = []
#     for i, sym in enumerate(sampled):
#         print(f"  拉取 {sym} ({i+1}/{len(sampled)})", end='\r')
#         df = get_daily_data(sym, start_date, end_date)
#         if not df.empty:
#             all_data.append(df)
#     print(f"\n  完成，共获取 {len(all_data)} 只股票数据")
#     return pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()
#
#
# def get_industry_map(symbols: list) -> dict:
#     """
#     通过东方财富行业板块 API 获取股票→行业分类映射。
#     实现方式：遍历所有行业名称，拉取每个行业的成分股，反向建立映射。
#     约需 30~50 次 API 调用，耗时 1~2 分钟。
#     """
#     print("  正在获取行业分类（约需 1~2 分钟）...")
#     symbol_set = set(str(s).zfill(6) for s in symbols)
#     industry_map = {}
#     try:
#         industries = ak.stock_board_industry_name_em()
#         total = len(industries)
#         for i, (_, row) in enumerate(industries.iterrows()):
#             ind_name = row['板块名称']
#             print(f"  行业 {i+1}/{total}: {ind_name:<12}", end='\r')
#             try:
#                 cons = ak.stock_board_industry_cons_em(symbol=ind_name)
#                 for code in cons['代码'].astype(str).str.zfill(6):
#                     if code in symbol_set:
#                         industry_map[code] = ind_name
#             except Exception:
#                 continue
#             time.sleep(1)  # 每次请求后暂停 1 秒，避免高频触发限流
#         print(f"\n  共获取 {len(industry_map)} 只股票的行业分类")
#     except Exception as e:
#         print(f"\n  行业数据获取失败（{e}），将跳过行业中性化")
#     return industry_map

# ──────────────────────────────────────────────────────────
# [v3 本地 H5 数据读取]
# 使用 h5py + hdf5plugin 读取（hdf5plugin 提供 Blosc 压缩支持）
# 依赖：pip install h5py hdf5plugin
# ──────────────────────────────────────────────────────────

def load_h5_matrix(fname: str) -> tuple[pd.DataFrame, list, list]:
    """
    读取单个价量 H5 文件，返回 (DataFrame, dates, codes)。

    文件是 pandas HDFStore 格式，结构：
      GROUP  <varname>/
        axis0         (N,)    |S9     股票代码（bytes）
        axis1         (T,)    int64   时间戳 nanoseconds
        block0_values (T, N)  float64 数据矩阵
    """
    fpath = os.path.join(DATA_DIR, fname)
    with h5py.File(fpath, 'r') as f:
        root_key = list(f.keys())[0]
        grp = f[root_key]

        raw_codes = grp['axis0'][()]
        codes = [c.decode().strip() if isinstance(c, bytes) else str(c).strip()
                 for c in raw_codes]
        codes = [c.zfill(6) if c.isdigit() else c for c in codes]

        ts_ns = grp['axis1'][()]
        dates = pd.to_datetime(ts_ns, unit='ns')

        data = grp['block0_values'][()]   # (T, N)

    df = pd.DataFrame(data, index=dates, columns=codes)
    return df, list(dates), codes


def load_calendar(fname: str = 'calendar.h5') -> pd.DatetimeIndex:
    """读取交易日历。calendar.h5 中时间戳在 dates/block0_values，shape=(T, 1)。"""
    fpath = os.path.join(DATA_DIR, fname)
    with h5py.File(fpath, 'r') as f:
        ts_ns = f['dates']['block0_values'][()].flatten()
    return pd.to_datetime(ts_ns, unit='ns')


def load_meta(fname: str = 'meta_Dataset') -> pd.DataFrame:
    """
    读取股票元信息文件。
    预期包含字段：code(股票代码), name(股票名称), industry(行业)。
    当前数据集 meta_Dataset 只含 startDate/endDate，行业信息缺失属正常情况，
    返回空 DataFrame，中性化步骤会自动跳过。
    """
    fpath = os.path.join(DATA_DIR, fname)
    import pickle
    with open(fpath, 'rb') as f:
        obj = pickle.load(f)

    if isinstance(obj, pd.DataFrame):
        meta = obj
    elif isinstance(obj, dict):
        # 检查是否有实质性的股票信息（非 startDate/endDate 这类元数据）
        useful_keys = [k for k in obj.keys()
                       if k.lower() not in ('startdate', 'enddate', 'start_date', 'end_date')]
        if not useful_keys:
            return pd.DataFrame()   # 只有日期范围信息，无股票数据
        meta = pd.DataFrame(obj)
    else:
        meta = pd.DataFrame(obj)

    # 统一列名
    rename_map = {}
    for col in meta.columns:
        cl = col.lower()
        if cl in ('code', 'symbol', '代码', 'stock_code'):
            rename_map[col] = 'code'
        elif cl in ('name', '名称', 'stock_name', 'stkname'):
            rename_map[col] = 'name'
        elif cl in ('industry', 'ind', '行业', 'sector', 'indname', 'industry_name'):
            rename_map[col] = 'industry'
    meta = meta.rename(columns=rename_map)

    if 'code' in meta.columns:
        meta['code'] = meta['code'].astype(str).str.zfill(6)

    return meta


def load_or_fetch_industry_map(codes: list) -> dict:
    """
    返回 {6位代码 -> 申万一级行业名称} 映射。
    优先读本地缓存，无缓存则通过 akshare 批量获取并写入缓存（仅需一次）。
    """
    pure_codes = {c[:6] for c in codes}

    if os.path.exists(INDUSTRY_CACHE):
        cache = pd.read_csv(INDUSTRY_CACHE, dtype=str)
        industry_map = dict(zip(cache['code'], cache['industry']))
        matched = {k: v for k, v in industry_map.items() if k in pure_codes}
        print(f"  行业分类：从缓存加载 {len(matched)}/{len(pure_codes)} 只")
        return matched

    print("  行业分类：缓存不存在，从 akshare 拉取申万一级行业（约1分钟）...")
    try:
        import akshare as ak
        sw_first = ak.sw_index_first_info()
    except Exception as e:
        print(f"  ⚠ 申万行业列表获取失败（{e}），跳过中性化")
        return {}

    industry_map: dict = {}
    total = len(sw_first)
    for i, (_, row) in enumerate(sw_first.iterrows()):
        sw_code  = str(row['行业代码']).split('.')[0]
        ind_name = row['行业名称']
        print(f"  [{i+1}/{total}] {ind_name:<8}", end='\r')
        try:
            cons = ak.index_component_sw(symbol=sw_code)
            for stock_code in cons['证券代码'].astype(str).str.zfill(6):
                industry_map[stock_code] = ind_name
        except Exception:
            continue

    print(f"\n  共获取 {len(industry_map)} 只股票的申万行业分类")
    os.makedirs(os.path.dirname(INDUSTRY_CACHE), exist_ok=True)
    pd.DataFrame({'code': list(industry_map.keys()),
                  'industry': list(industry_map.values())})\
      .to_csv(INDUSTRY_CACHE, index=False)
    print(f"  行业分类已缓存至 {INDUSTRY_CACHE}")

    matched = {k: v for k, v in industry_map.items() if k in pure_codes}
    return matched


def load_local_data(start_date: str, end_date: str,
                    n_stocks: int | None = None,
                    exclude_st: bool = True) -> tuple[pd.DataFrame, dict]:
    """
    从本地 H5 文件加载全部数据，组装成与 v2 相同格式的面板 DataFrame。

    返回
    ----
    raw_df      : long-format DataFrame，列：date, symbol, close, volume, amount, turnover
    industry_map: {code -> industry_name}
    """
    print(f"  数据目录: {DATA_DIR}")

    # ── 1. 读取交易日历（可选） ────────────────────────────────
    try:
        calendar = load_calendar('calendar.h5')
        print(f"  交易日历: {len(calendar)} 个交易日 "
              f"({calendar[0].date()} ~ {calendar[-1].date()})")
    except Exception as e:
        print(f"  ⚠ 交易日历读取失败（{e}），将从价格矩阵推断日期")
        calendar = None

    # ── 2. 读取元信息（行业 & 名称） ──────────────────────────
    industry_map: dict = {}
    st_codes: set = set()
    try:
        meta = load_meta('meta_Dataset')
        if meta.empty:
            print("  ℹ 元信息无股票数据（仅含日期范围），跳过行业分类 & ST 过滤")
        else:
            print(f"  元信息: {len(meta)} 条，列={list(meta.columns)}")
            if 'code' in meta.columns and 'industry' in meta.columns:
                industry_map = meta.dropna(subset=['industry'])\
                                   .set_index('code')['industry'].to_dict()
                print(f"  行业映射: {len(industry_map)} 只")
            if exclude_st and 'code' in meta.columns and 'name' in meta.columns:
                st_codes = set(
                    meta[meta['name'].str.contains('ST', na=False)]['code']
                )
                print(f"  ST 股过滤: {len(st_codes)} 只")
    except Exception as e:
        print(f"  ⚠ 元信息读取失败（{e}），跳过行业分类 & ST 过滤")

    # ── 3. 读取四个价量矩阵 ───────────────────────────────────
    print("  读取 adjclose.h5 ...")
    df_close,  dates_c, codes_c = load_h5_matrix('adjclose.h5')

    print("  读取 volume.h5 ...")
    df_volume, dates_v, codes_v = load_h5_matrix('volume.h5')

    print("  读取 amount.h5 ...")
    df_amount, dates_a, codes_a = load_h5_matrix('amount.h5')

    print("  读取 turn.h5 ...")
    df_turn,   dates_t, codes_t = load_h5_matrix('turn.h5')

    # 用 calendar 替换整数索引（仅布局 B 时需要）
    if calendar is not None:
        for df, name in [(df_close,'close'),(df_volume,'volume'),
                         (df_amount,'amount'),(df_turn,'turn')]:
            if df.index.dtype == 'int64' and len(df) == len(calendar):
                df.index = calendar
            elif df.index.dtype == 'int64':
                print(f"  ⚠ {name} 行数({len(df)}) ≠ calendar({len(calendar)})，保留原整数索引")

    # ── 4. 对齐日期 & 截取时间范围 ────────────────────────────
    t0, t1 = pd.Timestamp(start_date), pd.Timestamp(end_date)
    common_codes = (set(df_close.columns) & set(df_volume.columns)
                    & set(df_amount.columns) & set(df_turn.columns))
    common_codes = sorted(common_codes)

    df_close  = df_close .loc[t0:t1, common_codes]
    df_volume = df_volume.loc[t0:t1, common_codes]
    df_amount = df_amount.loc[t0:t1, common_codes]
    df_turn   = df_turn  .loc[t0:t1, common_codes]

    n_days = len(df_close)
    print(f"  对齐后：{n_days} 个交易日 × {len(common_codes)} 只股票")

    # ── 各文件覆盖诊断（幸存者偏差风险评估）────────────────────────
    sizes = {
        'close': len(codes_c), 'volume': len(codes_v),
        'amount': len(codes_a), 'turn':   len(codes_t),
        'intersection': len(common_codes),
    }
    print(f"  各文件股票数：{ {k: v for k, v in sizes.items()} }")

    # 按价格矩阵统计：有数据天数 < 95% 交易日 → 视为非全程股票（含新股/退市股）
    has_data   = (df_close.notna() & (df_close > 0))
    coverage   = has_data.sum(axis=0) / n_days
    n_partial  = int((coverage < 0.95).sum())
    n_full     = int((coverage >= 0.95).sum())
    print(f"  数据覆盖诊断：全程存活（≥95%交易日）{n_full} 只 | "
          f"部分期间（含新股/退市股）{n_partial} 只")

    # ── 5. 可选随机抽样 ───────────────────────────────────────
    all_codes = list(common_codes)
    if exclude_st:
        all_codes = [c for c in all_codes if c not in st_codes]
        print(f"  去 ST 后：{len(all_codes)} 只")

    if n_stocks is not None and n_stocks < len(all_codes):
        sampled_codes = random.sample(all_codes, n_stocks)
        print(f"  随机抽样：{n_stocks} 只")
    else:
        sampled_codes = all_codes
        print(f"  使用全量：{len(sampled_codes)} 只")

    df_close  = df_close [sampled_codes]
    df_volume = df_volume[sampled_codes]
    df_amount = df_amount[sampled_codes]
    df_turn   = df_turn  [sampled_codes]

    # ── 6. 宽表 → 长表（stack） ───────────────────────────────
    print("  拼合面板数据（stack）...")
    raw_df = pd.DataFrame({
        'close'   : df_close .stack(),
        'volume'  : df_volume.stack(),
        'amount'  : df_amount.stack(),
        'turnover': df_turn  .stack(),
    })
    raw_df.index.names = ['date', 'symbol']
    raw_df = raw_df.reset_index()

    # 过滤停牌（成交量为 0 或 NaN）
    raw_df = raw_df[raw_df['volume'].fillna(0) > 0].copy()
    print(f"  过滤停牌后：{raw_df.shape}，"
          f"{raw_df['symbol'].nunique()} 只，"
          f"{raw_df['date'].nunique()} 个交易日")

    # ── 7. 行业分类（申万一级，带本地缓存）────────────────────────
    industry_map_raw = load_or_fetch_industry_map(sampled_codes)
    industry_map = {}
    for code in sampled_codes:
        pure = code[:6]
        if pure in industry_map_raw:
            industry_map[code] = industry_map_raw[pure]
    covered = sum(1 for c in sampled_codes if c[:6] in industry_map_raw)
    print(f"  行业覆盖：{covered}/{len(sampled_codes)} 只（"
          f"{covered/len(sampled_codes)*100:.1f}%）")

    return raw_df, industry_map


# ============================================================
# 第二部分：因子计算
# 研报核心公式：factor = -log(1 + std(ma1, ma5, ma10, ma20, ma60, ma120))
# ============================================================

MA_PERIODS    = [1, 5, 10, 20, 60, 120]
MAX_MA_PERIOD = max(MA_PERIODS)   # MA120 预热期长度，前 119 行因子不完整

MA_PERIODS = [1, 5, 10, 20, 60, 120]

# ============================================================
# 量纲处理方式（可选）
# 'absolute'：研报原始公式，std(MAs) 为绝对离散度——存在量纲差异
# 'relative'：真正去量纲——用变异系数 CV = std(MAs)/mean(MAs)
#             代替绝对 std，使不同价格/成交量/成交额水平的股票
#             "相对收敛程度"直接可比
#
# 注意：这不是统计上的截面标准化（z-score），而是修改了因子
# 定义本身——会真正改变截面排序、真正改变 RankIC 结果（不是
# <1% 的噪声级别变化）。这相当于在研报因子基础上构造了一个
# "相对收敛因子"变体，不再是对研报原始因子的复现。
#
# 切换方式：改这一行即可，calc_all_factors 不需要改动
# ============================================================
DISPERSION_MODE = 'relative'  # 改成 'relative' 即可启用真正去量纲版本


def calc_convergence_factor(series: pd.Series,
                             periods: list = MA_PERIODS,
                             mode: str = None) -> pd.Series:
    """计算单只股票的收敛因子（适用于价格/成交量/成交额/换手率）。

    mode='absolute'：std(MAs)，研报原始公式
    mode='relative'：std(MAs)/mean(MAs)（变异系数 CV），真正去量纲
    """
    if mode is None:
        mode = DISPERSION_MODE

    mas = pd.DataFrame({
        f'ma{p}': series.rolling(p, min_periods=p).mean()
        for p in periods
    })

    if mode == 'relative':
        dispersion = mas.std(axis=1) / (mas.mean(axis=1) + 1e-8)
    else:
        dispersion = mas.std(axis=1)

    return -np.log(1 + dispersion)




def calc_all_factors(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算单只股票的 PCF / VCF / ACF / TRCF。
    PVCF 需要全市场截面数据，不在此处计算，在面板拼合后调用 calc_pvcf()。
    """
    result = df.copy()
    result['PCF']  = calc_convergence_factor(df['close'])
    result['VCF']  = calc_convergence_factor(df['volume'])
    result['ACF']  = calc_convergence_factor(df['amount'])
    result['TRCF'] = calc_convergence_factor(df['turnover'])
    return result


def calc_pvcf(panel_df: pd.DataFrame) -> pd.DataFrame:
    """
    在面板数据上做截面 z-score 后合成 PVCF。
    研报原文："将 PCF 与 VCF 在截面进行标准化后进行加总"。
    截面标准化 = 同一日期下对所有股票做 z-score，必须在面板拼合后调用。
    """
    panel_df = panel_df.copy()

    def cross_zscore(col: str) -> pd.Series:
        return panel_df.groupby('date')[col].transform(
            lambda x: (x - x.mean()) / (x.std() + 1e-8)
        )

    panel_df['PVCF'] = cross_zscore('PCF') + cross_zscore('VCF')
    return panel_df

def standardize_factors(panel_df: pd.DataFrame, factor_cols: list) -> pd.DataFrame:
    """
    对指定因子做截面 z-score 标准化，去除不同个股之间的量纲差异。

    逻辑与 calc_pvcf 中的 cross_zscore 完全一致：
    同一日期下，对所有股票的该因子值做 (x - mean) / (std + eps)。

    研报原文（PCF 部分）："且在因子构建时未剔除截面上不同个股价格
    数值的量纲差异。"——即 PCF / VCF / ACF / TRCF 默认都不做这一步。
    本函数提供一个可选的去量纲版本，用于对比测试其对 RankIC 的影响。

    注意：
    - 对 TRCF 而言，换手率本身已是比率（已无量纲），做 z-score
      只是单调变换，不会改变其 RankIC / 分组回测结果。
    - 对 PCF / VCF / ACF 而言，z-score 会把"个股自身价格/成交量/
      成交额绝对水平"这部分信息剔除，只保留截面相对位置信息。
    """
    panel_df = panel_df.copy()
    for col in factor_cols:
        panel_df[col] = panel_df.groupby('date')[col].transform(
            lambda x: (x - x.mean()) / (x.std() + 1e-8)
        )
    return panel_df


def winsorize_factors(panel_df: pd.DataFrame,
                      factor_cols: list,
                      n_std: float = 3.0) -> pd.DataFrame:
    """
    截面 Winsorize：将每个截面日期的因子值截断在 ±n_std 标准差之内。
    去除成交额/换手率等数据中的极端异常点，防止 IC 被单个离群股主导。
    """
    panel_df = panel_df.copy()
    for col in factor_cols:
        def _clip(x, n=n_std):
            mu, sigma = x.mean(), x.std()
            return x.clip(mu - n * sigma, mu + n * sigma)
        panel_df[col] = panel_df.groupby('date')[col].transform(_clip)
    return panel_df


# ============================================================
# 第三部分：行业市值中性化
# 研报默认对所有因子做行业市值中性化后再计算 IC
# ============================================================

def estimate_float_mktcap(panel_df: pd.DataFrame) -> pd.DataFrame:
    """
    从现有数据估算流通市值，无需额外 API 调用。

    推导：
      turnover(%) = 成交量 / 流通股数 × 100
      amount      = 成交量 × 价格
      ⟹  amount / (turnover/100) = 价格 × 流通股数 = 流通市值

    停牌日 turnover=0 会产生 inf，已用 replace(0, nan) 处理。
    """
    panel_df = panel_df.copy()
    t = panel_df['turnover'].replace(0, np.nan)
    panel_df['float_mktcap'] = panel_df['amount'] / (t / 100)
    panel_df['log_mktcap']   = np.log(panel_df['float_mktcap'].clip(lower=1))
    return panel_df


def _neutralize_one_date(group: pd.DataFrame, col: str) -> pd.Series:
    """
    对单个截面日期的某因子做行业市值中性化：
      factor_i = Σ β_k × industry_dummy_ki + γ × log_mktcap_i + ε_i
    返回残差 ε 作为中性化后的因子值。
    """
    valid = group[[col, 'industry', 'log_mktcap']].dropna()

    # 至少 20 只股票、至少 2 个行业才做中性化，否则原样返回
    if len(valid) < 20 or valid['industry'].nunique() < 2:
        return group[col]

    X_ind = pd.get_dummies(valid['industry'], drop_first=True).astype(float)
    X = np.column_stack([
        np.ones(len(valid)),
        valid['log_mktcap'].values,
        X_ind.values,
    ])
    y = valid[col].values

    try:
        coeffs, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        residuals = y - X @ coeffs
        result = group[col].copy()
        result.loc[valid.index] = residuals
        return result
    except Exception:
        return group[col]


def neutralize_factors(panel_df: pd.DataFrame,
                       factor_cols: list) -> pd.DataFrame:
    """
    对所有因子逐截面做行业市值中性化。
    如果 'industry' 列全为 NaN（行业获取失败），输出警告后跳过。
    """
    if 'industry' not in panel_df.columns or panel_df['industry'].isna().all():
        print("  ⚠ 无行业数据，跳过中性化（结果与研报差距会更大）")
        return panel_df

    panel_df = panel_df.copy()
    for col in factor_cols:
        print(f"  中性化 {col} ...", end='\r')
        parts = [
            _neutralize_one_date(group, col)
            for _, group in panel_df.groupby('date')
        ]
        panel_df[col] = pd.concat(parts).reindex(panel_df.index)

    print(f"  行业市值中性化完成（{len(factor_cols)} 个因子）        ")
    return panel_df


# ============================================================
# 第四部分：因子评价
# ============================================================

def calc_forward_return(df: pd.DataFrame, n_days: int = 20) -> pd.DataFrame:
    """
    计算未来 N 日收益率。
    pct_change(n).shift(-n) 在位置 t = close[t+n]/close[t]-1，即正确的 N 日前向收益。
    """
    df = df.copy()
    df['fwd_return'] = df['close'].pct_change(n_days).shift(-n_days)
    return df


def calc_rank_ic(factor_values: pd.Series,
                 forward_returns: pd.Series) -> float:
    valid = pd.concat([factor_values, forward_returns], axis=1).dropna()
    if len(valid) < 10:
        return np.nan
    return valid.iloc[:, 0].corr(valid.iloc[:, 1], method='spearman')


def evaluate_factors(panel_df: pd.DataFrame,
                     factor_cols: list,
                     fwd_return_col: str = 'fwd_return',
                     freq: str = 'monthly') -> tuple:
    """
    计算截面 RankIC 序列并汇总统计。
    年化 IR：月频 × sqrt(12)，周频 × sqrt(52)。

    研报使用月频截面 IC。必须先采样到月末/周末交易日，
    否则 20 日重叠收益窗口导致 IC 序列高度自相关，ICIR 完全失真。
    """
    annualize = np.sqrt(12) if freq == 'monthly' else np.sqrt(52)
    period    = 'M'         if freq == 'monthly' else 'W'

    all_dates    = pd.DatetimeIndex(sorted(panel_df['date'].unique()))
    sample_dates = set(
        pd.Series(all_dates)
        .groupby(pd.Series(all_dates).dt.to_period(period))
        .last()
    )
    eval_df = panel_df[panel_df['date'].isin(sample_dates)]
    print(f"  IC 评价：{len(sample_dates)} 个{'月末' if freq=='monthly' else '周末'}截面")

    results = {}
    for date, group in eval_df.groupby('date'):
        results[date] = {
            col: calc_rank_ic(group[col], group[fwd_return_col])
            for col in factor_cols
        }

    ic_df = pd.DataFrame(results).T
    summary = pd.DataFrame({
        'RankIC均值':     ic_df.mean(),
        'RankIC标准差':   ic_df.std(),
        'RankICIR(年化)': ic_df.mean() / ic_df.std() * annualize,
        'IC>0胜率':       (ic_df > 0).mean(),
    })
    return ic_df, summary


# ============================================================
# 第五部分：分组回测
# ============================================================

def group_backtest(panel_df: pd.DataFrame,
                   factor_col: str,
                   n_groups: int = 5,
                   fwd_return_col: str = 'fwd_return') -> pd.DataFrame:
    """按因子值五分组，验证各组收益单调性。"""
    group_returns = []
    for date, group in panel_df.groupby('date'):
        valid = group[[factor_col, fwd_return_col]].dropna().copy()
        if len(valid) < n_groups * 2:
            continue
        valid['group'] = pd.qcut(
            valid[factor_col], n_groups,
            labels=range(n_groups), duplicates='drop'
        )
        row = valid.groupby('group')[fwd_return_col].mean().to_dict()
        row['date'] = date
        group_returns.append(row)

    if not group_returns:
        return pd.DataFrame()
    return pd.DataFrame(group_returns).set_index('date')


# ============================================================
# 第六部分：可视化
# ============================================================

def _get_sample_dates(panel_df: pd.DataFrame, period: str = 'M') -> list:
    """返回月末（或周末）交易日列表，与 evaluate_factors 采样逻辑一致。"""
    all_dates = pd.DatetimeIndex(sorted(panel_df['date'].unique()))
    return sorted(
        pd.Series(all_dates)
        .groupby(pd.Series(all_dates).dt.to_period(period))
        .last()
    )


def plot_group_backtest(panel_df: pd.DataFrame,
                        factor_cols: list,
                        fwd_return_col: str = 'fwd_return',
                        n_groups: int = 5,
                        save_path: str = 'group_backtest.png') -> None:
    """
    分组回测可视化（月末重平衡）。
    上：G1~G5 累计净值曲线；G1=因子值最低（最发散），G5=最高（最收敛）。
    下：各组平均月收益率柱状图，标注是否单调递增。
    """
    sample_dates = _get_sample_dates(panel_df)
    eval_df = panel_df[panel_df['date'].isin(sample_dates)].copy()

    n_fac = len(factor_cols)
    fig, axes = plt.subplots(2, n_fac, figsize=(4.5 * n_fac, 9))
    if n_fac == 1:
        axes = axes.reshape(2, 1)

    palette = ['#d62728', '#ff7f0e', '#bcbd22', '#17becf', '#2ca02c']
    glabels = [f'G{g+1}' for g in range(n_groups)]
    glabels[0]  += '(发散)'
    glabels[-1] += '(收敛)'

    for fi, col in enumerate(factor_cols):
        grp_rets   = {g: [] for g in range(n_groups)}
        valid_dates = []

        for date in sample_dates:
            sub = eval_df[eval_df['date'] == date][[col, fwd_return_col]].dropna()
            if len(sub) < n_groups * 5:
                continue
            try:
                sub = sub.copy()
                sub['grp'] = pd.qcut(sub[col], n_groups,
                                     labels=range(n_groups), duplicates='drop')
            except Exception:
                continue
            for g in range(n_groups):
                grp_rets[g].append(sub[sub['grp'] == g][fwd_return_col].mean())
            valid_dates.append(date)

        if not valid_dates:
            continue

        # ── 累计净值 ──────────────────────────────────────────────
        ax_nav = axes[0, fi]
        for g in range(n_groups):
            rets = pd.Series(grp_rets[g], index=valid_dates)
            ax_nav.plot(valid_dates, (1 + rets).cumprod().values,
                        label=glabels[g], color=palette[g], linewidth=1.5)
        ax_nav.set_title(f'{col}  分组累计净值', fontsize=10)
        ax_nav.legend(fontsize=7, ncol=2)
        ax_nav.grid(True, alpha=0.3)
        ax_nav.set_ylabel('净值', fontsize=8)

        # ── 平均月收益率 ──────────────────────────────────────────
        ax_bar = axes[1, fi]
        mean_pct = [np.mean(grp_rets[g]) * 100 for g in range(n_groups)]
        is_mono  = all(mean_pct[i] <= mean_pct[i + 1] for i in range(n_groups - 1))
        mono_tag = '✓ 单调' if is_mono else '✗ 非单调'

        bars = ax_bar.bar(glabels, mean_pct, color=palette,
                          edgecolor='white', linewidth=0.5)
        ax_bar.axhline(0, color='black', linewidth=0.8)
        ax_bar.set_title(f'{col}  平均月收益率 (%)  {mono_tag}', fontsize=9)
        ax_bar.grid(True, alpha=0.3, axis='y')
        ax_bar.set_ylabel('月均收益率 (%)', fontsize=8)
        for bar, v in zip(bars, mean_pct):
            ax_bar.text(bar.get_x() + bar.get_width() / 2,
                        v + (0.02 if v >= 0 else -0.05),
                        f'{v:.2f}%', ha='center', va='bottom', fontsize=7)

    fig.suptitle('均线收敛因子  分组回测（月末重平衡，行业市值中性化）',
                 fontsize=12, y=1.01)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  分组回测图已保存至 {save_path}")


def plot_ic_series(ic_df: pd.DataFrame,
                   summary: pd.DataFrame,
                   save_path: str = 'ic_series.png') -> None:
    """绘制各因子月频 RankIC 时序图（逐月柱状 + 均值虚线）。"""
    cols = list(ic_df.columns)
    fig, axes = plt.subplots(len(cols), 1, figsize=(14, 2.8 * len(cols)))
    if len(cols) == 1:
        axes = [axes]

    for i, col in enumerate(cols):
        ax  = axes[i]
        ic  = ic_df[col].dropna()
        mu  = ic.mean()
        icir      = summary.loc[col, 'RankICIR(年化)']
        win_rate  = (ic > 0).mean()

        ax.bar(ic.index, ic.values * 100,
               color=['#2ca02c' if v > 0 else '#d62728' for v in ic.values],
               alpha=0.75, width=20)
        ax.axhline(mu * 100, color='navy', linewidth=1.5, linestyle='--',
                   label=f'均值 {mu*100:.2f}%')
        ax.axhline(0, color='black', linewidth=0.6)
        ax.set_title(
            f'{col}  RankIC均值={mu*100:.2f}%  年化ICIR={icir:.2f}  IC>0胜率={win_rate*100:.0f}%',
            fontsize=10)
        ax.legend(fontsize=8, loc='upper left')
        ax.grid(True, alpha=0.25, axis='y')
        ax.set_ylabel('RankIC (%)', fontsize=8)

    fig.suptitle('均线收敛因子  月频 RankIC 时序（行业市值中性化）', fontsize=12)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  IC时序图已保存至 {save_path}")


# ============================================================
# 第七部分：主流程
# ============================================================

def main():
    print("=" * 60)
    print("均线收敛因子复现框架 v3")
    print("改进：本地 H5 数据 + 全市场覆盖 + ST过滤 + 行业市值中性化")
    print("=" * 60)

    # ── 参数 ──────────────────────────────────────────────────
    START_DATE  = "20120101"   # 与研报一致
    END_DATE    = "20231231"
    N_STOCKS    = None         # None = 全量；改为整数（如 500）则随机抽样
    FWD_DAYS        = 20    # 月频 ~20 交易日
    NEW_STOCK_DAYS  = 250   # 上市不满一年的新股排除（研报标准），仅对样本期内上市股票生效
    # MAX_MA_PERIOD（=120）用于老股预热；新股用 NEW_STOCK_DAYS 兼顾预热与打新溢价

    # ── Step 1-3：从本地 H5 加载数据（替换原 akshare 爬取流程）────
    # [v2 爬取流程已注释，见第一部分]
    # stock_list   = get_stock_list(exclude_st=True)
    # industry_map = get_industry_map(stock_list)
    # raw_df       = get_batch_data(stock_list, START_DATE, END_DATE, N_STOCKS)

    print(f"\n[1-3/6] 从本地 H5 文件加载数据（{START_DATE} ~ {END_DATE}）...")
    raw_df, industry_map = load_local_data(
        start_date=START_DATE,
        end_date=END_DATE,
        n_stocks=N_STOCKS,
        exclude_st=True,
    )

    if raw_df.empty:
        print("数据加载失败，请检查 DATA_DIR 路径及文件完整性")
        return

    # ── Step 4：计算基础因子────────────────────────────────────
    print("\n[4/6] 计算基础因子（PCF / VCF / ACF / TRCF）...")
    t_start    = pd.Timestamp(START_DATE)
    factor_dfs = []
    for sym, group in raw_df.groupby('symbol'):
        group      = group.sort_values('date').copy()
        first_date = group['date'].iloc[0]

        # 老股（样本期前已上市）：只跳过 MA120 预热的 119 行，不额外过滤
        # 新股（样本期内上市）  ：跳过上市后前 NEW_STOCK_DAYS-1 行，同时满足预热 & 剔打新溢价
        skip_rows = (NEW_STOCK_DAYS - 1) if first_date > t_start else (MAX_MA_PERIOD - 1)

        if len(group) <= skip_rows:             # 剩余行为 0，无有效数据
            continue
        group = calc_all_factors(group)
        group = calc_forward_return(group, FWD_DAYS)
        group = group.iloc[skip_rows:]
        factor_dfs.append(group)

    if not factor_dfs:
        print("无满足条件的股票")
        return

    panel_df = pd.concat(factor_dfs, ignore_index=True)

    # ── Step 5：PVCF + 中性化────────────────────────────────────
    print("\n[5/6] 截面合成 PVCF + 行业市值中性化...")

    # PVCF：面板级别截面 z-score 后合成
    panel_df = calc_pvcf(panel_df)

    # ── 截面去量纲（可选）────────────────────────────────────
    # 对 PCF / VCF / ACF / TRCF 做截面 z-score，消除不同个股价格/
    # 成交量/成交额绝对水平不同带来的量纲差异。
    # 还原研报原始处理方式（不去量纲）：注释掉下面这一行即可。
   # panel_df = standardize_factors(panel_df, ['VCF', 'ACF', 'TRCF'])

    # 挂载行业标签 & 估算流通市值
    panel_df['industry'] = panel_df['symbol'].map(industry_map)

    # Winsorize：截面 ±3σ 截断，去除极端异常值（异常成交额/换手率数据）
    all_factor_cols = ['PCF', 'VCF', 'PVCF', 'ACF', 'TRCF']
    panel_df = winsorize_factors(panel_df, all_factor_cols)

    # 挂载行业标签 & 估算流通市值
    panel_df['industry'] = panel_df['symbol'].map(industry_map)
    panel_df = estimate_float_mktcap(panel_df)

    # 行业市值中性化（OLS 残差）
    factor_cols = ['PCF', 'VCF', 'PVCF', 'ACF', 'TRCF']
    panel_df = neutralize_factors(panel_df, factor_cols)

    print(f"  面板最终维度：{panel_df.shape}")

    # ── Step 6：因子评价────────────────────────────────────────
    print("\n[6/6] 计算 RankIC，评价因子效果...")
    ic_series, summary = evaluate_factors(panel_df, factor_cols, freq='monthly')

    print("\n" + "=" * 60)
    print("因子绩效汇总")
    print("=" * 60)
    print(summary.round(4).to_string())

    print("\n研报基准（全市场 + 行业市值中性化，2012-2023）：")
    print("  RankIC:  PCF(2.78%) < VCF(7.69%) < PVCF(9.11%) < ACF(10.30%) ≈ TRCF(10.31%)")
    print("  年化IR:  PCF(0.94)  < PVCF(2.94) < VCF(3.56)   ≈ ACF(3.57)   < TRCF(4.19)")
    # ── 年度 IC 分解（识别因子失效期）───────────────────────────
    print("\n各年度 RankIC 均值（识别因子失效期）：")
    annual_ic = ic_series.groupby(ic_series.index.year).mean()
    print(annual_ic.round(4).to_string())

    print("\n与研报的剩余差距来源：")
    print("  · 行业分类为静态分类，非历史动态分类")
    print("  · 若使用随机抽样（N_STOCKS≠None），样本量仍少于全市场")

    summary.to_csv("factor_results_v3.csv")
    ic_series.to_csv("ic_series_v3.csv")
    print("\n结果已保存至 factor_results_v3.csv 和 ic_series_v3.csv")

    # ── 可视化 ──────────────────────────────────────────────────
    print("\n[可视化] 绘制分组回测和 IC 时序图...")
    plot_group_backtest(panel_df, factor_cols)
    plot_ic_series(ic_series, summary)

    return panel_df, ic_series, summary


if __name__ == "__main__":
    result = main()
