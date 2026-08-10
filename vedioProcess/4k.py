#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import gc
import math
import os
import re
import shutil
import tempfile
from bisect import bisect_right
from pathlib import Path
from typing import Dict, Optional, Tuple, List

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoClip, AudioFileClip


# ============================================================
# 1. 路径配置
# ============================================================

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)


def get_abs_path(*rel_path) -> str:
    """
    根据项目根目录拼接绝对路径。
    """
    return os.path.join(PROJECT_ROOT, *rel_path)


# ============================================================
# 2. 全局配置
# ============================================================

SCALE = 2

VIDEO_W = 3840
VIDEO_H = 2160
FPS = 55

DEFAULT_BG_NAME = "jianlaihong"
DEFAULT_COVER_NAME = "jianlaihong"

CUSTOM_FONT_TITLE = get_abs_path(
    "resources",
    "fonts",
    "msyh.ttc"
)

CUSTOM_FONT_ARTIST = get_abs_path(
    "resources",
    "fonts",
    "shoujin.TTF"
)

CUSTOM_FONT_LYRIC = get_abs_path(
    "resources",
    "fonts",
    "msyh.ttc"
)

DEBUG_DURATION = 0.04
DEBUG_MODE = False

FS_CURRENT = 52 * SCALE
FS_NORMAL = 42 * SCALE
FS_TITLE = 74 * SCALE
FS_ARTIST = 52 * SCALE

COVER_CX = 320 * SCALE
COVER_CY = 600 * SCALE
COVER_R = 200 * SCALE
COVER_BORDER = 18 * SCALE

RING_DOTS = 80
RING_DOT_R = 4.5 * SCALE
RING_GAP = 14 * SCALE
COVER_ROT_DEG_PER_SEC = 3.0

RING_PULSE_FREQ = 0.5
RING_PULSE_MIN_ALPHA = 80
RING_PULSE_MAX_ALPHA = 255

BG_SCALE_FACTOR = 1.05
BG_SWAY_FREQ_X = 0.25
BG_SWAY_FREQ_Y = 0.18
BG_SWAY_AMP_X = 10.0 * SCALE
BG_SWAY_AMP_Y = 8.0 * SCALE

TITLE_X = 80 * SCALE
TITLE_Y = 90 * SCALE

ARTIST_X = 140 * SCALE
ARTIST_SPACING = 30 * SCALE

LYRIC_X = 860 * SCALE
LYRIC_CURRENT_Y = 320 * SCALE
LINE_H = 92 * SCALE

LINES_ABOVE = 2
LINES_BELOW = 6

C_CURRENT = (255, 255, 255)
C_ABOVE = (130, 130, 150)
C_BELOW = (130, 130, 150)
C_TITLE = (255, 255, 255)
C_ARTIST = (185, 185, 205)

BG_OVERLAY = 85
SCROLL_DURATION = 0.32


# ============================================================
# 3. 支持的音频格式
# ============================================================

SUPPORTED_AUDIO_EXTENSIONS = (
    ".mp3",
    ".m4a",
    ".flac",
    ".wav",
    ".aac",
    ".ogg",
    ".oga",
    ".opus",
    ".wma",
    ".ape",
    ".aiff",
    ".aif",
    ".m4b",
    ".mka",
    ".webm",
)

SUPPORTED_AUDIO_EXTENSIONS_CASEFOLD = {
    ext.casefold()
    for ext in SUPPORTED_AUDIO_EXTENSIONS
}


# ============================================================
# 4. 音频文件查找
# ============================================================

def _find_audio_file(
        audio_dir: str,
        song_name: str
) -> Path:
    """
    根据歌曲名称自动查找音频文件。

    支持以下调用方式：

        generate_lyric_video("歌曲名称")

    或者：

        generate_lyric_video("歌曲名称.m4a")

    同名文件同时存在时，优先级为：

        mp3 > m4a > flac > wav > 其他格式
    """

    audio_dir_path = Path(audio_dir)

    if not audio_dir_path.is_dir():
        raise FileNotFoundError(
            f"找不到音频目录：{audio_dir_path}"
        )

    requested_path = Path(str(song_name))
    requested_extension = requested_path.suffix.casefold()

    if requested_path.suffix:
        song_stem = requested_path.stem
    else:
        song_stem = requested_path.name

    candidates: List[Path] = []

    for path in audio_dir_path.iterdir():
        if not path.is_file():
            continue

        extension = path.suffix.casefold()

        if extension not in SUPPORTED_AUDIO_EXTENSIONS_CASEFOLD:
            continue

        if path.stem.casefold() == song_stem.casefold():
            candidates.append(path)

    if not candidates:
        supported = "、".join(
            SUPPORTED_AUDIO_EXTENSIONS
        )

        raise FileNotFoundError(
            f"找不到歌曲音频：{song_stem}\n"
            f"支持格式：{supported}"
        )

    # 如果调用时明确指定了扩展名，例如“歌曲.m4a”
    if requested_extension in SUPPORTED_AUDIO_EXTENSIONS_CASEFOLD:
        exact_candidates = [
            path
            for path in candidates
            if path.suffix.casefold() == requested_extension
        ]

        if exact_candidates:
            candidates = exact_candidates

    extension_priority = {
        ext: index
        for index, ext in enumerate(
            SUPPORTED_AUDIO_EXTENSIONS
        )
    }

    candidates.sort(
        key=lambda path: (
            extension_priority.get(
                path.suffix.casefold(),
                999
            ),
            path.name.casefold()
        )
    )

    return candidates[0]


def _prepare_audio_for_ffmpeg(
        audio_path: Path
) -> Tuple[str, Optional[str]]:
    """
    处理中文音频路径。

    某些 Windows + FFmpeg 环境对中文路径支持不稳定，
    如果路径中存在非 ASCII 字符，就复制到临时目录再读取。
    """

    audio_path = Path(audio_path)
    audio_text = str(audio_path)

    # 路径只包含英文、数字和 ASCII 符号时，直接使用
    if all(ord(char) < 128 for char in audio_text):
        return audio_text, None

    file_handle, temporary_path = tempfile.mkstemp(
        prefix="lyricvideo_audio_",
        suffix=audio_path.suffix
    )

    os.close(file_handle)

    try:
        shutil.copy2(
            str(audio_path),
            temporary_path
        )
    except Exception:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)
        raise

    return temporary_path, temporary_path


# ============================================================
# 5. 通用工具函数
# ============================================================

def _close_quietly(resource) -> None:
    """
    安全释放资源，避免 close() 再次抛出异常。
    """

    if resource is None:
        return

    try:
        resource.close()
    except Exception:
        pass


def _load_font(
        size: int,
        bold: bool = False,
        custom_path: Optional[str] = None
):
    """
    加载字体。
    """

    size = int(size)

    if custom_path and os.path.exists(custom_path):
        try:
            return ImageFont.truetype(
                custom_path,
                size
            )
        except Exception as error:
            print(
                f"警告：无法加载自定义字体 "
                f"{custom_path}：{error}"
            )

    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/wqy/"
        "wqy-zenhei.ttc",
    ]

    for font_path in candidates:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(
                    font_path,
                    size
                )
            except Exception:
                pass

    return ImageFont.load_default()


def _find_image(
        folder: str,
        name_hint: Optional[str] = None
) -> Optional[str]:
    """
    根据图片名称查找背景图或封面图。

    支持 jpg、jpeg、png、webp、bmp，
    同时忽略文件名和扩展名大小写。
    """

    image_extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".bmp",
    }

    folder_path = Path(folder)

    if not folder_path.is_dir():
        return None

    if not name_hint:
        return None

    hint_path = Path(str(name_hint))
    hint_stem = hint_path.stem.casefold()
    hint_name = hint_path.name.casefold()

    for path in folder_path.iterdir():
        if not path.is_file():
            continue

        if path.suffix.casefold() not in image_extensions:
            continue

        if (
            path.stem.casefold() == hint_stem
            or path.name.casefold() == hint_name
        ):
            return str(path)

    return None


# ============================================================
# 6. LRC 歌词解析
# ============================================================

def _parse_lrc(
        lrc_path: str
) -> Tuple[Dict[str, str], List[Tuple[float, str]]]:
    """
    解析 LRC 文件。

    支持：

        [00:12.34]歌词内容
        [00:12.345]歌词内容
        [00:12]歌词内容
        [00:12.34][00:25.10]重复歌词

    返回：

        meta:
            歌曲标题、歌手等元数据

        lines:
            [(时间秒数, 歌词文本), ...]
    """

    metadata: Dict[str, str] = {}
    lyric_lines: List[Tuple[float, str]] = []

    time_pattern = re.compile(
        r"\[(\d+):(\d{1,2})"
        r"(?:[.:](\d{1,3}))?\]"
    )

    metadata_pattern = re.compile(
        r"^\[([A-Za-z]+):(.*?)\]\s*$"
    )

    with open(
        lrc_path,
        "r",
        encoding="utf-8-sig",
        errors="replace"
    ) as file:
        for raw_line in file:
            line = raw_line.strip()

            if not line:
                continue

            time_matches = time_pattern.findall(line)

            if time_matches:
                text = time_pattern.sub(
                    "",
                    line
                ).strip()

                if not text:
                    continue

                for minutes, seconds, fraction in time_matches:
                    fraction = fraction or "0"

                    if len(fraction) == 1:
                        milliseconds = int(fraction) * 100
                    elif len(fraction) == 2:
                        milliseconds = int(fraction) * 10
                    else:
                        milliseconds = int(fraction[:3])

                    timestamp = (
                        int(minutes) * 60
                        + int(seconds)
                        + milliseconds / 1000.0
                    )

                    lyric_lines.append(
                        (timestamp, text)
                    )

                continue

            metadata_match = metadata_pattern.match(line)

            if metadata_match:
                key = metadata_match.group(1).lower()
                value = metadata_match.group(2).strip()
                metadata[key] = value

    lyric_lines.sort(key=lambda item: item[0])

    return metadata, lyric_lines


# ============================================================
# 7. 画面绘制函数
# ============================================================

def _ease_out_cubic(t: float) -> float:
    """
    缓动函数。
    """

    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def _draw_text(
        draw,
        x: int,
        y: int,
        text: str,
        font,
        color,
        alpha: int = 255
) -> None:
    """
    绘制带阴影的文字。
    """

    red, green, blue = color[:3]
    shadow_offset = 2 * SCALE

    draw.text(
        (
            x + shadow_offset,
            y + shadow_offset
        ),
        text,
        font=font,
        fill=(
            0,
            0,
            0,
            min(120, alpha // 2)
        )
    )

    draw.text(
        (x, y),
        text,
        font=font,
        fill=(
            red,
            green,
            blue,
            alpha
        )
    )


def _paste_cover(
        frame: Image.Image,
        cover_base: Image.Image,
        t: float
) -> None:
    """
    绘制旋转唱片封面。
    """

    center_x = COVER_CX
    center_y = COVER_CY
    radius = COVER_R
    border_width = COVER_BORDER

    border_diameter = (
        radius + border_width
    ) * 2

    current_degree = (
        t * COVER_ROT_DEG_PER_SEC
    ) % 360

    rotated = cover_base.rotate(
        -current_degree,
        resample=Image.BICUBIC,
        expand=False
    )

    diameter = radius * 2

    mask = Image.new(
        "L",
        (diameter, diameter),
        0
    )

    ImageDraw.Draw(mask).ellipse(
        (0, 0, diameter, diameter),
        fill=255
    )

    cover_circle = Image.new(
        "RGBA",
        (diameter, diameter),
        (0, 0, 0, 0)
    )

    cover_circle.paste(
        rotated,
        mask=mask
    )

    border = Image.new(
        "RGBA",
        (
            border_diameter,
            border_diameter
        ),
        (0, 0, 0, 0)
    )

    border_mask = Image.new(
        "L",
        (
            border_diameter,
            border_diameter
        ),
        0
    )

    ImageDraw.Draw(border_mask).ellipse(
        (
            0,
            0,
            border_diameter,
            border_diameter
        ),
        fill=255
    )

    border.paste(
        Image.new(
            "RGBA",
            (
                border_diameter,
                border_diameter
            ),
            (0, 0, 0, 255)
        ),
        mask=border_mask
    )

    frame.paste(
        border,
        (
            center_x - radius - border_width,
            center_y - radius - border_width
        ),
        border
    )

    frame.paste(
        cover_circle,
        (
            center_x - radius,
            center_y - radius
        ),
        cover_circle
    )

    _close_quietly(mask)
    _close_quietly(cover_circle)
    _close_quietly(border)
    _close_quietly(border_mask)
    _close_quietly(rotated)


def _draw_ring_dots(
        layer: Image.Image,
        t: float
) -> None:
    """
    绘制封面周围的呼吸点。
    """

    draw = ImageDraw.Draw(layer)

    pulse = math.sin(
        t * RING_PULSE_FREQ * 2 * math.pi
    )

    alpha = int(
        (
            RING_PULSE_MAX_ALPHA
            - RING_PULSE_MIN_ALPHA
        ) / 2
        * (pulse + 1)
        + RING_PULSE_MIN_ALPHA
    )

    distance = (
        COVER_R
        + COVER_BORDER
        + RING_GAP
    )

    for index in range(RING_DOTS):
        angle = (
            2 * math.pi * index / RING_DOTS
        )

        x = COVER_CX + distance * math.cos(angle)
        y = COVER_CY + distance * math.sin(angle)

        draw.ellipse(
            (
                x - RING_DOT_R,
                y - RING_DOT_R,
                x + RING_DOT_R,
                y + RING_DOT_R
            ),
            fill=(
                255,
                255,
                255,
                alpha
            )
        )


def _render_frame(
        t,
        bg_scaled: Image.Image,
        cover_base: Image.Image,
        lyrics: List[Tuple[float, str]],
        lyric_times: List[float],
        song_title: str,
        artist: str,
        fonts: Dict[str, object]
):
    """
    根据时间渲染单帧画面。
    """

    sway_x = int(
        round(
            math.sin(
                t * BG_SWAY_FREQ_X * 2 * math.pi
            ) * BG_SWAY_AMP_X
        )
    )

    sway_y = int(
        round(
            math.cos(
                t * BG_SWAY_FREQ_Y * 2 * math.pi
            ) * BG_SWAY_AMP_Y
        )
    )

    scaled_width, scaled_height = bg_scaled.size

    crop_x = max(
        0,
        min(
            (scaled_width - VIDEO_W) // 2 + sway_x,
            scaled_width - VIDEO_W
        )
    )

    crop_y = max(
        0,
        min(
            (scaled_height - VIDEO_H) // 2 + sway_y,
            scaled_height - VIDEO_H
        )
    )

    frame = bg_scaled.crop(
        (
            crop_x,
            crop_y,
            crop_x + VIDEO_W,
            crop_y + VIDEO_H
        )
    ).convert("RGBA")

    overlay = Image.new(
        "RGBA",
        frame.size,
        (0, 0, 0, BG_OVERLAY)
    )

    frame = Image.alpha_composite(
        frame,
        overlay
    )

    _close_quietly(overlay)

    _paste_cover(
        frame,
        cover_base,
        t
    )

    ring_layer = Image.new(
        "RGBA",
        frame.size,
        (0, 0, 0, 0)
    )

    _draw_ring_dots(
        ring_layer,
        t
    )

    frame = Image.alpha_composite(
        frame,
        ring_layer
    )

    _close_quietly(ring_layer)

    draw = ImageDraw.Draw(frame)

    _draw_text(
        draw,
        TITLE_X,
        TITLE_Y,
        f"【{song_title}】",

        fonts["title"],
        C_TITLE
    )

    if artist:
        _draw_text(
            draw,
            ARTIST_X,
            TITLE_Y + FS_TITLE + ARTIST_SPACING,
            artist,
            fonts["artist"],
            C_ARTIST
        )

    if lyric_times:
        current_index = (
            bisect_right(lyric_times, t) - 1
        )
    else:
        current_index = -1

    if current_index < 0:
        scroll_offset = 0
        top_offset = 0
    else:
        elapsed = (
            t - lyrics[current_index][0]
        )

        scroll_progress = (
            elapsed / SCROLL_DURATION
        )

        scroll_offset = (
            LINE_H
            * (
                1.0
                - _ease_out_cubic(
                    scroll_progress
                )
            )
        )

        top_offset = max(
            0,
            LINES_ABOVE - current_index
        ) * LINE_H

    display_current_index = max(
        current_index,
        0
    )

    for relative_index in range(
        -LINES_ABOVE,
        LINES_BELOW + 1
    ):
        lyric_index = (
            display_current_index
            + relative_index
        )

        if (
            lyric_index < 0
            or lyric_index >= len(lyrics)
        ):
            continue

        y = int(
            LYRIC_CURRENT_Y
            - top_offset
            + relative_index * LINE_H
            + scroll_offset
        )

        is_current = (
            relative_index == 0
            and current_index >= 0
        )

        font = (
            fonts["current"]
            if is_current
            else fonts["normal"]
        )

        color = (
            C_CURRENT
            if is_current
            else (
                C_ABOVE
                if relative_index < 0
                else C_BELOW
            )
        )

        if is_current:
            alpha = 255
        elif relative_index < 0:
            alpha = max(
                0,
                int(
                    200
                    * (
                        1.0
                        - abs(relative_index) * 0.45
                    )
                )
            )
        else:
            alpha = max(
                0,
                int(
                    150
                    * (
                        1.0
                        - (
                            relative_index - 1
                        ) * 0.13
                    )
                )
            )

        if alpha <= 0:
            continue

        _draw_text(
            draw,
            LYRIC_X,
            y,
            lyrics[lyric_index][1],
            font,
            color,
            alpha
        )

    result = np.array(
        frame.convert("RGB")
    )

    _close_quietly(frame)

    return result


# ============================================================
# 8. 主视频生成函数
# ============================================================

def generate_lyric_video(
        song_name: str,
        artist_name: str = "",
        bg_name: Optional[str] = None,
        cover_name: Optional[str] = None,
        font_paths: Optional[Dict[str, str]] = None
) -> str:
    """
    生成歌词视频。

    song_name 可以写：

        "歌曲名称"
        "歌曲名称.m4a"
        "歌曲名称.M4A"

    程序会自动寻找 input 目录下对应的音频文件。
    """

    requested_path = Path(str(song_name))
    song_stem = (
        requested_path.stem
        if requested_path.suffix
        else requested_path.name
    )

    target_bg = (
        bg_name
        if bg_name
        else DEFAULT_BG_NAME
    )

    # 第四个参数不填时，封面默认使用第三个背景参数
    target_cover = (
        cover_name
        if cover_name
        else target_bg
    )

    input_dir = Path(
        get_abs_path("input")
    )

    lrc_path = Path(
        get_abs_path(
            "output",
            "lrcCorrection",
            f"{song_stem}.lrc"
        )
    )

    img_dir = get_abs_path(
        "resources",
        "imgs"
    )

    output_dir = get_abs_path(
        "output",
        "vedio"
    )

    os.makedirs(
        output_dir,
        exist_ok=True
    )

    video_path = os.path.join(
        output_dir,
        f"{song_stem}.mp4"
    )

    # 自动查找音频文件
    audio_path = _find_audio_file(
        input_dir,
        song_name
    )

    if not lrc_path.is_file():
        raise FileNotFoundError(
            f"找不到歌词文件：{lrc_path}"
        )

    font_paths = font_paths or {}

    fonts = {
        "current": _load_font(
            FS_CURRENT,
            bold=True,
            custom_path=font_paths.get(
                "lyric",
                CUSTOM_FONT_LYRIC
            )
        ),
        "normal": _load_font(
            FS_NORMAL,
            custom_path=font_paths.get(
                "lyric",
                CUSTOM_FONT_LYRIC
            )
        ),
        "title": _load_font(
            FS_TITLE,
            bold=True,
            custom_path=font_paths.get(
                "title",
                CUSTOM_FONT_TITLE
            )
        ),
        "artist": _load_font(
            FS_ARTIST,
            custom_path=font_paths.get(
                "artist",
                CUSTOM_FONT_ARTIST
            )
        ),
    }

    audio = None
    audio_segment = None
    video = None

    bg_full = None
    bg_scaled = None
    cover_src = None
    cover_crop = None
    cover_base = None

    temporary_audio_path = None
    temporary_video_path = None

    try:
        # 处理中文音频路径
        ffmpeg_audio_path, temporary_audio_path = (
            _prepare_audio_for_ffmpeg(audio_path)
        )

        # m4a 会在这里由 FFmpeg 解码
        audio = AudioFileClip(
            ffmpeg_audio_path
        )

        audio_duration = float(
            audio.duration or 0
        )

        if audio_duration <= 0:
            raise ValueError(
                f"无法读取音频时长：{audio_path}"
            )

        # 读取歌词
        metadata, lyrics = _parse_lrc(
            str(lrc_path)
        )

        lyric_times = [
            timestamp
            for timestamp, _ in lyrics
        ]

        title = metadata.get(
            "ti",
            song_stem
        )

        artist = (
            artist_name
            or metadata.get("ar", "")
        )

        # ----------------------------------------------------
        # 加载背景图
        # ----------------------------------------------------

        background_path = _find_image(
            img_dir,
            target_bg
        )

        if background_path:
            with Image.open(background_path) as raw_image:
                original_width, original_height = (
                    raw_image.size
                )

                target_aspect = (
                    VIDEO_W / VIDEO_H
                )

                original_aspect = (
                    original_width / original_height
                )

                if original_aspect > target_aspect:
                    # 图片太宽，裁剪左右
                    new_width = int(
                        original_height
                        * target_aspect
                    )

                    left = (
                        original_width - new_width
                    ) // 2

                    crop_box = (
                        left,
                        0,
                        left + new_width,
                        original_height
                    )
                else:
                    # 图片太高，裁剪上下
                    new_height = int(
                        original_width
                        / target_aspect
                    )

                    top = (
                        original_height - new_height
                    ) // 2

                    crop_box = (
                        0,
                        top,
                        original_width,
                        top + new_height
                    )

                bg_full = raw_image.crop(
                    crop_box
                ).resize(
                    (VIDEO_W, VIDEO_H),
                    Image.LANCZOS
                )
        else:
            bg_full = Image.new(
                "RGB",
                (VIDEO_W, VIDEO_H),
                (20, 20, 30)
            )

        bg_scaled = bg_full.resize(
            (
                int(VIDEO_W * BG_SCALE_FACTOR),
                int(VIDEO_H * BG_SCALE_FACTOR)
            ),
            Image.LANCZOS
        ).convert("RGBA")

        _close_quietly(bg_full)
        bg_full = None

        # ----------------------------------------------------
        # 加载封面图
        # ----------------------------------------------------

        cover_path = _find_image(
            img_dir,
            target_cover
        )

        # 没有单独封面时，使用背景图
        if not cover_path:
            cover_path = background_path

        if cover_path:
            with Image.open(cover_path) as raw_cover:
                cover_src = raw_cover.convert("RGB")
        else:
            cover_src = Image.new(
                "RGB",
                (VIDEO_W, VIDEO_H),
                (20, 20, 30)
            )

        cover_width, cover_height = (
            cover_src.size
        )

        square_size = min(
            cover_width,
            cover_height
        )

        cover_crop = cover_src.crop(
            (
                (cover_width - square_size) // 2,
                (cover_height - square_size) // 2,
                (cover_width + square_size) // 2,
                (cover_height + square_size) // 2
            )
        )

        cover_base = cover_crop.resize(
            (COVER_R * 2, COVER_R * 2),
            Image.LANCZOS
        ).convert("RGBA")

        _close_quietly(cover_src)
        cover_src = None

        _close_quietly(cover_crop)
        cover_crop = None

        # ----------------------------------------------------
        # 创建视频
        # ----------------------------------------------------

        if DEBUG_MODE:
            render_duration = min(
                float(DEBUG_DURATION),
                audio_duration
            )
        else:
            render_duration = audio_duration

        video = VideoClip(
            lambda current_time: _render_frame(
                current_time,
                bg_scaled,
                cover_base,
                lyrics,
                lyric_times,
                title,
                artist,
                fonts
            ),
            duration=render_duration
        )

        audio_segment = audio.subclip(
            0,
            render_duration
        )

        video = video.set_audio(
            audio_segment
        )

        temporary_video_path = tempfile.NamedTemporaryFile(
            suffix=".mp4",
            delete=False
        ).name

        video.write_videofile(
            temporary_video_path,
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            preset="fast",
            ffmpeg_params=[
                "-crf",
                "18",
                "-threads",
                "4",
                "-b:a",
                "320k",
            ]
        )

        _close_quietly(video)
        video = None

        _close_quietly(audio_segment)
        audio_segment = None

        _close_quietly(audio)
        audio = None

        # 如果旧视频存在，先删除
        if os.path.exists(video_path):
            os.remove(video_path)

        # shutil.move 支持从 C 盘移动到 D 盘
        shutil.move(
            temporary_video_path,
            video_path
        )

        temporary_video_path = None




        print(
            f"视频生成完成：{video_path}"
        )

        return video_path

    finally:
        _close_quietly(video)
        _close_quietly(audio_segment)
        _close_quietly(audio)

        _close_quietly(bg_full)
        _close_quietly(bg_scaled)

        _close_quietly(cover_src)
        _close_quietly(cover_crop)
        _close_quietly(cover_base)

        # 删除中文路径临时音频
        if (
            temporary_audio_path
            and os.path.exists(temporary_audio_path)
        ):
            try:
                os.remove(
                    temporary_audio_path
                )
            except Exception:
                pass

        # 删除临时视频
        if (
            temporary_video_path
            and os.path.exists(temporary_video_path)
        ):
            try:
                os.remove(
                    temporary_video_path
                )
            except Exception:
                pass


# ============================================================
# 9. 批量执行入口
# ============================================================

if __name__ == "__main__":

    # 这里继续填写你的歌曲列表。
    #
    # 第一个参数：
    #   可以写歌曲名，也可以写歌曲名.m4a
    #
    # 第二个参数：
    #   歌手名称
    #
    # 第三个参数：
    #   resources/imgs 目录中的背景图片名称，不需要扩展名
    #
    # 第四个参数：
    #   可选，resources/imgs 目录中的封面图片名称

    songs = [
        ("年少有为", "李荣浩", "年少有为"),
        ("不将就", "李荣浩", "不将就"),

        ("伯虎说", "伯爵Johnny&唐伯虎Annie", "伯虎说"),
        ("红玫瑰", "陈奕迅", "红玫瑰"),
        ("给我一个理由忘记", "A-Lin", "给我一个理由忘记"),



        # ("蜀道难", "少司命", "蜀道难"),
        # ("滕王阁序", "萧忆情&Assen捷", "滕王阁序"),

        # 例如明确指定使用 m4a：
        # ("起风了.m4a", "买辣椒也用券", "起风了"),
    ]

    for song in songs:
        try:
            generate_lyric_video(*song)

        except Exception as error:
            print(
                f"歌曲 {song[0]} 生成失败：{error}"
            )

        finally:
            gc.collect()