#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iPhone 备忘录风格歌词视频生成器
封装函数：generate_iphone_lyric_video(song_name)
路径约定：MP3在 input/，LRC在 output/lrcCorrection/，输出在 output/vedio/
"""

import os
import sys
import re
import math
from pathlib import Path


# ── 依赖检查 ──────────────────────────────────────────────────────────────────
def _check_dependencies():
    missing = []
    try:
        from PIL import Image
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


_check_dependencies()

from PIL import Image, ImageDraw, ImageFont
import numpy as np
from moviepy.editor import VideoClip, AudioFileClip

# ── 视觉配置 ──────────────────────────────────────────────────────────────────
VIDEO_W, VIDEO_H, FPS = 1080, 1920, 30
BG_COLOR = (0, 0, 0)
TITLE_COLOR = (255, 255, 255)
LYRIC_COLOR = (200, 200, 200)  # 未播放歌词微灰
DONE_COLOR = (255, 255, 255)  # 已播放歌词纯白
CIRCLE_EMPTY = (120, 120, 120)
CIRCLE_DONE = (255, 195, 0)  # 金色 ✅
CHECK_COLOR = (0, 0, 0)  # 黑色勾
HEADER_COLOR = (255, 195, 0)

HEADER_FONT_SIZE = 44
TITLE_FONT_SIZE = 62
LYRIC_FONT_SIZE = 50
BULLET_SIZE = 50
MARGIN_LEFT = 80
MARGIN_TOP = 120
LINE_SPACING = 18


# ── 字体加载 ──────────────────────────────────────────────────────────────────
def _load_font(size, bold=False):
    candidates = [
        r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\STZHONGS.TTF",
        "/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    ] if bold else [
        r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf",
        "/System/Library/Fonts/PingFang.ttc", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ── LRC 解析 ──────────────────────────────────────────────────────────────────
def _parse_lrc(lrc_path: str):
    meta, lines = {}, []
    time_pat = re.compile(r'\[(\d{2}):(\d{2})\.(\d{2,3})\]')
    meta_pat = re.compile(r'\[(\w+):(.*)\]')

    with open(lrc_path, encoding='utf-8', errors='replace') as f:
        for raw in f:
            raw = raw.strip()
            if not raw: continue
            m = meta_pat.match(raw)
            if m and not time_pat.search(raw):
                meta[m.group(1).lower()] = m.group(2).strip()
                continue
            times = time_pat.findall(raw)
            text = time_pat.sub('', raw).strip()
            if not text: continue
            for mm, ss, ms in times:
                t = int(mm) * 60 + int(ss) + int(ms.ljust(3, '0')[:3]) / 1000.0
                lines.append((t, text))
    lines.sort(key=lambda x: x[0])
    return meta, lines


# ── 帧绘制核心 ────────────────────────────────────────────────────────────────
def _draw_checkmark(draw, cx, cy, size, color):
    p1, p2, p3 = (cx - size * 0.5, cy), (cx - size * 0.1, cy + size * 0.45), (cx + size * 0.55, cy - size * 0.45)
    lw = max(3, int(size * 0.22))
    draw.line([p1, p2], fill=color, width=lw)
    draw.line([p2, p3], fill=color, width=lw)


def _draw_frame(song_title, lyric_lines, current_time, bullet_indices, fonts):
    img = Image.new("RGB", (VIDEO_W, VIDEO_H), BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw.text((MARGIN_LEFT, 60), "< 一个小橘子🍊", font=fonts['header'], fill=HEADER_COLOR)
    draw.text((VIDEO_W - 160, 60), "⬆  ···", font=fonts['header'], fill=HEADER_COLOR)

    title_y = MARGIN_TOP + 80
    draw.text((MARGIN_LEFT, title_y), song_title, font=fonts['title'], fill=TITLE_COLOR)

    line_h = LYRIC_FONT_SIZE + LINE_SPACING + 10
    start_y = title_y + TITLE_FONT_SIZE + 50

    for i, (t, text) in enumerate(lyric_lines):
        y = start_y + i * line_h
        if y + line_h > VIDEO_H - 60: break

        cx, cy = MARGIN_LEFT + BULLET_SIZE // 2, y + LYRIC_FONT_SIZE // 2 + 10
        r = BULLET_SIZE // 2 - 2

        # 判断当前歌词是否已经播放
        is_done = current_time >= t

        # 统一逻辑：已播放=金色圆圈+对勾，未播放=空心圆圈
        if is_done:
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=CIRCLE_DONE)
            _draw_checkmark(draw, cx, cy, r - 6, CHECK_COLOR)
        else:
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=CIRCLE_EMPTY, width=3)

        txt_color = DONE_COLOR if is_done else LYRIC_COLOR
        draw.text((MARGIN_LEFT + BULLET_SIZE + 20, y), text, font=fonts['lyric'], fill=txt_color)
    return img

# 下边是伴奏版本的
# def _draw_frame(song_title, lyric_lines, current_time, bullet_indices, fonts):
#     img = Image.new("RGB", (VIDEO_W, VIDEO_H), BG_COLOR)
#     draw = ImageDraw.Draw(img)
#     draw.text((MARGIN_LEFT, 60), "< 一个小橘子🍊", font=fonts['header'], fill=HEADER_COLOR)
#     draw.text((VIDEO_W - 160, 60), "⬆  ···", font=fonts['header'], fill=HEADER_COLOR)
#
#     title_y = MARGIN_TOP + 80
#     draw.text((MARGIN_LEFT, title_y), song_title, font=fonts['title'], fill=TITLE_COLOR)
#
#     line_h = LYRIC_FONT_SIZE + LINE_SPACING + 10
#     start_y = title_y + TITLE_FONT_SIZE + 50
#
#     for i, (t, text) in enumerate(lyric_lines):
#         y = start_y + i * line_h
#         if y + line_h > VIDEO_H - 60: break
#
#         cx, cy = MARGIN_LEFT + BULLET_SIZE // 2, y + LYRIC_FONT_SIZE // 2 + 10
#         r = BULLET_SIZE // 2 - 2
#
#         is_bullet = i in bullet_indices
#         is_done = current_time >= t
#
#         if is_bullet:
#             # draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=LYRIC_COLOR)
#             draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=CIRCLE_DONE)
#         elif is_done:
#             draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=CIRCLE_DONE)
#             _draw_checkmark(draw, cx, cy, r - 6, CHECK_COLOR)
#         else:
#             draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=CIRCLE_EMPTY, width=3)
#
#         txt_color = DONE_COLOR if is_done else LYRIC_COLOR
#         draw.text((MARGIN_LEFT + BULLET_SIZE + 20, y), text, font=fonts['lyric'], fill=txt_color)
#     return img


# ── 🎯 主封装函数 ─────────────────────────────────────────────────────────────
def generate_iphone_lyric_video(song_name: str, header_text: str = "< 一个小橘子🍊", bullet_count: int = 2) -> str:
    """
    输入歌曲名，自动生成 iPhone 备忘录风格歌词视频
    :return: 生成视频的绝对路径
    """
    # 1. 动态定位项目根目录 (兼容从任意位置调用)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mp3_path = os.path.join(project_root, "input", f"{song_name}.mp3")
    lrc_path = os.path.join(project_root, "output", "lrcCorrection", f"{song_name}.lrc")
    out_dir = os.path.join(project_root, "output", "vedio")
    video_path = os.path.join(out_dir, f"{song_name}.mp4")

    if not os.path.exists(mp3_path): raise FileNotFoundError(f"❌ 找不到音频: {mp3_path}")
    if not os.path.exists(lrc_path): raise FileNotFoundError(f"❌ 找不到歌词: {lrc_path}")

    os.makedirs(out_dir, exist_ok=True)
    print(f"📂 路径就绪 | MP3: {os.path.basename(mp3_path)} | LRC: {os.path.basename(lrc_path)}")

    # 2. 解析数据
    print("📖 解析 LRC 歌词...")
    meta, lyric_lines = _parse_lrc(lrc_path)
    title = meta.get('ti', '') or song_name
    artist = meta.get('ar', '')
    song_title = f"《{title}》-{artist}" if artist else f"《{title}》"
    bullet_indices = list(range(min(bullet_count, len(lyric_lines))))
    print(f"🎵 歌曲: {song_title} | 歌词: {len(lyric_lines)} 行 | 前奏实心圆: {bullet_count} 行")

    # 3. 加载资源
    print("🔤 加载系统字体...")
    fonts = {'header': _load_font(HEADER_FONT_SIZE), 'title': _load_font(TITLE_FONT_SIZE, bold=True),
             'lyric': _load_font(LYRIC_FONT_SIZE)}

    print("🎧 加载音频并计算时长...")
    audio = AudioFileClip(mp3_path)
    duration = audio.duration

    # 4. 定义帧生成闭包
    def make_frame(t):
        return np.array(_draw_frame(song_title, lyric_lines, t, bullet_indices, fonts))

    # 5. 渲染输出
    print(f"🎬 开始渲染视频 ({VIDEO_W}x{VIDEO_H} @{FPS}fps)...")
    video = VideoClip(make_frame, duration=duration).set_audio(audio)
    video.write_videofile(
        video_path, fps=FPS, codec='libx264', audio_codec='aac',
        preset='fast', ffmpeg_params=['-crf', '18'], logger='bar'
    )
    print(f"✅ 视频生成完毕: {os.path.abspath(video_path)}")
    return os.path.abspath(video_path)


# ── 本地测试入口 ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    generate_iphone_lyric_video("天龙八部之宿敌")