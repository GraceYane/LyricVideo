# 处理 1分10秒 到 1分23秒 的部分
musicCut("绅士", "1m10s", "1m23s")

# 处理到结尾
musicCut("绅士", "1m10s")

# 自定义人声降低强度（0-1，越大降低越多）
musicCut("绅士", "1m10s", "1m23s", vocal_reduction_strength=0.9)