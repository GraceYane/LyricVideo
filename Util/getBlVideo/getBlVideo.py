from pathlib import Path
import sys

import yt_dlp


# 当前 Python 文件所在目录
SCRIPT_DIR = Path(__file__).resolve().parent

# 你电脑上的 FFmpeg 路径
FFMPEG_PATH = Path(
    r"D:\AAADownload\pAnaconda\install_path\envs\douyin2"
    r"\Lib\site-packages\imageio_ffmpeg\binaries"
    r"\ffmpeg-win-x86_64-v7.1.exe"
)

# 可选：把 B 站 Cookie 文件放在 Python 文件旁边
COOKIES_PATH = SCRIPT_DIR / "www.bilibili.com_cookies.txt"


def show_progress(status: dict) -> None:
    """显示下载进度。"""
    if status.get("status") == "downloading":
        percent = status.get("_percent_str", "未知")
        speed = status.get("_speed_str", "未知")
        remaining = status.get("_eta_str", "未知")

        print(
            f"\r下载进度：{percent} | 速度：{speed} | 剩余：{remaining}",
            end="",
            flush=True,
        )

    elif status.get("status") == "finished":
        print("\n视频流下载完成，正在使用 FFmpeg 合并为 MP4……")


def download_bilibili_video(url: str) -> None:
    """下载单个 B 站视频，并保存到当前 Python 文件所在目录。"""

    if not FFMPEG_PATH.is_file():
        raise FileNotFoundError(f"找不到 FFmpeg：{FFMPEG_PATH}")

    options = {
        # 优先选择 MP4 视频流和 M4A 音频流
        "format": (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]"
            "/best[ext=mp4]"
            "/best"
        ),

        # 使用指定的 FFmpeg
        "ffmpeg_location": str(FFMPEG_PATH),

        # 最终合并为 MP4
        "merge_output_format": "mp4",

        # 保存到当前 Python 文件所在目录
        "outtmpl": str(SCRIPT_DIR / "%(title)s [%(id)s].%(ext)s"),

        # 只下载当前视频，不下载整个合集或播放列表
        "noplaylist": True,

        # 处理 Windows 不支持的文件名字符
        "windowsfilenames": True,

        # 支持断点续传
        "continuedl": True,

        # 下载失败时重试
        "retries": 10,
        "fragment_retries": 10,

        # 显示下载进度
        "progress_hooks": [show_progress],
    }

    # 如果 Python 文件旁边存在 Cookie 文件，就自动使用
    if COOKIES_PATH.is_file():
        options["cookiefile"] = str(COOKIES_PATH)
        print(f"已加载 Cookie：{COOKIES_PATH.name}")
    else:
        print("未找到 Cookie 文件，将以未登录状态下载。")

    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)

        print("\n下载成功！")
        print(f"视频标题：{info.get('title', '未知标题')}")
        print(f"保存目录：{SCRIPT_DIR}")

    except yt_dlp.utils.DownloadError as error:
        print(f"\n下载失败：{error}")
        print("请检查视频链接、网络、Cookie 和 FFmpeg 路径。")
        sys.exit(1)


def main() -> None:
    print("B站视频下载工具")
    print(f"视频将保存到：{SCRIPT_DIR}")

    video_url = "https://www.bilibili.com/bangumi/play/ep426748?theme=movie&spm_id_from=333.337.0.0"

    if not video_url:
        print("没有输入视频链接。")
        return

    if "bilibili.com" not in video_url and "b23.tv" not in video_url:
        print("提示：输入的链接看起来可能不是 B 站链接。")

    download_bilibili_video(video_url)


if __name__ == "__main__":
    main()