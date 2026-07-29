import os
import re
from difflib import SequenceMatcher

# 繁简转换（Whisper 常输出繁体，TXT 是简体，统一后匹配率大幅提升）
try:
    from opencc import OpenCC
    cc = OpenCC('t2s')
    def to_simplified(text): return cc.convert(text)
except ImportError:
    def to_simplified(text): return text

def clean_text(text: str) -> str:
    """清洗文本：转简体 + 移除标点/空格，仅保留核心汉字/英文/数字"""
    return re.sub(r'[^\w\u4e00-\u9fff]', '', to_simplified(text))

def parse_lrc(lrc_path: str) -> tuple:
    """解析 LRC，返回 (时间列表[浮点秒], 文本列表)"""
    times, texts = [], []
    pattern = re.compile(r'\[(\d+):(\d+)(?:\.(\d+))?\](.*)')
    with open(lrc_path, 'r', encoding='utf-8') as f:
        for line in f:
            m = pattern.match(line.strip())
            if m:
                sec = int(m.group(1)) * 60 + float(m.group(2))
                if m.group(3):
                    sec += float(f"0.{m.group(3).ljust(2, '0')}")
                txt = m.group(4).strip()
                if txt:
                    times.append(sec)
                    texts.append(txt)
    return times, texts

def format_time(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{seconds % 60:05.2f}"

# ====================== 优化：添加 enable_correct 开关 ======================
def correct_lrc_with_txt(song_name: str,
                         enable_correct: bool = True,  # 新增开关：True=校准，False=直接输出原LRC
                         txt_dir: str = "output/txt",
                         lrc_dir: str = "output/lrc",
                         out_dir: str = "output/lrcCorrection",
                         threshold: float = 0.25) -> str:

    txt_path = os.path.join(txt_dir, f"{song_name}.txt")
    lrc_path = os.path.join(lrc_dir, f"{song_name}.lrc")
    out_path = os.path.join(out_dir, f"{song_name}.lrc")

    if not os.path.exists(lrc_path):
        return f"❌ 找不到 LRC: {lrc_path}"

    # ============== 开关关闭：直接原封不动复制 LRC 文件 ==============
    if not enable_correct:
        os.makedirs(out_dir, exist_ok=True)
        with open(lrc_path, 'r', encoding='utf-8') as f_in:
            original_lrc = f_in.read()
        with open(out_path, 'w', encoding='utf-8') as f_out:
            f_out.write(original_lrc)
        return f"✅ 开关关闭，直接输出原LRC: {os.path.abspath(out_path)}"

    # ============== 开关开启：执行原来的校准逻辑 ==============
    if not os.path.exists(txt_path):
        return f"❌ 找不到 TXT: {txt_path}"

    lrc_times, lrc_texts = parse_lrc(lrc_path)
    with open(txt_path, 'r', encoding='utf-8') as f:
        txt_lines = [line.strip() for line in f if line.strip()]

    if not lrc_texts:
        return "❌ LRC 文件中无有效歌词行"

    # 📦 暂存中间结果：{'time': 秒数, 'txt_idx': 匹配到的TXT索引 或 None}
    results = []
    used_txt_indices = set()  # 防止同一句 TXT 歌词被重复匹配

    print(f"🔄 LRC驱动校准: {len(lrc_times)} 行时间轴 -> 匹配 TXT 歌词...")

    # Pass 1: 全局贪婪匹配
    for idx, (time_sec, noisy_text) in enumerate(zip(lrc_times, lrc_texts), 1):
        clean_noisy = clean_text(noisy_text)
        best_score, best_idx = -1.0, -1

        for t_idx, txt_line in enumerate(txt_lines):
            if t_idx in used_txt_indices:
                continue
            score = SequenceMatcher(None, clean_noisy, clean_text(txt_line)).ratio()
            if score > best_score:
                best_score, best_idx = score, t_idx

        if best_score >= threshold and best_idx != -1:
            results.append({'time': time_sec, 'txt_idx': best_idx})
            used_txt_indices.add(best_idx)
        else:
            results.append({'time': time_sec, 'txt_idx': None})

    # 🔹 Pass 2: 上下文顺次填充
    last_valid_idx = -1
    for i in range(len(results)):
        if results[i]['txt_idx'] is not None:
            last_valid_idx = results[i]['txt_idx']
        else:
            if last_valid_idx != -1:
                fill_idx = last_valid_idx + 1
            else:
                fill_idx = 0
            fill_idx = min(fill_idx, len(txt_lines) - 1)
            results[i]['txt_idx'] = fill_idx
            last_valid_idx = fill_idx

    # Pass 3: 组装最终 LRC
    result_lines = []
    for r in results:
        idx = r['txt_idx']
        if idx is None:
            idx = 0
        result_lines.append(f"[{format_time(r['time'])}]{txt_lines[idx]}")

    # 保存
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(result_lines))

    return f"✅ 校准完成: {os.path.abspath(out_path)} (严格保持 {len(result_lines)} 行)"


# === 测试代码 ===
if __name__ == "__main__":
    # 使用示例：
    # True  = 开启校准
    # False = 直接输出原LRC
    print(correct_lrc_with_txt("天龙八部之宿敌", enable_correct=True))