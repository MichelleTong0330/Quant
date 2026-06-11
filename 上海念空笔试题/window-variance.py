import math

def rolling_var(data: list, w: int) -> list:
    n = len(data)
    if n == 0:
        return []
    
    result = [float('nan')] * n
    curr_sum = 0.0
    curr_sq_sum = 0.0
    count = 0
    
    for i in range(n):
        # 1. 移入新元素
        val_in = data[i]
        if not math.isnan(val_in):
            curr_sum += val_in
            curr_sq_sum += val_in ** 2
            count += 1
            
        # 2. 移出旧元素（当索引达到 window 长度时）
        if i >= w:
            val_out = data[i - w] #移除list里面第一个数据（可以理解为滑动）
            if not math.isnan(val_out):
                curr_sum -= val_out
                curr_sq_sum -= val_out ** 2
                count -= 1
        
        # 3. 计算当前窗口方差
        # 前 window - 1 个输出为 NaN
        if i >= w - 1: #未到达窗口尽头不会执行
            if count > 1: #否则分母N-1=0，无法计算方差
                # 使用公式: (sum_x2 - (sum_x)^2 / N) / (N - 1)
                # 增加 max(0, ...) 防止浮点数精度误差导致微小的负数
                variance = (curr_sq_sum - (curr_sum ** 2) / count) / (count - 1)
                result[i] = max(0.0, variance)
            else:
                # 如果有效数字不足2个，无法计算样本方差
                result[i] = float('nan')
                
    return result