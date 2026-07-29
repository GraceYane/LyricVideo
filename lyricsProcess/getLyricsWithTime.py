import os
import whisper

# 🌐 繁简转换配置 (Whisper 识别中文常输出繁体，此处统一转为简体)
try:
    import opencc

    # t2s = Traditional to Simplified
    CC_CONVERTER = opencc.OpenCC('t2s')
    print("✅ opencc 已加载，输出歌词将自动转为简体")
except ImportError:
    CC_CONVERTER = None
    print("⚠️ 未安装 opencc，将保留原始识别文本(可能含繁体)")
    print("💡 建议终端运行: pip install opencc 以启用自动繁简转换")


def format_lrc_time(seconds: float) -> str:
    """将秒数转换为 LRC 标准时间格式 [mm:ss.xx]"""
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins:02d}:{secs:05.2f}"


def getLyricsWithTime(song_name: str, input_dir: str = "input", output_dir: str = "output/lrc",
                      model_size: str = "base") -> str:
    """
    根据 MP3 音频直接生成带时间戳的简体 LRC 歌词文件
    """
    # 动态获取项目根目录，防止跨文件夹调用时路径失效
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.isabs(input_dir):
        input_dir = os.path.join(project_root, input_dir)
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(project_root, output_dir)

    mp3_path = os.path.join(input_dir, f"{song_name}.mp3")
    lrc_path = os.path.join(output_dir, f"{song_name}.lrc")

    if not os.path.exists(mp3_path):
        return f"❌ 找不到音频文件: {mp3_path}"

    os.makedirs(output_dir, exist_ok=True)

    print(f"🎙️ 正在加载 Whisper ({model_size}) 并解析: {song_name}.mp3")
    try:
        model = whisper.load_model(model_size)
        result = model.transcribe(mp3_path, verbose=False, language="zh")
    except Exception as e:
        return f"❌ Whisper 解析失败: {e}"

    # 4. 转换为 LRC 格式 + 繁简转换
    lrc_lines = []
    for seg in result.get("segments", []):
        text = seg["text"].strip()
        if text:  # 过滤纯音乐/空白片段
            # 🔄 核心优化：繁体转简体
            if CC_CONVERTER:
                text = CC_CONVERTER.convert(text)

            time_tag = format_lrc_time(seg["start"])
            lrc_lines.append(f"[{time_tag}]{text}")

    if not lrc_lines:
        return "️ 未识别到有效人声片段，请检查音频是否含演唱内容"

    # 5. 保存文件
    with open(lrc_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lrc_lines))

    return f"✅ 成功生成简体 LRC: {os.path.abspath(lrc_path)} (共 {len(lrc_lines)} 行)"


# 🔍 快速测试
if __name__ == "__main__":
    # 建议在 test.py 中调用，此处仅作演示
    print(getLyricsWithTime("天龙八部之宿敌"))
