import backtrader as bt
import akshare as ak
import pandas as pd

# 获取数据
df = ak.stock_zh_a_hist(
    symbol="000001",
    period="daily",
    start_date="20150101",
    end_date="20180101",
    adjust="qfq"
)

# 整理格式
df = df[['日期', '开盘', '最高', '最低', '收盘', '成交量']]
df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
df['date'] = pd.to_datetime(df['date'])
df.set_index('date', inplace=True)

# 策略
class 双均线策略(bt.Strategy):
    params = (
        ('短期', 5),   # 5日均线
        ('长期', 20),  # 20日均线
    )

    def __init__(self):
        self.短期均线 = bt.indicators.SMA(period=self.params.短期)
        self.长期均线 = bt.indicators.SMA(period=self.params.长期)

    def next(self):
        if not self.position:  # 没有持仓
            if self.短期均线[0] > self.长期均线[0]:  # 短线上穿长线
                self.buy()
        else:  # 有持仓
            if self.短期均线[0] < self.长期均线[0]:  # 短线下穿长线
                self.sell()

# 运行
cerebro = bt.Cerebro()
cerebro.addstrategy(双均线策略)
cerebro.adddata(bt.feeds.PandasData(dataname=df))
cerebro.broker.setcash(100000.0)
cerebro.broker.setcommission(commission=0.001)  # 0.1% 手续费

print('起始资金: %.2f' % cerebro.broker.getvalue())
cerebro.run()
print('最终资金: %.2f' % cerebro.broker.getvalue())

cerebro.plot()