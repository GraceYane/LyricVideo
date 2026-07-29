#!/usr/bin/env python3
"""
哔哩哔哩 BGM 提取器 (无损 Hi-Res 高音质版)
依赖: pip install yt-dlp  +  安装完整版 ffmpeg
"""

import os
import sys
import subprocess
import shutil
import re
import tempfile

# ── 如果 PATH 里的 ffmpeg 是残缺版，在这里写死完整路径 ──
FFMPEG_PATH = r"D:\AADownloads\Pffmpeg\ffmpeg\bin\ffmpeg.exe"

# ── 大会员 Cookie 配置（提取 Hi-Res/无损音质必填） ──
# 方式 A：直接指定你电脑上的浏览器名称，让 yt-dlp 自动读取登录状态。可选: "chrome", "edge", "firefox", "safari"
# 缺点：如果浏览器关了或者有权限限制可能会失败
COOKIE_BROWSER = ""

# 方式 B：如果你有导出的 cookies.txt 文件，请在下方写死路径（优先级高于浏览器）。留空则不使用文件。
COOKIE_FILE_PATH = "www.bilibili.com_cookies.txt"


def extract_title_core(title: str) -> str:
    """ 从完整标题中提取核心内容作为文件名 """
    remove_patterns = [
        r'百万豪装录音棚.*', r'录音棚.*', r'大声听.*', r'官方MV.*',
        r'MV版.*', r'高清.*', r'无损.*', r'原版.*', r'现场.*', r'live.*', r'Live.*'
    ]

    book_title_pattern = r'《([^》]+)》'
    match = re.search(book_title_pattern, title)
    if match:
        core_title = match.group(1)
    else:
        bracket_pattern = r'「([^」]+)」'
        match = re.search(bracket_pattern, title)
        if match:
            core_title = match.group(1)
        else:
            core_title = title

    core_title = re.sub(r'^[\w\s]+《', '', core_title)
    for pattern in remove_patterns:
        core_title = re.sub(pattern, '', core_title)

    core_title = core_title.strip()
    return core_title if core_title else title[:30].strip()


def safe_filename(title: str) -> str:
    """ 生成安全的文件名 """
    invalid_chars = r'[\\/:*?"<>|]'
    safe = re.sub(invalid_chars, '', title)
    safe = re.sub(r'\s+', ' ', safe).strip()
    safe = re.sub(r'\.+', '.', safe).strip('.')
    return safe if safe else "output"


def extract_bgmHires(url: str, output_dir: str = ".", use_core_title: bool = True, audio_format: str = "flac") -> str:
    """
    从哔哩哔哩链接提取音质最高的音频。

    Args:
        url:           视频链接
        output_dir:    音频输出目录
        use_core_title: 是否使用核心标题
        audio_format:  目标格式，可选 "flac" (无损), "wav" (无损未压缩), "mp3" (高码率压缩)
    """
    # ── 1. 检查 yt-dlp ────────────────────────────────────────────────────────
    if shutil.which("yt-dlp"):
        ytdlp_cmd = ["yt-dlp"]
    else:
        try:
            subprocess.run([sys.executable, "-m", "yt_dlp", "--version"], capture_output=True, check=True)
            ytdlp_cmd = [sys.executable, "-m", "yt_dlp"]
        except Exception:
            raise EnvironmentError("未检测到 yt-dlp，请先安装：pip install yt-dlp")

    # ── 2. 确定 ffmpeg 路径 ───────────────────────────────────────────────────
    ffmpeg_exe = FFMPEG_PATH if FFMPEG_PATH and os.path.isfile(FFMPEG_PATH) else shutil.which("ffmpeg")
    if not ffmpeg_exe:
        raise EnvironmentError("未检测到 ffmpeg，请在脚本顶部设置 FFMPEG_PATH。")

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    url = url.strip()
    if not url:
        raise ValueError("链接不能为空")

    # ── 3. 构造 Cookie 参数（无损音质的核心保障） ─────────────────────────────
    cookie_args = []
    if COOKIE_FILE_PATH and os.path.exists(COOKIE_FILE_PATH):
        cookie_args = ["--cookies", COOKIE_FILE_PATH]
        print(f"🍪 已加载 Cookie 文件: {COOKIE_FILE_PATH}")
    elif COOKIE_BROWSER:
        cookie_args = ["--cookies-from-browser", COOKIE_BROWSER]
        print(f"🌐 尝试从浏览器【{COOKIE_BROWSER}】中读取大会员登录状态...")

    # ── 4. 获取视频标题 ────────────────────────────────────────────────────────
    print(f"🔍 正在解析链接：{url}")
    title_result = subprocess.run(
        ytdlp_cmd + cookie_args + ["--get-title", "--no-warnings", url],
        capture_output=True, encoding="utf-8", errors="replace", env=env,
    )
    if title_result.returncode != 0 or not title_result.stdout:
        raise RuntimeError(f"无法解析视频信息，请检查链接或 Cookie 是否有效。\n{(title_result.stderr or '').strip()}")
    title = title_result.stdout.strip().splitlines()[0]

    # ── 5. 生成文件名 ────────────────────────────────────────────────────────
    if use_core_title:
        core_title = extract_title_core(title)
        final_title = safe_filename(core_title)
    else:
        final_title = safe_filename(title)

    output_path = os.path.abspath(os.path.join(output_dir, f"{final_title}.{audio_format}"))
    os.makedirs(output_dir, exist_ok=True)

    # ── 6. 下载并提取最高画质音频 ─────────────────────────────────────────────
    # 定义临时输出模板
    temp_template = os.path.join(output_dir, "%(title)s.%(ext)s")

    print(f"🚀 正在提取【{audio_format.upper()}】极佳音质音频：《{title}》...")

    # 核心音质参数组合：
    # -f "ba" 或者 "bestaudio": 让 B 站服务器下发它能提供的码率最高的原生音频流（如 Hi-Res / FLAC / 320k m4a）
    # --audio-quality 0: 保持 FFmpeg 转换时的最高品质等级
    download_args = ytdlp_cmd + cookie_args + [
        url,
        "-f", "bestaudio/best",  # 强制索取最优音轨
        "--extract-audio",
        "--audio-format", audio_format,  # 指定目标格式
        "--audio-quality", "0",  # 0 代表最高品质
        "--output", temp_template,
        "--no-playlist",
        "--embed-thumbnail",
        "--add-metadata",
        "--no-warnings",
        "--ffmpeg-location", ffmpeg_exe,
    ]

    result = subprocess.run(download_args, capture_output=True, encoding="utf-8", errors="replace", env=env)

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "Encoder not found" in stderr or "audio conversion failed" in stderr:
            raise RuntimeError(f"音频转换失败，ffmpeg 路径可能有误：{ffmpeg_exe}")
        else:
            raise RuntimeError(f"音频提取失败：\n{stderr}")

    # ── 7. 重命名与多文件清理逻辑 ─────────────────────────────────────────────
    temp_path = os.path.abspath(os.path.join(output_dir, f"{safe_filename(title)}.{audio_format}"))

    if os.path.exists(temp_path) and temp_path != output_path:
        if os.path.exists(output_path):
            counter = 1
            base, ext = os.path.splitext(output_path)
            while os.path.exists(f"{base}_{counter}{ext}"):
                counter += 1
            output_path = f"{base}_{counter}{ext}"
        os.rename(temp_path, output_path)
    elif not os.path.exists(output_path):
        # 兜底：如果没找到精确匹配，模糊寻找目录下最新生成的对应格式文件
        target_files = [f for f in os.listdir(output_dir) if f.endswith(f".{audio_format}")]
        if target_files:
            latest_file = max(target_files, key=lambda f: os.path.getmtime(os.path.join(output_dir, f)))
            temp_path = os.path.join(output_dir, latest_file)
            if temp_path != output_path:
                if os.path.exists(output_path):
                    counter = 1
                    base, ext = os.path.splitext(output_path)
                    while os.path.exists(f"{base}_{counter}{ext}"):
                        counter += 1
                    output_path = f"{base}_{counter}{ext}"
                os.rename(temp_path, output_path)
        else:
            raise RuntimeError(f"下载完成，但未在输出目录找到 .{audio_format} 文件。")

    print(f"✅ 完美无损提取成功！文件已保存至：{output_path}")
    return output_path


# ── 命令行入口 ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python bili_bgm.py <哔哩哔哩链接> [输出目录] [--format flac/mp3/wav]")
        print("示例: python bili_bgm.py https://www.bilibili.com/video/BV1xx411c7mD ./music --format flac")
        sys.exit(1)

    link = sys.argv[1]
    out = "."
    fmt = "flac"  # 默认改用无损 FLAC 格式

    # 解析参数
    if len(sys.argv) > 2:
        for i in range(2, len(sys.argv)):
            if sys.argv[i] == "--format" and i + 1 < len(sys.argv):
                fmt = sys.argv[i + 1].lower()
            elif not sys.argv[i].startswith("--") and sys.argv[i - 1] != "--format":
                out = sys.argv[i]

    try:
        path = extract_bgm(link, out, use_core_title=True, audio_format=fmt)
    except Exception as e:
        print(f"❌ 错误：{e}")
        sys.exit(1)