#!/usr/bin/env python3
"""
哔哩哔哩无损音频提取器

依赖：
    pip install -U yt-dlp
    安装完整版 ffmpeg，并把 ffmpeg 加入 PATH，或填写 FFMPEG_PATH。

重要说明：
    只有来源本身提供 FLAC、ALAC、WAV/PCM 等无损音频流时，输出才是真正无损。
    如果没有原生无损流，脚本会自动下载最高质量的原始音频流（例如 M4A/AAC
    或 WebM/Opus），不会把有损音频转换成 FLAC 后冒充无损。

    请只下载你拥有版权或已获授权的内容，并遵守平台服务条款。本脚本不会绕过
    会员权限、DRM、访问控制或其他平台限制。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


# 如果 PATH 里的 ffmpeg 不完整，可以在这里填写 ffmpeg.exe 的绝对路径。
# 例如：r"D:\Tools\ffmpeg\bin\ffmpeg.exe"

FFMPEG_PATH = r"D:\AAADownload\pAnaconda\install_path\envs\douyin2\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_COOKIES = SCRIPT_DIR / "www.bilibili.com_cookies.txt"

# 这些编码代表无损或未压缩音频；AAC/Opus/MP3 不在其中。
LOSSLESS_CODEC_HINTS = (
    "flac",
    "alac",
    "pcm",
    "wavpack",
    "ape",
    "tta",
    "tak",
)
LOSSLESS_EXTENSIONS = {"flac", "wav", "alac", "ape", "wv", "tta", "tak"}
INVALID_FILENAME_CHARS = r'[\\/:*?"<>|]'


class LosslessUnavailable(RuntimeError):
    """来源没有可下载的原生无损音频流。"""


def find_ytdlp() -> list[str]:
    """优先使用 PATH 中的 yt-dlp，否则尝试 python -m yt_dlp。"""
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    try:
        subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--version"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise EnvironmentError(
            "未检测到 yt-dlp，请先安装：python -m pip install -U yt-dlp"
        ) from exc
    return [sys.executable, "-m", "yt_dlp"]


def find_ffmpeg() -> str:
    """返回可用的 ffmpeg 路径。"""
    if FFMPEG_PATH and Path(FFMPEG_PATH).is_file():
        return FFMPEG_PATH
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise EnvironmentError(
        "未检测到完整版 ffmpeg。请把 ffmpeg 加入 PATH，或在脚本顶部填写 FFMPEG_PATH。"
    )


def find_ffprobe(ffmpeg: str | None = None) -> str | None:
    """查找与 ffmpeg 配套的 ffprobe；没有时返回 None。"""
    if ffmpeg:
        ffmpeg_path = Path(ffmpeg)
        names = ("ffprobe.exe", "ffprobe") if os.name == "nt" else ("ffprobe", "ffprobe.exe")
        for name in names:
            candidate = ffmpeg_path.parent / name
            if candidate.is_file():
                return str(candidate)

    # 未指定单文件版 ffmpeg 时，也允许使用 PATH 里的完整工具套件。
    if not FFMPEG_PATH:
        return shutil.which("ffprobe")
    return None


def safe_filename(title: str) -> str:
    """生成适用于 Windows/macOS/Linux 的安全文件名。"""
    value = re.sub(INVALID_FILENAME_CHARS, "", title)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\.+", ".", value).strip(" .")
    return (value or "output")[:100].rstrip(" .")


def extract_title_core(title: str) -> str:
    """提取《歌名》或「歌名」中的内容，找不到时保留标题并清理常见后缀。"""
    match = re.search(r"《([^》]+)》|「([^」]+)」", title)
    core = next((part for part in match.groups() if part), title) if match else title
    patterns = (
        r"百万豪装录音棚.*",
        r"录音棚.*",
        r"大声听.*",
        r"官方MV.*",
        r"MV版.*",
        r"高清.*",
        r"无损.*",
        r"原版.*",
        r"现场.*",
        r"(?i:live).*",
    )
    for pattern in patterns:
        core = re.sub(pattern, "", core)
    return core.strip() or title.strip()[:100]


def cookies_args(cookies_path: Path | None) -> list[str]:
    """Cookies 文件存在时才传给 yt-dlp，避免默认文件不存在导致失败。"""
    if cookies_path and cookies_path.is_file():
        return ["--cookies", str(cookies_path)]
    return []


def run_ytdlp(
    base: list[str], args: list[str], env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        base + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def load_info(
    ytdlp: list[str], url: str, cookies_path: Path | None, env: dict[str, str]
) -> dict[str, Any]:
    result = run_ytdlp(
        ytdlp,
        [
            "--dump-single-json",
            "--skip-download",
            "--no-playlist",
            "--no-warnings",
            *cookies_args(cookies_path),
            url,
        ],
        env,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        if "This video is only available" in message:
            message += "\n该视频需要登录或会员权限；请使用你有权使用的账号和内容。"
        raise RuntimeError(f"无法解析视频信息：\n{message}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("yt-dlp 返回的信息不是有效 JSON，请升级 yt-dlp 后重试。") from exc


def is_audio_only(fmt: dict[str, Any]) -> bool:
    vcodec = str(fmt.get("vcodec") or "none").lower()
    return vcodec in {"none", ""} and bool(fmt.get("acodec"))


def is_lossless(fmt: dict[str, Any]) -> bool:
    if not is_audio_only(fmt):
        return False
    acodec = str(fmt.get("acodec") or "").lower()
    ext = str(fmt.get("ext") or "").lower()
    return any(hint in acodec for hint in LOSSLESS_CODEC_HINTS) or (
        ext in LOSSLESS_EXTENSIONS and acodec not in {"aac", "mp4a", "opus", "vorbis", "mp3"}
    )


def numeric_value(fmt: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = fmt.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def lossless_score(fmt: dict[str, Any]) -> tuple[float, ...]:
    acodec = str(fmt.get("acodec") or "").lower()
    codec_priority = next(
        (len(LOSSLESS_CODEC_HINTS) - index for index, hint in enumerate(LOSSLESS_CODEC_HINTS) if hint in acodec),
        0,
    )
    # 采样率、声道数和文件大小用于同一编码存在多个音频流时择优。
    return (
        float(codec_priority),
        numeric_value(fmt, "asr"),
        numeric_value(fmt, "audio_channels"),
        numeric_value(fmt, "filesize", "filesize_approx"),
    )


def best_audio_score(fmt: dict[str, Any]) -> tuple[float, ...]:
    """在没有无损流时，选择质量最高的原始音频流。"""
    return (
        numeric_value(fmt, "quality"),
        numeric_value(fmt, "preference"),
        numeric_value(fmt, "source_preference"),
        numeric_value(fmt, "abr", "tbr"),
        numeric_value(fmt, "asr"),
        numeric_value(fmt, "audio_channels"),
        numeric_value(fmt, "filesize", "filesize_approx"),
    )


def format_summary(fmt: dict[str, Any]) -> str:
    codec = fmt.get("acodec") or "未知编码"
    ext = fmt.get("ext") or "?"
    rate = fmt.get("asr") or "?"
    channels = fmt.get("audio_channels") or "?"
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    size_text = f"{size / 1024 / 1024:.1f} MiB" if size else "大小未知"
    return f"id={fmt.get('format_id')}  {ext}/{codec}  {rate} Hz  {channels} 声道  {size_text}"


def choose_unique_stem(output_dir: Path, stem: str, extension: str) -> Path:
    """不覆盖已有文件，返回一个新的目标路径。"""
    target = output_dir / f"{stem}.{extension}"
    counter = 1
    while target.exists():
        target = output_dir / f"{stem}_{counter}.{extension}"
        counter += 1
    return target


def output_file_for_download(output_dir: Path, stem: str, extension: str) -> Path:
    return output_dir / f"{stem}.%(ext)s"


def extract_lossless(
    url: str,
    output_dir: str = ".",
    *,
    use_core_title: bool = True,
    container: str = "flac",
    cookies: str | None = None,
    embed_thumbnail: bool = True,
) -> str:
    """优先下载无损音频；没有无损流时保留最高质量的原始音频。"""
    url = url.strip()
    if not url:
        raise ValueError("链接不能为空")
    if container not in {"flac", "wav", "native"}:
        raise ValueError("container 只能是 flac、wav 或 native")

    ytdlp = find_ytdlp()
    cookies_path = Path(cookies).expanduser() if cookies else DEFAULT_COOKIES
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    print(f"🔍 正在解析：{url}")
    info = load_info(ytdlp, url, cookies_path, env)
    title = str(info.get("title") or "output")
    formats = [fmt for fmt in info.get("formats", []) if isinstance(fmt, dict)]
    lossless_formats = [fmt for fmt in formats if is_lossless(fmt)]
    is_selected_lossless = bool(lossless_formats)
    if is_selected_lossless:
        selected = max(lossless_formats, key=lossless_score)
    else:
        audio_formats = [fmt for fmt in formats if is_audio_only(fmt)]
        if not audio_formats:
            raise RuntimeError("来源没有返回任何可下载的音频流。")
        selected = max(audio_formats, key=best_audio_score)

    print(f"📝 标题：{title}")
    if is_selected_lossless:
        print(f"✅ 检测到原生无损流：{format_summary(selected)}")
    else:
        print("⚠️ 来源没有原生无损音频流。")
        print("ℹ️ AAC/Opus 转成 FLAC 不会增加音质，已自动选择最高质量原始音频：")
        print(f"   {format_summary(selected)}")
    if use_core_title:
        stem = safe_filename(extract_title_core(title))
    else:
        stem = safe_filename(title)

    source_ext = str(selected.get("ext") or "flac").lower()
    # 只有原始流确实无损时才允许无损容器转换；有损兜底必须保留原编码和容器。
    should_convert = is_selected_lossless and container != "native"
    ffmpeg = find_ffmpeg() if should_convert else None
    ffprobe = find_ffprobe(ffmpeg)
    final_ext = container if should_convert else source_ext
    output_dir_path = Path(output_dir).expanduser().resolve()
    output_dir_path.mkdir(parents=True, exist_ok=True)
    final_path = choose_unique_stem(output_dir_path, stem, final_ext)
    template = output_file_for_download(output_dir_path, final_path.stem, final_ext)

    args = [
        url,
        "--format", str(selected["format_id"]),
        "--no-playlist",
        "--output", str(template),
        "--no-warnings",
        "--newline",
        *cookies_args(cookies_path),
    ]
    if should_convert:
        args += [
            "--ffmpeg-location", str(ffmpeg),
            "--extract-audio", "--audio-format", container, "--audio-quality", "0",
        ]
        if ffprobe:
            args += ["--add-metadata"]
            # WAV 容器通常不支持嵌入封面；FLAC 可以。
            if embed_thumbnail and final_ext.lower() != "wav":
                args += ["--embed-thumbnail"]
        elif embed_thumbnail:
            print("ℹ️ 未检测到 ffprobe，已跳过封面和元数据嵌入，不影响音质。")
    elif embed_thumbnail:
        print("ℹ️ 直接保存最高质量原始音轨，已跳过封面和元数据嵌入，不影响音质。")

    quality_label = "无损音频" if is_selected_lossless else "最高质量原始音频"
    print(f"🎵 正在下载{quality_label}（输出：{final_ext.upper()}）……")
    result = run_ytdlp(ytdlp, args, env)
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"下载或封装失败：\n{message}")

    # yt-dlp 的后处理可能改变扩展名；在本次目标前缀下寻找实际生成的文件。
    candidates = sorted(
        output_dir_path.glob(f"{final_path.stem}.*"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    audio_suffixes = {
        ".flac", ".wav", ".m4a", ".mp4", ".webm", ".opus", ".ogg",
        ".mp3", ".aac", ".ape", ".wv", ".tta", ".tak",
    }
    candidates = [item for item in candidates if item.suffix.lower() in audio_suffixes]
    if not candidates:
        raise RuntimeError("下载完成，但未找到输出文件。")
    actual = candidates[0]
    if actual != final_path and final_path.exists():
        final_path = actual
    elif actual != final_path:
        actual.rename(final_path)
    print(f"✅ 完成：{final_path}")
    return str(final_path)


def extract_bgm(url: str, output_dir: str = ".", use_core_title: bool = True) -> str:
    """
    与普通音质版本保持完全一致的公开函数接口。

    Args:
        url:           哔哩哔哩视频链接（支持完整链接和 b23.tv 短链接）
        output_dir:    无损音频输出目录，默认为当前目录
        use_core_title: 是否使用核心标题（True）还是完整标题（False）

    Returns:
        生成的 FLAC 文件绝对路径（str）。

    Raises:
        EnvironmentError: yt-dlp 或 ffmpeg 未安装
        ValueError:       链接或参数有误
        RuntimeError:     下载或转换失败

    注意：函数输入和返回值形状与原来的 extract_bgm 相同，只有输出文件格式
    无损源返回 FLAC 路径；没有无损源时返回最高质量原始音频路径（通常为 M4A
    或 WebM），不会把有损音频伪装成 FLAC。
    """
    return extract_lossless(
        url,
        output_dir,
        use_core_title=use_core_title,
        container="flac",
    )


def extract_bgm_lossless(url: str, output_dir: str = ".", use_core_title: bool = True) -> str:
    """语义更明确的别名；参数和返回值与 ``extract_bgm`` 完全一致。"""
    return extract_bgm(url, output_dir, use_core_title)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="无损音频优先；没有无损流时自动保留最高质量的原始音频。"
    )
    parser.add_argument("url", help="哔哩哔哩视频链接（支持 BV、av、b23.tv）")
    parser.add_argument("output_dir", nargs="?", default=".", help="输出目录，默认当前目录")
    parser.add_argument("--full-title", action="store_true", help="文件名使用完整视频标题")
    parser.add_argument("--container", choices=("flac", "wav", "native"), default="flac", help="输出容器，默认 flac")
    parser.add_argument("--cookies", help="Netscape cookies.txt 路径；默认读取脚本同目录文件")
    parser.add_argument("--no-cover", action="store_true", help="不嵌入封面，避免额外请求缩略图")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        extract_lossless(
            args.url,
            args.output_dir,
            use_core_title=not args.full_title,
            container=args.container,
            cookies=args.cookies,
            embed_thumbnail=not args.no_cover,
        )
    except (EnvironmentError, ValueError, LosslessUnavailable, RuntimeError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
