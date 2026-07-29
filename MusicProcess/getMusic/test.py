from bili_bgm import extract_bgm
from musicCut import musicCut
# mp3_path = extract_bgm("https://www.bilibili.com/video/BV1wuo6BZErK/?spm_id_from=333.1387.homepage.video_card.click&vd_source=8451966041ec52beb0f6936ba54722e8")
# print(mp3_path)  # 返回 MP3 文件的绝对路径


mp3_paths = ["https://www.bilibili.com/video/BV15RGb6GEr9/?spm_id_from=333.1007.tianma.4-1-11.click&vd_source=e29259537f15576fed15e2ba7fcc511a"]

# 指定目录输出
for i in mp3_paths:
    # extract_bgm(i,output_dir="./biblMusic")
    extract_bgm(i, output_dir="../../input")


# 基本用法
# musicCut("绅士", "1m10s", "1m43s")

# 指定输出目录
# musicCut("绅士", "1m10s", "1m23s", output_dir="./output")