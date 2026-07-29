#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音爆款版 · iPhone 备忘录歌词视频生成器
动画特性：
  · 打字机逐字显示（当前行）
  · 光标 | 随打字闪烁，打完后停止
  · 新行淡入出现
  · checkbox 弹性勾选动画（打字完成后触发）
  · 当前行文字呼吸高亮
  · 智能滚动：当前行保持在屏幕中段
路径约定：MP3在 input/，LRC在 output/lrcCorrection/，输出在 output/vedio/
"""

import os, sys, re, math, datetime
from pathlib import Path

def _check_dependencies():
    missing = []
    for pkg in [("PIL", "Pillow"), ("numpy", "numpy"), ("moviepy", "moviepy")]:
        try: __import__(pkg[0])
        except ImportError: missing.append(pkg[1])
    if missing:
        print(f"[错误] 缺少依赖：pip install {' '.join(missing)}")
        sys.exit(1)

_check_dependencies()

from PIL import Image, ImageDraw, ImageFont
import numpy as np
from moviepy.editor import VideoClip, AudioFileClip

# ── 画面规格 ──────────────────────────────────────────────────────────────────
VIDEO_W, VIDEO_H, FPS = 1080, 1920, 30

# ── iOS 系统色 ────────────────────────────────────────────────────────────────
BG_COLOR         = (28,  28,  30)
SEPARATOR_COLOR  = (58,  58,  60)
HEADER_FG        = (174, 174, 178)
IOS_BLUE         = (10,  132, 255)
LYRIC_WHITE      = (255, 255, 255)
LYRIC_DIM        = (99,  99,  102)
PROG_BG          = (58,  58,  60)

# ── 布局 ──────────────────────────────────────────────────────────────────────
MARGIN_L         = 100          # 调整：整体左边距
MARGIN_R         = 72
LINE_H           = 92           # 每行高度
BULLET_R         = 22           # checkbox 半径
HEADER_FS        = 38
TITLE_FS         = 58
SUBTITLE_FS      = 30
DATE_FS          = 28
LYRIC_FS         = 46

# ── 动画参数 ──────────────────────────────────────────────────────────────────
CHARS_PER_SEC    = 10.0   # 打字速度：每秒显示多少个汉字
CURSOR_BLINK_HZ  = 2.0    # 光标闪烁频率
BREATH_AMP       = 18     # 呼吸高亮振幅（亮度 ±N）
BREATH_HZ        = 1.2    # 呼吸频率
BOUNCE_DUR       = 0.35   # checkbox 弹性动画时长（秒）
FADE_DUR         = 0.25   # 新行淡入时长（秒）


# ── 字体 ─────────────────────────────────────────────────────────────────────
def _load_font(size, bold=False):
    candidates = (
        ["/System/Library/Fonts/PingFang.ttc",
         "/System/Library/Fonts/Helvetica.ttc",
         r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc",
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]
        if bold else
        ["/System/Library/Fonts/PingFang.ttc",
         "/System/Library/Fonts/Helvetica.ttc",
         r"C:\Windows\Fonts\msyh.ttc",
         "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"]
    )
    for p in candidates:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except: continue
    return ImageFont.load_default()


# ── LRC 解析 ──────────────────────────────────────────────────────────────────
def _parse_lrc(path):
    meta, lines = {}, []
    tp = re.compile(r'\[(\d{2}):(\d{2})\.(\d{2,3})\]')
    mp = re.compile(r'\[(\w+):(.*)\]')
    with open(path, encoding='utf-8', errors='replace') as f:
        for raw in f:
            raw = raw.strip()
            if not raw: continue
            m = mp.match(raw)
            if m and not tp.search(raw):
                meta[m.group(1).lower()] = m.group(2).strip(); continue
            times = tp.findall(raw)
            text  = tp.sub('', raw).strip()
            if not text: continue
            for mm, ss, ms in times:
                t = int(mm)*60 + int(ss) + int(ms.ljust(3,'0')[:3])/1000.0
                lines.append((t, text))
    lines.sort(key=lambda x: x[0])
    return meta, lines


# ── 动画计算工具 ──────────────────────────────────────────────────────────────
def _easeOutElastic(x):
    """弹性缓动，用于 checkbox 弹跳"""
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    c4 = (2 * math.pi) / 3
    return pow(2, -10*x) * math.sin((x*10 - 0.75) * c4) + 1

def _easeInOutQuad(x):
    return 2*x*x if x < 0.5 else 1 - (-2*x+2)**2 / 2


# ── 绘制工具 ──────────────────────────────────────────────────────────────────
def _checkmark(draw, cx, cy, r, done_progress):
    """
    done_progress: 0~1，弹性动画进度
    0 = 空心灰圆；1 = 蓝色实心+白勾
    """
    if done_progress <= 0:
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=(99,99,102), width=3)
        return

    # 弹性缩放：圆圈先变大再回弹到正常
    scale = _easeOutElastic(done_progress)
    er = max(1, int(r * scale))

    # 蓝色填充（按进度 lerp 颜色）
    prog = min(1.0, done_progress)
    blue = tuple(int(99 + (IOS_BLUE[i]-99)*prog) for i in range(3))
    draw.ellipse([cx-er, cy-er, cx+er, cy+er], fill=blue)

    # 白色勾（只在接近完成时显示）
    if done_progress > 0.4:
        alpha = min(1.0, (done_progress - 0.4) / 0.3)
        wc = int(255 * alpha)
        lw = max(3, int(er * 0.26))
        p1 = (cx - er*0.40, cy + er*0.04)
        p2 = (cx - er*0.08, cy + er*0.38)
        p3 = (cx + er*0.44, cy - er*0.30)
        draw.line([p1, p2], fill=(wc,wc,wc), width=lw)
        draw.line([p2, p3], fill=(wc,wc,wc), width=lw)


def _progress_bar(draw, cur, dur, y, h=8):
    bx, bw = MARGIN_L, VIDEO_W - MARGIN_L - MARGIN_R
    draw.rounded_rectangle([bx, y, bx+bw, y+h], radius=h//2, fill=PROG_BG)
    p = min(1.0, cur / max(dur, 1))
    pw = int(bw * p)
    if pw > h:
        draw.rounded_rectangle([bx, y, bx+pw, y+h], radius=h//2, fill=IOS_BLUE)
    kx = bx + pw
    kr = 14
    draw.ellipse([kx-kr, y+h//2-kr, kx+kr, y+h//2+kr], fill=IOS_BLUE)


def _sep(draw, y):
    draw.line([(MARGIN_L, y), (VIDEO_W-MARGIN_R, y)], fill=SEPARATOR_COLOR, width=1)


def _fmt(sec):
    return f"{int(sec)//60}:{int(sec)%60:02d}"


# ── 核心帧绘制 ────────────────────────────────────────────────────────────────
def _draw_frame(t, dur, song_title, artist, lyric_lines, fonts):
    img  = Image.new("RGB", (VIDEO_W, VIDEO_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # ── 顶部导航栏
    NAV_TOP = 60
    NAV_BOT = NAV_TOP + 110
    nav_mid = (NAV_TOP + NAV_BOT) // 2

    draw.text((MARGIN_L, nav_mid - HEADER_FS//2),
              "< 备忘录", font=fonts['header'], fill=IOS_BLUE)
    rw = draw.textlength("···", font=fonts['header'])
    draw.text((VIDEO_W - MARGIN_R - rw, nav_mid - HEADER_FS//2),
              "···", font=fonts['header'], fill=IOS_BLUE)
    _sep(draw, NAV_BOT)

    # ── 内容区
    cy_cursor = NAV_BOT + 36
    today = datetime.date.today().strftime("%Y年%m月%d日")
    draw.text((MARGIN_L, cy_cursor), today, font=fonts['date'], fill=HEADER_FG)
    cy_cursor += DATE_FS + 18

    draw.text((MARGIN_L, cy_cursor), song_title, font=fonts['title'], fill=LYRIC_WHITE)
    cy_cursor += TITLE_FS + 8

    draw.text((MARGIN_L, cy_cursor), artist, font=fonts['subtitle'], fill=HEADER_FG)
    cy_cursor += SUBTITLE_FS + 24

    _sep(draw, cy_cursor)
    cy_cursor += 32

    # ── 确定当前播放行
    cur_idx = 0
    for i, (lt, _) in enumerate(lyric_lines):
        if t >= lt:
            cur_idx = i

    # ── 智能滚动：当前行居中
    list_top  = cy_cursor
    avail_h   = VIDEO_H - list_top - 160
    max_lines = int(avail_h // LINE_H)
    half      = max_lines // 2
    start_i   = max(0, min(cur_idx - half, len(lyric_lines) - max_lines))
    end_i     = min(len(lyric_lines), start_i + max_lines)

    # ── 呼吸高亮：当前行亮度微振
    breath = math.sin(t * BREATH_HZ * 2 * math.pi)
    bright_add = int(BREATH_AMP * breath)
    cur_color = tuple(min(255, LYRIC_WHITE[i] + bright_add) for i in range(3))

    for slot, real_i in enumerate(range(start_i, end_i)):
        lt, text = lyric_lines[real_i]
        row_y = list_top + slot * LINE_H

        # 行出现的淡入 alpha（新行从 0 渐显）
        age = t - lt                          # 此行已显示多久（可负）
        if real_i > cur_idx:                  # 未来行，不显示
            fade_alpha = 0.0
        elif real_i < cur_idx:                # 已完成行，全显
            fade_alpha = 1.0
        else:                                 # 当前行淡入
            fade_alpha = min(1.0, max(0.0, age / FADE_DUR)) if age >= 0 else 0.0

        if fade_alpha <= 0:
            continue

        # ── checkbox 弹性动画
        # checkbox 在该行打字完成后才勾上
        char_dur   = len(text) / CHARS_PER_SEC
        done_time  = lt + char_dur            # 打字完成时刻
        if real_i < cur_idx:
            ck_prog = 1.0
        elif real_i == cur_idx:
            bounce_age = t - done_time
            ck_prog = min(1.0, max(0.0, bounce_age / BOUNCE_DUR)) if bounce_age >= 0 else 0.0
        else:
            ck_prog = 0.0

        # checkbox 圆心（稍微往下偏移 8px）
        cbx = MARGIN_L + BULLET_R
        cby = row_y + LINE_H // 2 + 8

        # 用 alpha 模拟淡入（简单：用灰混背景色）
        def _fade_color(color, alpha):
            return tuple(int(BG_COLOR[i] + (color[i] - BG_COLOR[i]) * alpha) for i in range(3))

        # 绘制 checkbox
        if ck_prog <= 0:
            outline_c = _fade_color((99, 99, 102), fade_alpha)
            draw.ellipse([cbx-BULLET_R, cby-BULLET_R, cbx+BULLET_R, cby+BULLET_R],
                         outline=outline_c, width=3)
        else:
            scale = _easeOutElastic(ck_prog)
            er    = max(1, int(BULLET_R * scale))
            blue  = _fade_color(IOS_BLUE, fade_alpha * min(1.0, ck_prog))
            draw.ellipse([cbx-er, cby-er, cbx+er, cby+er], fill=blue)
            if ck_prog > 0.4:
                wa = min(1.0, (ck_prog - 0.4) / 0.3) * fade_alpha
                wc = int(255 * wa)
                lw = max(3, int(er * 0.26))
                p1 = (cbx - er*0.40, cby + er*0.04)
                p2 = (cbx - er*0.08, cby + er*0.38)
                p3 = (cbx + er*0.44, cby - er*0.30)
                draw.line([p1, p2], fill=(wc,wc,wc), width=lw)
                draw.line([p2, p3], fill=(wc,wc,wc), width=lw)

        # ── 歌词文字
        txt_x  = MARGIN_L + BULLET_R * 2 + 24
        txt_y  = row_y + (LINE_H - LYRIC_FS) // 2

        if real_i < cur_idx:
            # 已完成行：全文显示，普通白
            c = _fade_color(LYRIC_WHITE, fade_alpha)
            draw.text((txt_x, txt_y), text, font=fonts['lyric'], fill=c)

        elif real_i == cur_idx:
            # 当前行：打字机逐字 + 光标
            age_clamped = max(0.0, age)
            n_shown = min(len(text), int(age_clamped * CHARS_PER_SEC))
            shown   = text[:n_shown]

            # 呼吸高亮色
            c = _fade_color(cur_color, fade_alpha)
            draw.text((txt_x, txt_y), shown, font=fonts['lyric_bold'], fill=c)

            # 光标（打字未完成时显示）
            if n_shown < len(text):
                typed_w = int(draw.textlength(shown, font=fonts['lyric_bold']))
                cursor_x = txt_x + typed_w + 4
                # 光标闪烁
                blink = math.sin(t * CURSOR_BLINK_HZ * 2 * math.pi)
                if blink > -0.3:   # 大部分时间显示，少量时间隐藏
                    cursor_alpha = fade_alpha * min(1.0, (blink + 1) / 2 + 0.5)
                    cc = _fade_color(IOS_BLUE, cursor_alpha)
                    draw.text((cursor_x, txt_y), "|", font=fonts['lyric_bold'], fill=cc)

        else:
            # 未来行：灰色占位（淡入）
            c = _fade_color(LYRIC_DIM, fade_alpha)
            draw.text((txt_x, txt_y), text, font=fonts['lyric'], fill=c)

    # ── 底部进度条
    prog_y = VIDEO_H - 120
    _sep(draw, prog_y - 30)
    draw.text((MARGIN_L, prog_y + 18), _fmt(t), font=fonts['date'], fill=HEADER_FG)
    dw = draw.textlength(_fmt(dur), font=fonts['date'])
    draw.text((VIDEO_W - MARGIN_R - dw, prog_y + 18), _fmt(dur), font=fonts['date'], fill=HEADER_FG)
    _progress_bar(draw, t, dur, prog_y, h=8)

    return img


# ── 主函数 ────────────────────────────────────────────────────────────────────
def iphone_lyric_video_tiktok(song_name: str) -> str:
    root       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mp3_path   = os.path.join(root, "input", f"{song_name}.mp3")
    lrc_path   = os.path.join(root, "output", "lrcCorrection", f"{song_name}.lrc")
    out_dir    = os.path.join(root, "output", "vedio")
    video_path = os.path.join(out_dir, f"{song_name}_tiktok.mp4")

    if not os.path.exists(mp3_path):  raise FileNotFoundError(f"❌ 音频不存在: {mp3_path}")
    if not os.path.exists(lrc_path):  raise FileNotFoundError(f"❌ 歌词不存在: {lrc_path}")
    os.makedirs(out_dir, exist_ok=True)

    print("📖 解析歌词...")
    meta, lyric_lines = _parse_lrc(lrc_path)
    title  = meta.get('ti', '') or song_name
    artist = meta.get('ar', '')
    song_title = f"《{title}》"
    print(f"🎵 {song_title}  {artist}  共 {len(lyric_lines)} 行")

    print("🔤 加载字体...")
    fonts = {
        'header'    : _load_font(HEADER_FS),
        'title'     : _load_font(TITLE_FS, bold=True),
        'subtitle'  : _load_font(SUBTITLE_FS),
        'lyric'     : _load_font(LYRIC_FS),
        'lyric_bold': _load_font(LYRIC_FS, bold=True),
        'date'      : _load_font(DATE_FS),
    }

    print("🎧 加载音频...")
    audio = AudioFileClip(mp3_path)
    dur   = audio.duration

    def make_frame(t):
        return np.array(_draw_frame(t, dur, song_title, artist, lyric_lines, fonts))

    print(f"🎬 渲染中 ({VIDEO_W}x{VIDEO_H} @{FPS}fps)...")
    clip = VideoClip(make_frame, duration=dur).set_audio(audio)
    clip.write_videofile(
        video_path, fps=FPS, codec='libx264', audio_codec='aac',
        preset='fast', ffmpeg_params=['-crf', '18'], logger='bar'
    )
    print(f"✅ 完成: {os.path.abspath(video_path)}")
    return os.path.abspath(video_path)


# ── 调参速查表 ────────────────────────────────────────────────────────────────
"""
CHARS_PER_SEC   打字速度，越大越快（默认10，抒情建议7~9，快歌可到14）
CURSOR_BLINK_HZ 光标闪烁频率（默认2，视觉效果够了不需要改）
BREATH_AMP      呼吸高亮强度（默认18，调大更明显，调0关闭）
BREATH_HZ       呼吸频率（默认1.2，抒情建议0.8~1.0）
BOUNCE_DUR      checkbox弹性动画时长（默认0.35秒，越短越脆）
FADE_DUR        新行淡入时长（默认0.25秒）
LINE_H          行高（默认92px，字多可调大）
"""

if __name__ == "__main__":
    iphone_lyric_video_tiktok("知我")
