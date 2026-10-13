"""音频格式、元数据和 Whisper 输入预处理。"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWN_FFMPEG = Path(
    r"D:\AAADownload\pAnaconda\install_path\envs\douyin2\Lib\site-packages"
    r"\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
)
SUPPORTED_AUDIO_EXTENSIONS = {
    ".mp3", ".m4a", ".flac", ".wav", ".aac", ".opus", ".ogg",
    ".webm", ".mp4", ".ape", ".wv", ".tta", ".tak", ".wma",
}


@dataclass(frozen=True)
class AudioInfo:
    path: Path
    title: str
    artist: str | None
    duration: float


@dataclass(frozen=True)
class PreparedAudio:
    path: Path
    used_vocals: bool
    voice_onset: float | None


def find_ffmpeg() -> str:
    """找到项目可用的 FFmpeg。"""
    found = shutil.which("ffmpeg")
    if found:
        return found
    if KNOWN_FFMPEG.is_file():
        return str(KNOWN_FFMPEG)
    raise EnvironmentError("未找到 FFmpeg，无法读取或预处理音频。")


def resolve_audio_path(audio_path: str | Path) -> Path:
    path = Path(audio_path).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"找不到音频文件：{path}")
    if path.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
        raise ValueError(f"暂不支持该音频格式：{path.suffix or '无扩展名'}")
    return path


def clean_title_guess(filename_stem: str) -> tuple[str, str | None]:
    """从 B 站风格文件名中尽量提取歌名和歌手。"""
    value = re.sub(r"^[\s_]+|[\s_]+$", "", filename_stem)
    value = re.sub(r"^[【\[].*?[】\]]\s*", "", value)
    value = re.sub(
        r"(?i)\b(?:hi[ -]?res|4k|8k|无损|高音质|动态歌词|完整版|官方mv)\b",
        " ",
        value,
    )
    value = re.sub(r"\s+", " ", value).strip(" -—–_")

    book_title = re.search(r"《([^》]{1,60})》", value)
    if book_title:
        return book_title.group(1).strip(), None

    # 常见标题形式：歌手-歌名「歌词片段」。引号前的右半部分是歌名。
    artist_first = re.match(
        r"^([^\s|｜,，/—–-]{1,30})[-—–]([^「『《（(\s|｜,，/]{1,40})[「『《（(]",
        value,
    )
    if artist_first:
        return artist_first.group(2).strip(), artist_first.group(1).strip()

    # 另一类常见标题形式：歌名-歌手 后面跟视频宣传语。
    match = re.match(r"^(.{1,40}?)[-—–]\s*([^\s|｜,，/]{1,30})(?:\s|$)", value)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    value = re.sub(r"_\d+$", "", value).strip()
    return value[:100] or "未知歌曲", None


def _read_optional_metadata(path: Path) -> tuple[str | None, str | None, float | None]:
    """可选使用 mutagen；未安装时安静回退到 FFmpeg 和文件名。"""
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        return None, None, None

    try:
        media = MutagenFile(path, easy=True)
    except Exception:
        return None, None, None
    if media is None:
        return None, None, None

    tags = media.tags or {}
    title_values = tags.get("title") or []
    artist_values = tags.get("artist") or []
    title = str(title_values[0]).strip() if title_values else None
    artist = str(artist_values[0]).strip() if artist_values else None
    duration = float(media.info.length) if getattr(media, "info", None) else None
    return title, artist, duration


def probe_duration(path: Path) -> float:
    """使用 FFmpeg 读取音频时长，不要求系统安装 ffprobe。"""
    result = subprocess.run(
        [find_ffmpeg(), "-hide_banner", "-i", str(path), "-f", "null", "NUL"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    output = f"{result.stdout}\n{result.stderr}"
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", output)
    if not match:
        raise RuntimeError(f"无法读取音频时长：{path}")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def inspect_audio(
    audio_path: str | Path,
    *,
    title: str | None = None,
    artist: str | None = None,
) -> AudioInfo:
    """读取音频路径、歌名、歌手和时长。显式参数优先级最高。"""
    path = resolve_audio_path(audio_path)
    tag_title, tag_artist, tag_duration = _read_optional_metadata(path)
    guessed_title, guessed_artist = clean_title_guess(path.stem)
    final_title = (title or tag_title or guessed_title).strip()
    final_artist = (artist or tag_artist or guessed_artist or "").strip() or None
    duration = tag_duration if tag_duration and tag_duration > 0 else probe_duration(path)
    return AudioInfo(path=path, title=final_title, artist=final_artist, duration=duration)


def _demucs_command() -> list[str] | None:
    command = shutil.which("demucs")
    if command:
        return [command]
    if importlib.util.find_spec("demucs") is not None:
        return [sys.executable, "-m", "demucs"]
    return None


def _try_separate_vocals(source: Path, work_dir: Path) -> Path | None:
    command = _demucs_command()
    if not command:
        return None
    ffmpeg_dir = str(Path(find_ffmpeg()).resolve().parent)
    env = os.environ.copy()
    env["PATH"] = ffmpeg_dir + os.pathsep + env.get("PATH", "")
    demucs_input = work_dir / "demucs_input.wav"
    decode_result = subprocess.run(
        [
            find_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(source), "-vn", "-ac", "2", "-ar", "44100",
            "-c:a", "pcm_s16le", str(demucs_input),
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if decode_result.returncode != 0 or not demucs_input.is_file():
        print(f"[警告] Demucs 输入音频转换失败：{decode_result.stderr.strip()}")
        return None
    result = subprocess.run(
        command + [
            "--two-stems", "vocals", "-o", str(work_dir / "demucs"),
            str(demucs_input),
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "未知错误").strip()
        if len(details) > 1200:
            details = details[-1200:]
        print(f"[警告] 人声分离失败，将直接使用原始音频进行对齐。\n{details}")
        return None
    candidates = list((work_dir / "demucs").rglob("vocals.wav"))
    if not candidates:
        print("[警告] Demucs 已结束但没有生成 vocals.wav，将使用原始音频。")
        return None
    return candidates[0]


def detect_audio_onset(wav_path: Path) -> float | None:
    """从人声 WAV 的能量变化中估算第一段持续人声的开始时间。"""
    import wave

    import numpy as np

    with wave.open(str(wav_path), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        if wav_file.getsampwidth() != 2:
            return None
        frame_size = max(1, int(sample_rate * 0.05))
        values: list[float] = []
        while True:
            frames = wav_file.readframes(frame_size)
            if not frames:
                break
            samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
            values.append(float(np.sqrt(np.mean(samples * samples))))

    if not values or max(values) <= 0:
        return None
    ordered = sorted(values)
    noise_floor = ordered[max(0, int(len(ordered) * 0.15) - 1)]
    high_level = ordered[max(0, int(len(ordered) * 0.90) - 1)]
    threshold = max(noise_floor * 3.0, high_level * 0.12, 40.0)
    required_frames = 5
    for index in range(0, len(values) - required_frames + 1):
        window = values[index:index + required_frames]
        if sum(value >= threshold for value in window) >= required_frames - 1:
            return index * 0.05
    return None


@contextmanager
def prepare_for_alignment(
    audio_path: str | Path,
    *,
    separate_vocals: bool | str = "auto",
) -> Iterator[PreparedAudio]:
    """
    临时生成 16kHz 单声道 WAV，并在可用时先做 Demucs 人声分离。

    ``separate_vocals='auto'`` 表示安装了 Demucs 才启用；缺失时自动回退。
    """
    source = resolve_audio_path(audio_path)
    if separate_vocals not in {True, False, "auto"}:
        raise ValueError("separate_vocals 只能是 True、False 或 'auto'")

    with tempfile.TemporaryDirectory(prefix="lyric_audio_") as temp_name:
        work_dir = Path(temp_name)
        should_try_vocals = separate_vocals is True or (
            separate_vocals == "auto" and _demucs_command() is not None
        )
        vocal_path = _try_separate_vocals(source, work_dir) if should_try_vocals else None
        normalized_path = work_dir / "alignment.wav"
        result = subprocess.run(
            [
                find_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(vocal_path or source), "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", str(normalized_path),
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0 or not normalized_path.is_file():
            raise RuntimeError(f"音频预处理失败：{result.stderr.strip()}")
        voice_onset = detect_audio_onset(normalized_path) if vocal_path is not None else None
        yield PreparedAudio(
            path=normalized_path,
            used_vocals=vocal_path is not None,
            voice_onset=voice_onset,
        )
