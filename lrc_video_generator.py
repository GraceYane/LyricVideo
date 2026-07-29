#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LRC 歌词视频生成器
效果：仿 iPhone 备忘录风格，黑底金字，随歌词时间轴逐行打勾
用法：python lrc_video_generator.py --mp3 歌曲.mp3 --lrc 歌词.lrc
"""

import re
import argparse
import os
import sys
import math
from pathlib import Path

# ── 依赖检查 ──────────────────────────────────────────────────────────────────
def check_dependencies():
    missing = []
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        missing.append("Pillow")
    try:
        import numpy
    except ImportError:
        missing.append("numpy")
    try:
        import moviepy
    except ImportError:
        missing.append("moviepy")
    if missing:
        print(f"[错误] 缺少依赖，请运行：pip install {' '.join(missing)}")
        sys.exit(1)

check_dependencies()

from PIL import Image, ImageDraw, ImageFont
import numpy as np
from moviepy.editor import VideoClip, AudioFileClip, CompositeVideoClip

# ── 配置 ──────────────────────────────────────────────────────────────────────
VIDEO_W = 1080          # 视频宽（px）
VIDEO_H = 1920          # 视频高（px）  竖屏 9:16
FPS = 30

# 颜色
BG_COLOR      = (0, 0, 0)           # 黑色背景
TITLE_COLOR   = (255, 255, 255)     # 白色标题
LYRIC_COLOR   = (255, 255, 255)     # 白色未播放歌词
DONE_COLOR    = (255, 255, 255)     # 已播放歌词颜色（保持白色）
CIRCLE_EMPTY  = (180, 180, 180)     # 空心圆颜色
CIRCLE_DONE   = (255, 195, 0)       # 金色勾选圆  #FFC300
CHECK_COLOR   = (0, 0, 0)          # 勾的颜色（黑色，在金圆上）
HEADER_COLOR  = (255, 195, 0)       # 顶栏金色文字

# 字体大小
HEADER_FONT_SIZE  = 44
TITLE_FONT_SIZE   = 62
LYRIC_FONT_SIZE   = 50
BULLET_SIZE       = 50             # 实心圆/勾选圆直径

# 边距
MARGIN_LEFT  = 80
MARGIN_TOP   = 120
LINE_SPACING = 20   # 行间额外间距（不含字体高度）

# 顶栏文字（可自定义）
HEADER_TEXT = "< 一个小橘子🍊"

# ── 字体加载 ──────────────────────────────────────────────────────────────────
def load_font(size, bold=False):
    """
    优先加载系统中文字体，找不到则用默认字体
    Windows: C:/Windows/Fonts/
    macOS:   /System/Library/Fonts/ 或 ~/Library/Fonts/
    Linux:   /usr/share/fonts/
    """
    candidates_bold = [
        # Windows
        "C:/Windows/Fonts/msyhbd.ttc",   # 微软雅黑 Bold
        "C:/Windows/Fonts/simhei.ttf",   # 黑体
        "C:/Windows/Fonts/stzhongs.ttf",
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        # Linux
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ]
    candidates_normal = [
        # Windows
        "C:/Windows/Fonts/msyh.ttc",     # 微软雅黑
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        # Linux
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    candidates = candidates_bold if bold else candidates_normal
    from PIL import ImageFont
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    # 最终回退
    return ImageFont.load_default()


# ── LRC 解析 ──────────────────────────────────────────────────────────────────
def parse_lrc(lrc_path: str):
    """
    解析 LRC 文件，返回 [(time_sec, text), ...] 按时间排序
    同时提取 title / artist 元信息
    """
    meta = {}
    lines = []
    time_pattern = re.compile(r'\[(\d{2}):(\d{2})\.(\d{2,3})\]')
    meta_pattern = re.compile(r'\[(\w+):(.*)\]')

    with open(lrc_path, encoding='utf-8', errors='replace') as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            # 提取元信息
            m = meta_pattern.match(raw)
            if m and not time_pattern.search(raw):
                meta[m.group(1).lower()] = m.group(2).strip()
                continue
            # 提取时间轴歌词（一行可能有多个时间标签）
            times = time_pattern.findall(raw)
            text  = time_pattern.sub('', raw).strip()
            if not text:
                continue
            for mm, ss, ms in times:
                ms_str = ms.ljust(3, '0')[:3]  # 统一到毫秒
                t = int(mm) * 60 + int(ss) + int(ms_str) / 1000.0
                lines.append((t, text))

    lines.sort(key=lambda x: x[0])
    return meta, lines


# ── 绘制单帧 ──────────────────────────────────────────────────────────────────
def draw_frame(
    song_title: str,
    lyric_lines: list,      # [(time_sec, text), ...]
    current_time: float,
    bullet_lines: list,     # 前几行用实心圆（非时间轴，通常是副歌提示）
    fonts: dict,
):
    """
    绘制一帧 PIL Image。
    bullet_lines: 索引列表，这些行用 ● 而不是勾选圆
    """
    img  = Image.new("RGB", (VIDEO_W, VIDEO_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # ── 顶栏 ──────────────────────────────────────────
    draw.text((MARGIN_LEFT, 60), HEADER_TEXT,
              font=fonts['header'], fill=HEADER_COLOR)

    # 右侧图标（简单用文字代替）
    draw.text((VIDEO_W - 180, 60), "⬆  ···",
              font=fonts['header'], fill=HEADER_COLOR)

    # ── 歌曲标题 ──────────────────────────────────────
    title_y = MARGIN_TOP + 80
    draw.text((MARGIN_LEFT, title_y), song_title,
              font=fonts['title'], fill=TITLE_COLOR)

    # ── 歌词列表 ──────────────────────────────────────
    line_h = LYRIC_FONT_SIZE + LINE_SPACING + 10
    start_y = title_y + TITLE_FONT_SIZE + 50

    for i, (t, text) in enumerate(lyric_lines):
        y = start_y + i * line_h
        if y + line_h > VIDEO_H - 60:
            break  # 超出画面不绘制

        cx = MARGIN_LEFT + BULLET_SIZE // 2   # 圆心 x
        cy = y + LYRIC_FONT_SIZE // 2 + 10      # 圆心 y（+10 向下偏移对齐歌词基线）
        r  = BULLET_SIZE // 2 - 2

        is_bullet = False
        is_done   = (current_time >= t)

        if is_bullet:
            # 实心小圆点 ●
            draw.ellipse(
                [cx - 8, cy - 8, cx + 8, cy + 8],
                fill=LYRIC_COLOR
            )
        elif is_done:
            # 金色实心圆 + 白色勾
            draw.ellipse(
                [cx - r, cy - r, cx + r, cy + r],
                fill=CIRCLE_DONE
            )
            _draw_checkmark(draw, cx, cy, r - 6, CHECK_COLOR)
        else:
            # 空心圆
            draw.ellipse(
                [cx - r, cy - r, cx + r, cy + r],
                outline=CIRCLE_EMPTY, width=3
            )

        # 歌词文字
        text_x = MARGIN_LEFT + BULLET_SIZE + 20
        text_color = DONE_COLOR if is_done else LYRIC_COLOR
        draw.text((text_x, y), text, font=fonts['lyric'], fill=text_color)

    return img


def _draw_checkmark(draw, cx, cy, size, color):
    """在 (cx,cy) 处绘制勾号"""
    # 勾号三点坐标（相对中心）
    p1 = (cx - size * 0.5, cy)
    p2 = (cx - size * 0.1, cy + size * 0.45)
    p3 = (cx + size * 0.55, cy - size * 0.45)
    lw = max(3, int(size * 0.22))
    draw.line([p1, p2], fill=color, width=lw)
    draw.line([p2, p3], fill=color, width=lw)


# ── 主流程 ────────────────────────────────────────────────────────────────────
def generate_video(mp3_path: str, lrc_path: str, output_path: str,
                   header_text: str = None,
                   bullet_count: int = 2,
                   fade_duration: float = 0.3):
    """
    mp3_path     : 音频文件路径
    lrc_path     : LRC 歌词文件路径
    output_path  : 输出视频路径（.mp4）
    header_text  : 顶栏文字，默认读脚本常量
    bullet_count : 前 N 行用实心圆（非勾选），通常是前奏/副歌提示
    fade_duration: 状态切换的淡入淡出时长（秒）
    """
    global HEADER_TEXT
    if header_text:
        HEADER_TEXT = header_text

    print(f"[1/4] 解析 LRC 文件: {lrc_path}")
    meta, lyric_lines = parse_lrc(lrc_path)

    # 从 meta 提取标题，或使用文件名
    title  = meta.get('ti', '')
    artist = meta.get('ar', '')
    if title and artist:
        song_title = f"《{title}》-{artist}"
    elif title:
        song_title = f"《{title}》"
    else:
        song_title = Path(mp3_path).stem

    print(f"    歌曲: {song_title}")
    print(f"    歌词行数: {len(lyric_lines)}")

    # 前 bullet_count 行作为实心圆（只在 lyric_lines 中标记索引）
    bullet_indices = list(range(min(bullet_count, len(lyric_lines))))

    print(f"[2/4] 加载字体")
    fonts = {
        'header': load_font(HEADER_FONT_SIZE),
        'title' : load_font(TITLE_FONT_SIZE, bold=True),
        'lyric' : load_font(LYRIC_FONT_SIZE),
    }

    print(f"[3/4] 加载音频: {mp3_path}")
    audio = AudioFileClip(mp3_path)
    duration = audio.duration

    print(f"    时长: {duration:.1f}s")

    def make_frame(t):
        img = draw_frame(
            song_title   = song_title,
            lyric_lines  = lyric_lines,
            current_time = t,
            bullet_lines = bullet_indices,
            fonts        = fonts,
        )
        return np.array(img)

    print(f"[4/4] 渲染视频 (分辨率 {VIDEO_W}x{VIDEO_H}, {FPS}fps)...")
    video = VideoClip(make_frame, duration=duration)
    video = video.set_audio(audio)

    video.write_videofile(
        output_path,
        fps=FPS,
        codec='libx264',
        audio_codec='aac',
        temp_audiofile='_temp_audio.m4a',
        remove_temp=True,
        preset='fast',
        ffmpeg_params=['-crf', '18'],
        logger='bar',
    )
    print(f"\n✅ 视频已生成：{output_path}")


# ── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='生成仿 iPhone 备忘录歌词视频',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python lrc_video_generator.py --mp3 song.mp3 --lrc song.lrc
  python lrc_video_generator.py --mp3 song.mp3 --lrc song.lrc --output out.mp4 --header "< 我的歌单🎵" --bullet 2
        """
    )
    parser.add_argument('--mp3',    required=True,  help='MP3 音频文件路径')
    parser.add_argument('--lrc',    required=True,  help='LRC 歌词文件路径')
    parser.add_argument('--output', default='',     help='输出视频路径，默认与 mp3 同名 .mp4')
    parser.add_argument('--header', default='',     help='顶栏文字，默认 "< 一个小橘子🍊"')
    parser.add_argument('--bullet', type=int, default=2,
                        help='前 N 行用实心圆点（默认 2，对应前奏歌词）')
    args = parser.parse_args()

    if not os.path.exists(args.mp3):
        print(f"[错误] MP3 文件不存在: {args.mp3}"); sys.exit(1)
    if not os.path.exists(args.lrc):
        print(f"[错误] LRC 文件不存在: {args.lrc}"); sys.exit(1)

    out = args.output or Path(args.mp3).with_suffix('.mp4').name
    generate_video(
        mp3_path    = args.mp3,
        lrc_path    = args.lrc,
        output_path = out,
        header_text = args.header or None,
        bullet_count= args.bullet,
    )
