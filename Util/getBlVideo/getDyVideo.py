from html import unescape
from pathlib import Path
import re
import sys

import yt_dlp


# Python 文件所在目录
SCRIPT_DIR = Path(__file__).resolve().parent

# 你电脑上的 FFmpeg 路径
FFMPEG_PATH = Path(
    r"D:\AAADownload\pAnaconda\install_path\envs\douyin2"
    r"\Lib\site-packages\imageio_ffmpeg\binaries"
    r"\ffmpeg-win-x86_64-v7.1.exe"
)

# 可选：Cookie 文件放在 Python 文件旁边
COOKIES_PATH = SCRIPT_DIR / "www.douyin.com_cookies.txt"


def extract_url(text: str) -> str:
    """从链接或分享文案中提取并规范化抖音链接。"""
    text = unescape(text.strip())
    match = re.search(r"https?://[^\s]+", text)

    if not match:
        return ""

    url = match.group(0).rstrip(
        "。，、；;！!？?）)]}>\"'"
    )

    # 把主页弹窗链接转换成标准视频链接
    # 例如：
    # https://www.douyin.com/user/self?...&modal_id=123456...
    modal_match = re.search(
        r"[?&]modal_id=(\d+)",
        url,
        flags=re.IGNORECASE,
    )

    if modal_match:
        video_id = modal_match.group(1)
        return f"https://www.douyin.com/video/{video_id}"

    return url


def show_progress(status: dict) -> None:
    """显示下载进度。"""
    current_status = status.get("status")

    if current_status == "downloading":
        percent = status.get("_percent_str", "未知")
        speed = status.get("_speed_str", "未知")
        remaining = status.get("_eta_str", "未知")

        print(
            f"\r下载进度：{percent} | "
            f"速度：{speed} | "
            f"剩余时间：{remaining}",
            end="",
            flush=True,
        )

    elif current_status == "finished":
        print("\n文件下载完成，正在处理 MP4……")


def download_douyin_video(url: str) -> None:
    """下载单个抖音视频。"""
    options = {
        # 优先选择最佳视频和音频
        "format": "bestvideo+bestaudio/best",

        # 视频和音频分开时合并为 MP4
        "merge_output_format": "mp4",

        # 保存到当前 Python 文件所在目录
        "outtmpl": str(
            SCRIPT_DIR / "%(title)s [%(id)s].%(ext)s"
        ),

        # 不下载播放列表
        "noplaylist": True,

        # 处理 Windows 不支持的文件名字符
        "windowsfilenames": True,
        "trim_file_name": 120,

        # 断点续传和失败重试
        "continuedl": True,
        "retries": 10,
        "fragment_retries": 10,

        # 避免重复下载同名文件
        "overwrites": False,

        # 自定义下载进度
        "noprogress": True,
        "progress_hooks": [show_progress],

        # 模拟普通浏览器请求
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0"
            ),
            "Referer": "https://www.douyin.com/",
        },
    }

    # 配置 FFmpeg
    if FFMPEG_PATH.is_file():
        options["ffmpeg_location"] = str(FFMPEG_PATH)
        print(f"已找到 FFmpeg：{FFMPEG_PATH.name}")
    else:
        print(f"警告：找不到 FFmpeg：{FFMPEG_PATH}")
        print("如果需要合并视频和音频，下载可能失败。")

    # 优先读取代码旁边的 Cookie 文件
    if COOKIES_PATH.is_file():
        options["cookiefile"] = str(COOKIES_PATH)
        print(f"已加载 Cookie 文件：{COOKIES_PATH.name}")
    else:
        # 没有 Cookie 文件时，读取 Edge 的抖音登录信息
        options["cookiesfrombrowser"] = ("edge",)
        print("未找到 Cookie 文件，将读取 Edge 的抖音登录信息。")

    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)

        print("\n下载成功！")
        print(f"视频标题：{info.get('title', '未知标题')}")
        print(f"视频作者：{info.get('uploader', '未知作者')}")
        print(f"视频编号：{info.get('id', '未知编号')}")
        print(f"保存目录：{SCRIPT_DIR}")

    except yt_dlp.utils.DownloadError as error:
        print(f"\n下载失败：{error}")
        print("\n请检查以下项目：")
        print("1. Edge 是否已经登录抖音网页版")
        print("2. Edge 是否已经完全退出")
        print("3. yt-dlp 是否为最新版本")
        print("4. 视频是否已删除、私密或限制访问")
        sys.exit(1)

    except PermissionError as error:
        print(f"\n读取 Edge 数据失败：{error}")
        print("请完全退出 Edge，包括右下角托盘和后台进程。")
        sys.exit(1)

    except Exception as error:
        print(f"\n程序发生错误：{error}")
        sys.exit(1)


def main() -> None:
    print("=" * 55)
    print("抖音视频下载工具（Edge 版本）")
    print("=" * 55)
    print(f"视频保存位置：{SCRIPT_DIR}")
    print("可以粘贴纯链接，也可以粘贴完整分享文案。")

    share_text = "https://www.douyin.com/user/self?modal_id=7665715298133400762"

    if not share_text:
        print("没有输入任何内容。")
        return

    video_url = extract_url(share_text)

    if not video_url:
        print("没有从输入内容中找到有效链接。")
        return

    if "douyin.com" not in video_url:
        print(f"识别到的链接不是抖音链接：{video_url}")
        return

    print(f"识别到链接：{video_url}")

    download_douyin_video(video_url)


if __name__ == "__main__":
    main()