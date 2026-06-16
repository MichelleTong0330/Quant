import backtrader as bt

class 我的策略(bt.Strategy):
    
    def __init__(self):
        # 在这里准备数据和指标
        self.dataclose = self.datas[0].close
    
    def next(self):
        # 每天都会执行一次这里
        # 在这里写买卖逻辑
        if self.dataclose[0] > self.dataclose[-1]:
            self.buy()   # 今天比昨天涨，买！

# 固定套路，每次都这样写
cerebro = bt.Cerebro()
cerebro.addstrategy(我的策略)
cerebro.broker.setcash(100000.0)
cerebro.run()