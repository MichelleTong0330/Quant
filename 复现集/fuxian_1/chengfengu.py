from jqdatasdk import auth, get_industry_stocks
import pandas as pd

auth('13510894384', 'Tx722388!')

# 申万一级行业代码
SW_INDUSTRIES = {
    "农林牧渔": "801010", "采掘": "801020", "化工": "801030",
    "钢铁": "801040", "有色金属": "801050", "电子": "801080",
    "家用电器": "801110", "食品饮料": "801120", "纺织服装": "801130",
    "轻工制造": "801140", "医药生物": "801150", "公用事业": "801160",
    "交通运输": "801170", "房地产": "801180", "商业贸易": "801200",
    "休闲服务": "801210", "综合": "801230", "建筑材料": "801710",
    "建筑装饰": "801720", "电气设备": "801730", "国防军工": "801740",
    "计算机": "801750", "传媒": "801760", "通信": "801770",
    "银行": "801780", "非银金融": "801790", "汽车": "801880",
    "机械设备": "801890",
}

# 每月月底日期
dates = pd.date_range("2015-01-31", "2025-04-30", freq="ME")

records = []
for industry, code in SW_INDUSTRIES.items():
    print(f"处理: {industry}")
    for date in dates:
        date_str = date.strftime("%Y-%m-%d")
        try:
            stocks = get_industry_stocks(code, date=date_str)
            for s in stocks:
                records.append({
                    "date": date_str,
                    "stock_code": s.replace(".XSHG", "").replace(".XSHE", ""),
                    "industry": industry
                })
        except Exception as e:
            print(f"  {industry} {date_str} 失败: {e}")

df = pd.DataFrame(records)
df.to_csv("/Users/tongxin/Desktop/复现/sw_components_2015_2025.csv", 
          index=False, encoding="utf-8-sig")
print(f"完成！共 {len(df)} 行")