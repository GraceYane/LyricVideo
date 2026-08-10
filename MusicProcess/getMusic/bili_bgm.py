#!/usr/bin/env python3
"""
哔哩哔哩 BGM 提取器
依赖: pip install yt-dlp  +  安装完整版 ffmpeg
"""

import os
import sys
import subprocess
import shutil
import re

# ── 如果 PATH 里的 ffmpeg 是残缺版（conda 环境常见问题），在这里直接写死完整路径 ──
# 例如: r"D:\AADownloads\Pffmpeg\ffmpeg\bin\ffmpeg.exe"
# 留空则自动从 PATH 查找
# FFMPEG_PATH = r"D:\AADownloads\Pffmpeg\ffmpeg\bin\ffmpeg.exe"
FFMPEG_PATH = r"D:\AAADownload\pAnaconda\install_path\envs\douyin2\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
COOKIES_PATH = os.path.join(os.path.dirname(__file__), "www.bilibili.com_cookies.txt")
def extract_title_core(title: str) -> str:
    """
    从完整标题中提取核心内容作为文件名

    处理规则:
    1. 提取《》或「」中的内容
    2. 移除常见的后缀描述（百万豪装录音棚、大声听等）
    3. 清理特殊字符

    Args:
        title: 完整标题，如 'XueZhiQian《狐狸》百万豪装录音棚大声听'

    Returns:
        核心标题，如 '狐狸'

    Examples:
        >>> extract_title_core('XueZhiQian《狐狸》百万豪装录音棚大声听')
        '狐狸'
        >>> extract_title_core('绅士')
        '绅士'
        >>> extract_title_core('【4K】周杰伦《七里香》官方MV')
        '七里香'
    """
    # 常见需要移除的后缀模式
    remove_patterns = [
        r'百万豪装录音棚.*',  # 移除"百万豪装录音棚"及其后续内容
        r'录音棚.*',  # 移除"录音棚"及其后续内容
        r'大声听.*',  # 移除"大声听"及其后续内容
        r'官方MV.*',  # 移除"官方MV"及其后续内容
        r'MV版.*',  # 移除"MV版"及其后续内容
        r'高清.*',  # 移除"高清"及其后续内容
        r'无损.*',  # 移除"无损"及其后续内容
        r'原版.*',  # 移除"原版"及其后续内容
        r'现场.*',  # 移除"现场"及其后续内容
        r'live.*',  # 移除"live"及其后续内容
        r'Live.*',  # 移除"Live"及其后续内容
    ]

    # 1. 优先提取《》中的内容
    book_title_pattern = r'《([^》]+)》'
    match = re.search(book_title_pattern, title)
    if match:
        core_title = match.group(1)
    else:
        # 2. 尝试提取「」中的内容
        bracket_pattern = r'「([^」]+)」'
        match = re.search(bracket_pattern, title)
        if match:
            core_title = match.group(1)
        else:
            # 3. 如果没有书名号，使用原始标题
            core_title = title

    # 清理提取后的标题
    # 移除常见的艺术家前缀（如果标题太长的话）
    core_title = re.sub(r'^[\w\s]+《', '', core_title)  # 移除"XueZhiQian《"这类前缀（如果没被书名号捕获到）

    # 移除后缀描述
    for pattern in remove_patterns:
        core_title = re.sub(pattern, '', core_title)

    # 移除多余的空白和特殊字符
    core_title = core_title.strip()

    # 如果处理后为空，使用原始标题的合理部分
    if not core_title or len(core_title) < 1:
        # 使用原始标题的前30个字符
        core_title = title[:30].strip()

    return core_title


def safe_filename(title: str) -> str:
    """
    生成安全的文件名

    Args:
        title: 文件标题

    Returns:
        安全的文件名（不含扩展名）
    """
    # 移除不适合作为文件名的字符
    invalid_chars = r'[\\/:*?"<>|]'
    safe = re.sub(invalid_chars, '', title)

    # 移除多余的空格和点
    safe = re.sub(r'\s+', ' ', safe).strip()
    safe = re.sub(r'\.+', '.', safe).strip('.')

    # 如果处理后为空，使用默认名称
    if not safe:
        safe = "output"

    # 限制文件名长度（Windows 路径长度限制）
    if len(safe) > 100:
        safe = safe[:100].strip()

    return safe


def extract_bgm(url: str, output_dir: str = ".", use_core_title: bool = True) -> str:
    """
    从哔哩哔哩链接提取音频，输出 MP3 文件。

    Args:
        url:           哔哩哔哩视频链接（支持完整链接和 b23.tv 短链接）
        output_dir:    MP3 输出目录，默认为当前目录
        use_core_title: 是否使用核心标题（True）还是完整标题（False）

    Returns:
        生成的 MP3 文件的绝对路径

    Raises:
        EnvironmentError: yt-dlp 或 ffmpeg 未安装
        ValueError:       链接格式有误
        RuntimeError:     下载或转换失败
    """
    # ── 1. 检查 yt-dlp ────────────────────────────────────────────────────────
    if shutil.which("yt-dlp"):
        ytdlp_cmd = ["yt-dlp"]
    else:
        try:
            subprocess.run(
                [sys.executable, "-m", "yt_dlp", "--version"],
                capture_output=True, check=True
            )
            ytdlp_cmd = [sys.executable, "-m", "yt_dlp"]
        except Exception:
            raise EnvironmentError(
                "未检测到 yt-dlp，请先安装：pip install yt-dlp"
            )

    # ── 2. 确定 ffmpeg 路径 ───────────────────────────────────────────────────
    ffmpeg_exe = FFMPEG_PATH if FFMPEG_PATH and os.path.isfile(FFMPEG_PATH) else shutil.which("ffmpeg")
    if not ffmpeg_exe:
        raise EnvironmentError(
            "未检测到 ffmpeg。\n"
            "请在脚本顶部设置 FFMPEG_PATH，例如：\n"
            r'  FFMPEG_PATH = r"D:\AADownloads\Pffmpeg\ffmpeg\bin\ffmpeg.exe"'
        )

    # ── 3. Windows GBK 修复 ───────────────────────────────────────────────────
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    # ── 4. 校验链接 ────────────────────────────────────────────────────────────
    url = url.strip()
    if not url:
        raise ValueError("链接不能为空")

    # ── 5. 获取视频标题 ────────────────────────────────────────────────────────
    print(f"🔍 正在解析链接：{url}")
    title_result = subprocess.run(
        ytdlp_cmd + ["--get-title", "--no-warnings","--cookies", COOKIES_PATH ,  url],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if title_result.returncode != 0 or not title_result.stdout:
        raise RuntimeError(
            f"无法解析视频信息，请检查链接是否有效。\n"
            f"{(title_result.stderr or '').strip()}"
        )
    title = title_result.stdout.strip().splitlines()[0]

    # ── 6. 生成文件名 ────────────────────────────────────────────────────────
    if use_core_title:
        # 使用优化后的核心标题作为文件名
        core_title = extract_title_core(title)
        print(f"📝 原始标题: {title}")
        print(f"📝 提取核心: {core_title}")
        final_title = safe_filename(core_title)
    else:
        # 使用完整标题作为文件名（保留原逻辑）
        final_title = safe_filename(title)

    output_path = os.path.abspath(os.path.join(output_dir, f"{final_title}.mp3"))

    # ── 7. 下载并转换为 MP3 ───────────────────────────────────────────────────
    os.makedirs(output_dir, exist_ok=True)

    # 使用临时模板（yt-dlp 使用原标题下载，之后重命名）
    temp_template = os.path.join(output_dir, "%(title)s.%(ext)s")

    print(f"🎵 正在提取音频：《{title}》")
    result = subprocess.run(
        ytdlp_cmd + [
            url,
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--output", temp_template,
            "--no-playlist",
            "--embed-thumbnail",
            "--add-metadata",
            "--no-warnings",
            "--ffmpeg-location", ffmpeg_exe,
            "--cookies", COOKIES_PATH
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "Encoder not found" in stderr or "audio conversion failed" in stderr:
            raise RuntimeError(
                f"音频转换失败，ffmpeg 路径可能有误：{ffmpeg_exe}\n"
                "请检查 FFMPEG_PATH 是否正确。"
            )
        elif "This video is only available" in stderr:
            raise RuntimeError("该视频为大会员专属，请登录后重试。")
        else:
            raise RuntimeError(f"音频提取失败：\n{stderr}")

    # ── 8. 重命名文件（如果需要） ─────────────────────────────────────────────
    # yt-dlp 下载的文件名基于原始标题，我们需要重命名为核心标题
    temp_path = os.path.abspath(os.path.join(output_dir, f"{safe_filename(title)}.mp3"))

    if os.path.exists(temp_path) and temp_path != output_path:
        # 如果目标文件已存在，先备份或覆盖
        if os.path.exists(output_path):
            # 如果目标文件已存在，生成新文件名
            counter = 1
            base, ext = os.path.splitext(output_path)
            while os.path.exists(f"{base}_{counter}{ext}"):
                counter += 1
            output_path = f"{base}_{counter}{ext}"

        os.rename(temp_path, output_path)
        print(f"📝 文件已重命名为: {os.path.basename(output_path)}")

    elif not os.path.exists(output_path):
        # 如果预期文件都不存在，尝试查找其他 mp3 文件
        mp3_files = [f for f in os.listdir(output_dir) if f.endswith(".mp3")]
        if mp3_files:
            # 使用最新的文件
            latest_file = max(mp3_files, key=lambda f: os.path.getmtime(os.path.join(output_dir, f)))
            temp_path = os.path.join(output_dir, latest_file)

            if temp_path != output_path:
                if os.path.exists(output_path):
                    counter = 1
                    base, ext = os.path.splitext(output_path)
                    while os.path.exists(f"{base}_{counter}{ext}"):
                        counter += 1
                    output_path = f"{base}_{counter}{ext}"
                os.rename(temp_path, output_path)
                print(f"📝 文件已重命名为: {os.path.basename(output_path)}")
            else:
                output_path = temp_path
        else:
            raise RuntimeError("下载完成，但未找到 MP3 文件，请检查输出目录。")

    print(f"✅ 完成！文件已保存至：{output_path}")
    return output_path


# ── 命令行入口 ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python bili_bgm.py <哔哩哔哩链接> [输出目录] [--full-title]")
        print("示例: python bili_bgm.py https://www.bilibili.com/video/BV1xx411c7mD ./music")
        print("      python bili_bgm.py <链接> ./music --full-title  # 使用完整标题作为文件名")
        sys.exit(1)

    link = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "."

    # 检查是否使用完整标题
    use_core = "--full-title" not in sys.argv

    try:
        path = extract_bgm(link, out, use_core)
    except (EnvironmentError, ValueError, RuntimeError) as e:
        print(f"❌ 错误：{e}")
        sys.exit(1)