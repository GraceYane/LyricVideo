#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iPhone 备忘录风格歌词视频生成器 —— iOS 重设计版
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

# ── 视觉配置（iOS 设计语言 - 黄色主题版） ───────────────────────────────────
VIDEO_W, VIDEO_H, FPS = 1080, 1920, 30

# 🟡 修改后的颜色方案 - 纯黑背景 + 黄色主题
BG_COLOR = (0, 0, 0)  # 纯黑色背景
SURFACE_COLOR = (20, 20, 20)  # 稍微亮一点的黑色（用于区分层次）
SEPARATOR_COLOR = (45, 45, 45)  # 深灰分隔线

HEADER_FG = (255, 215, 0)  # 🟡 金黄色 #FFD700
HEADER_BACK = (255, 215, 0)  # 🟡 导航栏文字改为黄色

TITLE_COLOR = (255, 255, 255)  # 标题保持白色
LYRIC_INACTIVE = (128, 128, 128)  # 未播放歌词：灰色
LYRIC_ACTIVE = (255, 255, 255)  # 已播放歌词：纯白

# 🟡 iOS Checkbox 颜色改为黄色
CHECK_FILL_DONE = (255, 215, 0)  # 🟡 systemYellow #FFD700
CHECK_FILL_EMPTY = (0, 0, 0)  # 🟡 纯黑色（与背景一致）
CHECK_BORDER = (128, 128, 128)  # 🟡 白色边框
CHECK_MARK = (0, 0, 0)  # 🟡 勾号改为黑色（黄色背景上更清晰）

# 🟡 进度条改为黄色
PROG_BG = (45, 45, 45)
PROG_FG = (255, 215, 0)  # 🟡 进度条黄色


# 布局常量，歌词的位置
MARGIN_LEFT = 92
MARGIN_RIGHT = 72
MARGIN_TOP = 0
LINE_H_BASE = 88  # 每行总高（含行间距）
BULLET_R = 22  # checkbox 半径
BULLET_MARGIN = 60  # bullet 右侧到文字间距

HEADER_FONT_SIZE = 38
TITLE_FONT_SIZE = 60
LYRIC_FONT_SIZE = 46
SUBTITLE_FONT_SIZE = 32
DATE_FONT_SIZE = 30


# ── 字体加载（优先 SF Pro → PingFang → 微软雅黑 → 备用） ───────────────────
def _load_font(size: int, weight: str = "regular"):
    """weight: 'regular' | 'bold' | 'semibold'"""
    # SF Pro / Apple fonts (macOS / iOS)
    sf_bold = [
        "/System/Library/Fonts/SFPro-Bold.otf",
        "/System/Library/Fonts/SF Pro Display/SF-Pro-Display-Bold.otf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    sf_regular = [
        "/System/Library/Fonts/SFPro-Regular.otf",
        "/System/Library/Fonts/SF Pro Display/SF-Pro-Display-Regular.otf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    # Windows fallback
    win_bold = [r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc"]
    win_regular = [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"]
    # Linux fallback
    linux_bold = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                  "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"]
    linux_reg = ["/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                 "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"]

    if weight == "bold":
        candidates = sf_bold + win_bold + linux_bold
    else:
        candidates = sf_regular + win_regular + linux_reg

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
            if not raw:
                continue
            m = meta_pat.match(raw)
            if m and not time_pat.search(raw):
                meta[m.group(1).lower()] = m.group(2).strip()
                continue
            times = time_pat.findall(raw)
            text = time_pat.sub('', raw).strip()
            if not text:
                continue
            for mm, ss, ms in times:
                t = int(mm) * 60 + int(ss) + int(ms.ljust(3, '0')[:3]) / 1000.0
                lines.append((t, text))
    lines.sort(key=lambda x: x[0])
    return meta, lines


# ── 绘制工具 ──────────────────────────────────────────────────────────────────
def _aa_ellipse(draw, cx, cy, r, fill=None, outline=None, width=3):
    """用 2x 超采样模拟抗锯齿圆（Pillow 本身 ellipse 无 AA）"""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=outline, width=width)


def _draw_ios_checkmark(draw, cx, cy, r, done: bool):
    """绘制 iOS 风格 checkbox：完成=黄色底黑勾，未完成=黄色边空心"""
    if done:
        # 🟡 实心黄色圆
        _aa_ellipse(draw, cx, cy, r, fill=CHECK_FILL_DONE)
        # 🟡 黑色勾（3段折线，比例参考 SF Symbols checkmark.circle.fill）
        lw = max(4, int(r * 0.28))
        p1 = (cx - r * 0.42, cy + r * 0.02)
        p2 = (cx - r * 0.10, cy + r * 0.38)
        p3 = (cx + r * 0.46, cy - r * 0.32)
        draw.line([p1, p2], fill=CHECK_MARK, width=lw)
        draw.line([p2, p3], fill=CHECK_MARK, width=lw)
    else:
        # 🟡 空心圆（黄色边框）
        _aa_ellipse(draw, cx, cy, r, fill=None, outline=CHECK_BORDER, width=max(3, int(r * 0.14)))


def _draw_progress_bar(draw, current_time, duration, y, h=6):
    """底部 iOS 风格进度条"""
    bar_x = MARGIN_LEFT
    bar_w = VIDEO_W - MARGIN_LEFT - MARGIN_RIGHT
    # 背景轨道
    rx = MARGIN_LEFT
    draw.rounded_rectangle([rx, y, rx + bar_w, y + h], radius=h // 2, fill=PROG_BG)
    # 🟡 黄色进度
    progress = min(1.0, current_time / max(duration, 1))
    prog_w = int(bar_w * progress)
    if prog_w > h:
        draw.rounded_rectangle([rx, y, rx + prog_w, y + h], radius=h // 2, fill=PROG_FG)
    # 🟡 黄色拖块
    knob_x = rx + prog_w
    knob_r = 14
    draw.ellipse([knob_x - knob_r, y + h // 2 - knob_r,
                  knob_x + knob_r, y + h // 2 + knob_r], fill=PROG_FG)


def _draw_separator(draw, y):
    """iOS 分隔线"""
    draw.line([(MARGIN_LEFT, y), (VIDEO_W - MARGIN_RIGHT, y)],
              fill=SEPARATOR_COLOR, width=1)


# ── 核心帧绘制 ────────────────────────────────────────────────────────────────
def _draw_frame(song_title, artist, lyric_lines, current_time, duration, fonts):
    img = Image.new("RGB", (VIDEO_W, VIDEO_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # ── 状态栏占位（iOS 刘海区域模拟）
    STATUS_H = 60

    # ── 顶部导航栏（模拟 iOS Notes NavigationBar）🟡 黄色主题 ──────────
    NAV_H = 110
    nav_y_top = STATUS_H
    nav_mid = nav_y_top + NAV_H // 2

    # 🟡 返回按钮 "< 备忘录" - 黄色
    back_txt = "< 备忘录"
    draw.text((MARGIN_LEFT, nav_mid - HEADER_FONT_SIZE // 2),
              back_txt, font=fonts['header'], fill=HEADER_BACK)

    # 🟡 右侧操作区 "···" 分享 - 黄色
    right_txt = "···"
    right_w = draw.textlength(right_txt, font=fonts['header'])
    draw.text((VIDEO_W - MARGIN_RIGHT - right_w, nav_mid - HEADER_FONT_SIZE // 2),
              right_txt, font=fonts['header'], fill=HEADER_BACK)

    # 导航栏底部分隔线
    _draw_separator(draw, nav_y_top + NAV_H)

    # ── 笔记内容区 ────────────────────────────────────────────────────────
    content_top = nav_y_top + NAV_H + 36

    # 日期行（iOS Notes 风格小灰字）- 保持灰色
    import datetime
    today = datetime.date.today().strftime("%Y年%m月%d日")
    draw.text((MARGIN_LEFT, content_top),
              today, font=fonts['date'], fill=HEADER_FG)

    # 歌曲标题（大标题，bold）- 白色
    title_y = content_top + DATE_FONT_SIZE + 20
    draw.text((MARGIN_LEFT, title_y),
              song_title, font=fonts['title'], fill=TITLE_COLOR)

    # 歌手副标题 - 灰色
    subtitle_y = title_y + TITLE_FONT_SIZE + 10
    draw.text((MARGIN_LEFT, subtitle_y),
              artist, font=fonts['subtitle'], fill=HEADER_FG)

    # 分隔线
    sep_y = subtitle_y + SUBTITLE_FONT_SIZE + 28
    _draw_separator(draw, sep_y)

    # ── 歌词列表 ──────────────────────────────────────────────────────────
    list_top = sep_y + 32
    avail_h = VIDEO_H - list_top - 180  # 为底部进度条留空间

    # 计算最多能显示几行
    max_lines = int(avail_h // LINE_H_BASE)

    # 智能滚动：当前播放行居中
    cur_idx = 0
    for i, (t, _) in enumerate(lyric_lines):
        if current_time >= t:
            cur_idx = i

    # 滑动窗口：让当前行尽量在中间
    half = max_lines // 2
    start_idx = max(0, min(cur_idx - half, len(lyric_lines) - max_lines))
    end_idx = min(len(lyric_lines), start_idx + max_lines)

    for i, (t, text) in enumerate(lyric_lines[start_idx:end_idx]):
        real_i = start_idx + i
        row_y = list_top + i * LINE_H_BASE
        # 歌词前边的圆圈
        cy = row_y + LINE_H_BASE // 2 + 8

        is_done = current_time >= t
        is_current = (real_i == cur_idx)

        # 🟡 checkbox - 黄色主题
        cx = MARGIN_LEFT + BULLET_R
        _draw_ios_checkmark(draw, cx, cy, BULLET_R, is_done)

        # 文字颜色：当前行=白色粗体，已播放=白色普通，未播放=灰色
        txt_x = MARGIN_LEFT + BULLET_R * 2 + 24
        if is_current:
            color = LYRIC_ACTIVE
            draw.text((txt_x, row_y + (LINE_H_BASE - LYRIC_FONT_SIZE) // 2),
                      text, font=fonts['lyric_bold'], fill=color)
        elif is_done:
            color = LYRIC_ACTIVE
            draw.text((txt_x, row_y + (LINE_H_BASE - LYRIC_FONT_SIZE) // 2),
                      text, font=fonts['lyric'], fill=color)
        else:
            color = LYRIC_INACTIVE
            draw.text((txt_x, row_y + (LINE_H_BASE - LYRIC_FONT_SIZE) // 2),
                      text, font=fonts['lyric'], fill=color)

    # ── 底部进度条区域 🟡 黄色主题 ─────────────────────────────────────
    prog_y = VIDEO_H - 120
    _draw_separator(draw, prog_y - 30)

    # 时间标签
    def fmt_time(sec):
        m, s = int(sec) // 60, int(sec) % 60
        return f"{m}:{s:02d}"

    draw.text((MARGIN_LEFT, prog_y + 20), fmt_time(current_time),
              font=fonts['date'], fill=HEADER_FG)
    dur_txt = fmt_time(duration)
    dur_w = draw.textlength(dur_txt, font=fonts['date'])
    draw.text((VIDEO_W - MARGIN_RIGHT - dur_w, prog_y + 20),
              dur_txt, font=fonts['date'], fill=HEADER_FG)

    _draw_progress_bar(draw, current_time, duration, prog_y, h=8)

    return img


# ── 🎯 主封装函数 ─────────────────────────────────────────────────────────────
def vedioProduceIOS1(song_name: str) -> str:
    """
    输入歌曲名，自动生成 iOS 备忘录风格歌词视频
    :return: 生成视频的绝对路径
    """
    # 1. 路径定位
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mp3_path = os.path.join(project_root, "input", f"{song_name}.mp3")
    lrc_path = os.path.join(project_root, "output", "lrcCorrection", f"{song_name}.lrc")
    out_dir = os.path.join(project_root, "output", "vedio")
    video_path = os.path.join(out_dir, f"{song_name}.mp4")

    if not os.path.exists(mp3_path):
        raise FileNotFoundError(f"❌ 找不到音频: {mp3_path}")
    if not os.path.exists(lrc_path):
        raise FileNotFoundError(f"❌ 找不到歌词: {lrc_path}")
    os.makedirs(out_dir, exist_ok=True)
    print(f"📂 路径就绪 | MP3: {os.path.basename(mp3_path)} | LRC: {os.path.basename(lrc_path)}")

    # 2. 解析 LRC
    print("📖 解析 LRC 歌词...")
    meta, lyric_lines = _parse_lrc(lrc_path)
    title = meta.get('ti', '') or song_name
    artist = meta.get('ar', '')
    song_title_display = f"《{title}》"
    print(f"🎵 歌曲: {song_title_display}  歌手: {artist or '—'}  歌词: {len(lyric_lines)} 行")

    # 3. 加载字体
    print("🔤 加载系统字体...")
    fonts = {
        'header': _load_font(HEADER_FONT_SIZE),
        'title': _load_font(TITLE_FONT_SIZE, weight="bold"),
        'subtitle': _load_font(SUBTITLE_FONT_SIZE),
        'lyric': _load_font(LYRIC_FONT_SIZE),
        'lyric_bold': _load_font(LYRIC_FONT_SIZE, weight="bold"),
        'date': _load_font(DATE_FONT_SIZE),
    }

    # 4. 加载音频
    print("🎧 加载音频...")
    audio = AudioFileClip(mp3_path)
    duration = audio.duration

    # 5. 帧生成闭包
    def make_frame(t):
        return np.array(_draw_frame(
            song_title_display, artist, lyric_lines, t, duration, fonts
        ))

    # 6. 渲染
    print(f"🎬 开始渲染 ({VIDEO_W}x{VIDEO_H} @{FPS}fps)...")
    video = VideoClip(make_frame, duration=duration).set_audio(audio)
    video.write_videofile(
        video_path, fps=FPS, codec='libx264', audio_codec='aac',
        preset='fast', ffmpeg_params=['-crf', '18'], logger='bar'
    )
    print(f"✅ 视频生成完毕: {os.path.abspath(video_path)}")
    return os.path.abspath(video_path)


# ── 本地测试入口 ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    vedioProduceIOS1("天龙八部之宿敌")