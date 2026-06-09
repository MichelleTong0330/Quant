const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  LevelFormat
} = require('docx');
const fs = require('fs');

const BLUE = "2C5F8A";
const LIGHT_BLUE = "EAF1F8";
const WHITE = "FFFFFF";
const DARK = "1A1A2E";
const CODE_BG = "F5F5F5";

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 };

function heading1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 400, after: 200 },
    children: [new TextRun({ text, bold: true, size: 32, color: BLUE, font: "Arial" })]
  });
}

function heading2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 300, after: 150 },
    children: [new TextRun({ text, bold: true, size: 26, color: DARK, font: "Arial" })]
  });
}

function heading3(text) {
  return new Paragraph({
    spacing: { before: 200, after: 100 },
    children: [new TextRun({ text, bold: true, size: 22, color: BLUE, font: "Arial" })]
  });
}

function body(text) {
  return new Paragraph({
    spacing: { before: 80, after: 80 },
    children: [new TextRun({ text, size: 20, font: "Arial" })]
  });
}

function code(text) {
  return new Paragraph({
    spacing: { before: 60, after: 60 },
    indent: { left: 360 },
    children: [new TextRun({ text, size: 18, font: "Courier New", color: "333333" })]
  });
}

function divider() {
  return new Paragraph({
    spacing: { before: 200, after: 200 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "DDDDDD", space: 1 } },
    children: [new TextRun("")]
  });
}

function makeTable(headers, rows) {
  const totalWidth = 9360;
  const colCount = headers.length;
  const colWidth = Math.floor(totalWidth / colCount);
  const colWidths = headers.map(() => colWidth);

  const headerRow = new TableRow({
    children: headers.map(h => new TableCell({
      borders,
      width: { size: colWidth, type: WidthType.DXA },
      margins: cellMargins,
      shading: { fill: BLUE, type: ShadingType.CLEAR },
      children: [new Paragraph({
        children: [new TextRun({ text: h, bold: true, color: WHITE, size: 18, font: "Arial" })]
      })]
    }))
  });

  const dataRows = rows.map((row, ri) => new TableRow({
    children: row.map(cell => new TableCell({
      borders,
      width: { size: colWidth, type: WidthType.DXA },
      margins: cellMargins,
      shading: { fill: ri % 2 === 0 ? LIGHT_BLUE : WHITE, type: ShadingType.CLEAR },
      children: [new Paragraph({
        children: [new TextRun({ text: cell, size: 18, font: "Arial" })]
      })]
    }))
  }));

  return new Table({
    width: { size: totalWidth, type: WidthType.DXA },
    columnWidths: colWidths,
    rows: [headerRow, ...dataRows]
  });
}

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 20 } } },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: BLUE },
        paragraph: { spacing: { before: 400, after: 200 }, outlineLevel: 0 }
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: DARK },
        paragraph: { spacing: { before: 300, after: 150 }, outlineLevel: 1 }
      }
    ]
  },
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } }
        }]
      }
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
      }
    },
    children: [

      // ── 封面 ──────────────────────────────────────────────────
      new Paragraph({
        spacing: { before: 1200, after: 200 },
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "Python 量化金融学习笔记", bold: true, size: 52, color: BLUE, font: "Arial" })]
      }),
      new Paragraph({
        spacing: { before: 100, after: 100 },
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "基于《A股行业动量的精细结构》复现代码", size: 24, color: "666666", font: "Arial" })]
      }),
      new Paragraph({
        spacing: { before: 100, after: 800 },
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "记录重要知识点 · 对应代码 · 拓展应用", size: 20, color: "999999", font: "Arial" })]
      }),
      divider(),

      // ══════════════════════════════════════════════════════════
      // 知识点 1：函数参数逻辑
      // ══════════════════════════════════════════════════════════
      heading1("知识点 1：函数参数是「调用时」才传入的"),

      heading2("核心概念"),
      body("函数定义只是写好了菜谱，参数是做菜时才传进来的食材。定义函数时写的参数名只是一个「占位符」，真正的数据在调用函数时才被传入。"),

      heading2("对应代码"),
      body("函数定义（只是菜谱，index_data 是占位符）："),
      code("def calc_factors(index_data: dict) -> dict:"),
      code("    # 这里的 index_data 是形参，还没有真实数据"),
      code("    for name, df in index_data.items():"),
      code("        ..."),
      new Paragraph({ spacing: { before: 100 }, children: [] }),
      body("主流程里建好数据，再传进去（这里才有真实数据）："),
      code("index_data = {}"),
      code("for code, name in SW_INDUSTRIES.items():"),
      code("    df = get_index_daily(code, name)"),
      code("    index_data[name] = df"),
      new Paragraph({ spacing: { before: 60 }, children: [] }),
      code("factor_data = calc_factors(index_data)  # 这里才把真实数据传进去"),

      heading2("General 写法"),
      code("def 函数名(参数名):"),
      code("    # 函数体，用参数名操作数据"),
      code("    return 结果"),
      new Paragraph({ spacing: { before: 60 }, children: [] }),
      code("数据 = {...}          # 先准备好数据"),
      code("结果 = 函数名(数据)   # 调用时才传入"),

      heading2("拓展应用"),
      body("同一个函数可以用不同的数据调用多次："),
      code("factor_data_A = calc_factors(index_data_A)  # 用A股数据"),
      code("factor_data_H = calc_factors(index_data_H)  # 用港股数据"),
      body("函数本身不变，只是传入不同的食材，做出不同的结果。"),

      divider(),

      // ══════════════════════════════════════════════════════════
      // 知识点 2：代码三大核心工具
      // ══════════════════════════════════════════════════════════
      heading1("知识点 2：代码的三大核心工具"),

      heading2("整体关系"),
      body("三个工具各司其职，共同完成「原始日数据 → 月度因子 → 回测打分」的流程："),
      code("原始日数据"),
      code("   ↓ rolling()           → 构造因子（过去20日累计信号）"),
      code("   ↓ groupby().last()    → 压缩成月度（取每月最后一个交易日）"),
      code("   ↓ df.loc[]            → 每月取出来打分排名"),

      // 工具1
      heading3("工具 1：DataFrame 索引与切片（df.loc[]）"),
      body("DataFrame 是 pandas 里的表格结构，.loc[] 是定位工具，用来取出你想要的行和列。"),
      makeTable(
        ["操作", "代码", "含义"],
        [
          ["取某一列", 'df["close"]', "取收盘价这一列"],
          ["取某一行", "df.loc[last_month]", "取上个月那一行"],
          ["按条件筛选", 'df[df["intra"].abs() > 0.2]', "取涨跌幅绝对值超20%的行"],
          ["条件修改", 'df.loc[条件, "列名"] = 新值', "满足条件的格子改成新值"],
        ]
      ),
      new Paragraph({ spacing: { before: 120 }, children: [] }),
      body("General 写法："),
      code("df.loc[行条件, 列名] = 新值   # 定位并修改"),
      code("df.loc[某月份]               # 取某一行"),
      code('df["列名"]                   # 取某一列'),

      // 工具2
      heading3("工具 2：groupby().last() — 日数据压缩成月数据"),
      body("把每天的数据按月分组，取每组（每月）最后一个值，即每月最后一个交易日的数据。"),
      code("# 把日收盘价压缩成月收盘价"),
      code("mc = df['close'].groupby(df['close'].index.to_period('M')).last()"),
      code("# 2005-01-04, 2005-01-05 ... → 2005-01  (取最后一天)"),
      code("# 2005-02-01, 2005-02-02 ... → 2005-02  (取最后一天)"),
      new Paragraph({ spacing: { before: 60 }, children: [] }),
      body("General 写法："),
      code("月度数据 = 日数据.groupby(日数据.index.to_period('M')).last()"),
      body("拓展：把 .last() 换成 .sum() 可以算每月成交量总和，换成 .mean() 可以算每月均价。"),

      // 工具3
      heading3("工具 3：rolling() — 滚动窗口"),
      body("想象一个固定大小的「框」在数据上从上往下滑动，每次计算框内所有数据的统计量。"),
      code("# 窗口大小20天，至少15个有效值才计算"),
      code("df['M0'] = df['intra'].rolling(20, min_periods=15).sum()"),
      new Paragraph({ spacing: { before: 60 }, children: [] }),
      body("示意图（窗口=3）："),
      code("第1天  0.01   →  NaN          (不够3天)"),
      code("第2天  0.02   →  NaN          (不够3天)"),
      code("第3天  0.03   →  0.06         (第1+2+3天之和)"),
      code("第4天  0.01   →  0.06         (第2+3+4天之和)"),
      code("第5天  0.02   →  0.06         (第3+4+5天之和)"),
      new Paragraph({ spacing: { before: 60 }, children: [] }),
      body("General 写法："),
      code("结果 = 数据列.rolling(窗口大小, min_periods=最少有效值).聚合函数()"),
      body("拓展：.rolling().mean() 是移动平均，.rolling().std() 是滚动标准差，.rolling().max() 是滚动最大值。"),

      divider(),

      // ══════════════════════════════════════════════════════════
      // 知识点 3：常用函数速查
      // ══════════════════════════════════════════════════════════
      heading1("知识点 3：课程中出现的常用函数速查"),

      makeTable(
        ["函数", "含义", "例子"],
        [
          [".shift(1)", "整列往下移一格，取前一天的值", "df['close'].shift(1) → 昨天收盘价"],
          [".abs()", "取绝对值", "df['intra'].abs() > 0.2"],
          [".dropna()", "删除含空值的行", "dropna(how='all') 全空才删"],
          [".pct_change(n)", "计算n期涨跌幅", "df['close'].pct_change(20)"],
          [".clip(lower, upper)", "截断极端值到边界", "s.clip(lower=0.025分位, upper=0.975分位)"],
          [".rank()", "截面排名", "m0.rank(method='first')"],
          [".cumprod()", "累乘，算净值曲线", "(1 + 月收益).cumprod()"],
          [".intersection()", "取两个索引的交集", "m0.index.intersection(m1.index)"],
          ["pd.to_numeric()", "强制转成数字，转不了变NaN", "pd.to_numeric(df['close'], errors='coerce')"],
          ["pd.to_datetime()", "把字符串转成真正的日期", "pd.to_datetime(df['date'])"],
          [".fillna(0)", "把NaN替换成0", "group_ret_df.fillna(0)"],
          [".quantile(n)", "取第n分位数值", "s.quantile(0.025) → 最低2.5%的值"],
        ]
      ),

      divider(),

      // ══════════════════════════════════════════════════════════
      // 知识点 4：重要语法
      // ══════════════════════════════════════════════════════════
      heading1("知识点 4：重要语法"),

      heading2("f-string（字符串插值）"),
      body("在字符串里直接嵌入变量值，用 f'' 开头，变量放在 {} 里。"),
      code('g = 3'),
      code('print(f"G{g}")      # 输出: G3'),
      code('v = 0.12345'),
      code('print(f"{v:.4f}")   # 输出: 0.1235  （保留4位小数）'),
      code('print(f"{v:.2%}")   # 输出: 12.35%  （转成百分比）'),

      heading2("try...except（错误处理）"),
      body("尝试执行某段代码，如果出错就执行 except 里的内容，防止程序崩溃。"),
      code("try:"),
      code("    df = ak.index_hist_sw(symbol=code)  # 尝试下载"),
      code("except Exception as e:"),
      code("    print(f'下载失败: {e}')             # 出错就打印警告"),
      code("    return pd.DataFrame()               # 返回空表，继续运行"),

      heading2("if __name__ == '__main__'"),
      body("Python 固定写法。直接运行这个文件时才执行 main()，被别的文件 import 时不执行。"),
      code("if __name__ == '__main__':"),
      code("    main()"),

      heading2("字典推导式"),
      code("{g: [] for g in range(1, 6)}"),
      body("等价于："),
      code("{1: [], 2: [], 3: [], 4: [], 5: []}"),
      body("快速建一个有规律的字典。"),

      divider(),

      // ══════════════════════════════════════════════════════════
      // 知识点 5：同比 vs 环比
      // ══════════════════════════════════════════════════════════
      heading1("知识点 5：同比 vs 环比——PCA 和回归各用哪个？"),

      heading2("核心区别"),
      makeTable(
        ["", "同比（Year-on-Year）", "环比（Month-on-Month）"],
        [
          ["计算方式", "今月 vs 去年同月\npct_change(12) 或 diff(12)", "今月 vs 上月\npct_change(1) 或 diff(1)"],
          ["特点", "过滤短期噪音，反映长期趋势", "捕捉当月的实际变化"],
          ["用途", "PCA：找各资产的共同结构（方向）", "回归自变量：解释这个月因子动了多少"],
          ["类比", "「今年销售额比去年高了多少」", "「这个月销售额比上个月高了多少」"],
        ]
      ),
      new Paragraph({ spacing: { before: 120 }, children: [] }),

      heading2("为什么 PCA 用同比"),
      body("PCA 的目的是找出哪些资产在「长期趋势」上同步运动，提取共同结构（主成分方向）。用同比可以过滤掉单月短期波动的干扰，让共同结构更清晰稳定。"),

      heading2("为什么回归自变量用环比"),
      body("回归要解释的是「这个月行业收益率为什么涨了或跌了」。因子和行业收益都是月度变化，必须用环比（MoM）口径才能对齐，建立有意义的因果关系。"),

      heading2("一句话总结"),
      body("同比找方向（PCA 提取权重），环比算大小（回归解释当月变化）。"),

      heading2("对应代码"),
      body("PCA 用同比："),
      code("yoy = monthly_close.pct_change(12)   # 同比"),
      code("yoy = np.log(1 + yoy)                # 转成对数口径"),
      new Paragraph({ spacing: { before: 60 }, children: [] }),
      body("回归自变量用环比："),
      code("mom = monthly_close.pct_change(1)    # 环比"),
      code("mom = np.log(1 + mom)                # 转成对数口径"),

      divider(),

      // ══════════════════════════════════════════════════════════
      // 知识点 6：残差动量 Debug 记录
      // ══════════════════════════════════════════════════════════
      heading1("知识点 6：残差动量复现 Debug 记录"),

      heading2("概述"),
      body("以下是复现过程中遇到的所有 bug，按出现顺序排列。每个 bug 包含：错误现象、根本原因、诊断方法、修改方法。"),

      heading3("Bug 1：dropna() 把所有数据删光了"),
      body("错误信息：ValueError: Found array with 0 sample(s) (shape=(0, 31))"),
      body("根本原因：stock_yoy、bond_yoy、comm_yoy 三张表时间范围不完全一致，pd.concat 拼合后很多行都有 NaN。默认的 dropna() 会删掉任何含 NaN 的行，结果把所有行都删光了。"),
      body("诊断方法：打印 window_data.shape，发现是 (0, 31)。"),
      body("修改方法："),
      code("# 错误写法"),
      code("window_data = data.iloc[i-window:i].dropna()"),
      code("# 正确写法：只删全空行，其余 NaN 填0"),
      code("window_data = data.iloc[i-window:i].dropna(how='all').fillna(0)"),

      heading3("Bug 2：PCA 和 stock_mom 维度不匹配"),
      body("错误信息：ValueError: matmul: Input operand 1 has a mismatch, size 31 is different from 44"),
      body("根本原因：PCA 是对股+债+商共44列数据做的，pca.components_ 形状是 (3×44)，但点积右边传的是 stock_mom，只有31列，维度不对齐。"),
      body("诊断方法：打印 pca.components_.shape 和 stock_mom.shape，发现列数不一致。"),
      body("修改方法："),
      code("all_mom = pd.concat([stock_mom, bond_mom, comm_mom], axis=1)"),
      code("factor_values = pca.components_ @ all_mom.iloc[i-1].values"),

      heading3("Bug 3：bond_mom 多了一列 date"),
      body("错误信息：ValueError: matmul: size 45 is different from 44"),
      body("根本原因：build_bond_mom 里缺少 set_index('date')，date 列留着作为普通列，导致 all_mom 拼出来有45列。"),
      body("诊断方法：打印 bond_mom.columns.tolist()，发现列名里有 'date'。"),
      body("修改方法："),
      code("def build_bond_mom(bond_data):"),
      code("    bond_data = bond_data.set_index('date')  # 加这行"),
      code("    ..."),

      heading3("Bug 4：OLS 遇到 NaN 报错"),
      body("错误信息：ValueError: Input X contains NaN. LinearRegression does not accept missing values."),
      body("根本原因：all_mom 里有 NaN（不同资产数据起始时间不同），导致 factor_df 里也有 NaN。"),
      body("修改方法："),
      code("X = factor_df.iloc[i-window:i].fillna(0).values"),
      code("y = stock_mom.iloc[i-window:i].fillna(0).values"),

      heading3("Bug 5：用 [] 索引行导致 KeyError"),
      body("错误信息：KeyError: Timestamp('2017-01-31 00:00:00')"),
      body("根本原因：high_vol_mom 是行的 index（日期），但 adjusted[high_vol_mom] 用的是 [] 索引，pandas 的 [] 默认按列索引。"),
      body("修改方法："),
      code("# 错误写法：[] 是按列索引"),
      code("adjusted[high_vol_mom] *= -1"),
      code("# 正确写法：.loc[] 才是按行索引"),
      code("adjusted.loc[high_vol_mom] *= -1"),

      heading3("Bug 6：策略净值持续跑输基准（时间未对齐）"),
      body("错误现象：没有报错，但蓝线（策略）一直低于橙线（基准），结果方向完全错误。"),
      body("根本原因：factor_df 的 index 从2008年开始，stock_mom 的 index 从1999年开始，第i行 X 和第i行 Y 对应的时间完全不同，回归建立在错误的对应关系上。"),
      body("诊断方法："),
      code("print(factor_df.index[:3])   # 2008-03-31"),
      code("print(stock_mom.index[:3])   # 1999-12-31  ← 不一致"),
      body("修改方法："),
      code("stock_mom = stock_mom.loc[factor_df.index]  # 强制对齐"),

      heading3("Bug 7：胜率计算 shape 不匹配"),
      body("错误信息：ValueError: operands could not be broadcast together with shapes (80,) (93,)"),
      body("根本原因：portfolio_returns 和 benchmark 用 .loc[start:end] 截取后，两者长度不一致（80 vs 93）。"),
      body("修改方法："),
      code("common = port_trimmed.index.intersection(bench_trimmed.index)"),
      code("port_trimmed = port_trimmed.loc[common]"),
      code("bench_trimmed = bench_trimmed.loc[common]"),

      heading2("通用 Debug 思路总结"),
      makeTable(
        ["问题类型", "第一步诊断", "常见修复"],
        [
          ["维度错误 shape mismatch", "打印两边的 .shape", "检查数据拼合是否完整，是否有多余列"],
          ["NaN 报错", "打印 .isna().sum()", "传入模型前加 .fillna(0) 或 .dropna(how='all')"],
          ["KeyError Timestamp", "判断 key 是行index还是列名", "行用 .loc[]，列用 []"],
          ["结果方向错误（无报错）", "打印 .index[:3] 对比", "用 .loc[另一张表的index] 强制对齐"],
          ["两个 Series 长度不一致", "打印 len() 确认差异", "用 .intersection() 取公共index后对齐"],
        ]
      ),
      new Paragraph({ spacing: { before: 120 }, children: [] }),

      divider(),

      // ══════════════════════════════════════════════════════════
      // 知识点 7：回测绩效指标计算
      // ══════════════════════════════════════════════════════════
      heading1("知识点 7：回测绩效指标计算"),

      heading2("年化收益率"),
      body("把整个回测期的总收益折算成「如果每年都这样涨，年化是多少」。"),
      code("n_months = len(port_trimmed)"),
      code("annual_return = (nav_trimmed.iloc[-1] / nav_trimmed.iloc[0]) ** (12 / n_months) - 1"),
      body("公式含义：期末净值 / 期初净值 = 总倍数，开 (12/月数) 次方 = 折算成年化。"),

      heading2("年化超额收益"),
      body("策略年化收益率 - 基准年化收益率，衡量策略相对基准多赚了多少。"),
      code("excess_return = annual_return - bench_annual"),

      heading2("最大回撤"),
      body("净值从历史最高点跌到最低点的最大幅度，衡量策略的最坏情况。"),
      code("rolling_max = nav_trimmed.cummax()"),
      code("drawdown = (nav_trimmed - rolling_max) / rolling_max"),
      code("max_drawdown = drawdown.min()"),
      body("注意：cummax() 是「滚动最大值」，每一行取到当前为止的最大值，不是全局最大值。这样才能正确计算每个时间点相对历史高点的回撤。"),

      heading2("月度胜率"),
      body("策略收益 > 基准收益的月份占总月份的比例。"),
      code("win = (port_trimmed.values > bench_trimmed.values).sum()"),
      code("win_rate = win / len(port_trimmed)"),

      heading2("注意：时间对齐"),
      body("计算前必须确保策略和基准的 index 一致，否则比较会报错："),
      code("common = port_trimmed.index.intersection(bench_trimmed.index)"),
      code("port_trimmed = port_trimmed.loc[common]"),
      code("bench_trimmed = bench_trimmed.loc[common]"),

      heading2("本次复现结果 vs 研报对比"),
      makeTable(
        ["指标", "本次结果", "研报结果", "差距原因"],
        [
          ["年化超额收益", "4.68%", "12.80%", "本次用3个主成分，研报用6个自变量"],
          ["最大回撤", "-35.12%", "未披露", "—"],
          ["月度胜率", "47.50%", "未披露", "—"],
        ]
      ),
      new Paragraph({ spacing: { before: 120 }, children: [] }),

      divider(),

      // ── 尾部说明 ──
      new Paragraph({
        spacing: { before: 400 },
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "笔记持续更新中 · 遇到不懂的随时问", size: 18, color: "999999", font: "Arial" })]
      }),
    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("/mnt/user-data/outputs/Python量化金融学习笔记.docx", buffer);
  console.log("Done!");
});
