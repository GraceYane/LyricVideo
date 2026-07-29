#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import gc
import os, re, math, shutil, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from moviepy.editor import VideoClip, AudioFileClip

# ════════════════════════════════════════════════════════
#  1. 路径自动对齐
# ════════════════════════════════════════════════════════
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_abs_path(*rel_path):
    return os.path.join(PROJECT_ROOT, *rel_path)


# ════════════════════════════════════════════════════════
#  全局默认配置
# ════════════════════════════════════════════════════════
VIDEO_W, VIDEO_H, FPS = 1920, 1080, 55

# 默认图片名称
DEFAULT_BG_NAME = "jianlaihong"
DEFAULT_COVER_NAME = "jianlaihong"

# ── 字体路径配置 ──
CUSTOM_FONT_TITLE = get_abs_path("resources", "fonts", "msyh.ttc")
CUSTOM_FONT_ARTIST = get_abs_path("resources", "fonts", "shoujin.TTF")
CUSTOM_FONT_LYRIC = get_abs_path("resources", "fonts", "msyh.ttc")

DEBUG_DURATION = 45
DEBUG_MODE = False

# ── 字号及布局配置 ──
FS_CURRENT = 52
FS_NORMAL = 42
FS_TITLE = 60
FS_ARTIST = 52

COVER_CX, COVER_CY, COVER_R = 320, 600, 200
COVER_BORDER = 18  # ★ 已调回 18
RING_DOTS, RING_DOT_R, RING_GAP = 80, 4.5, 14
COVER_ROT_DEG_PER_SEC = 3.0

RING_PULSE_FREQ = 0.5
RING_PULSE_MIN_ALPHA, RING_PULSE_MAX_ALPHA = 80, 255

BG_SCALE_FACTOR = 1.05
BG_SWAY_FREQ_X, BG_SWAY_FREQ_Y = 0.25, 0.18
BG_SWAY_AMP_X, BG_SWAY_AMP_Y = 10.0, 8.0

TITLE_X, TITLE_Y = 80, 90
ARTIST_X, ARTIST_SPACING = 140, 30
LYRIC_X, LYRIC_CURRENT_Y = 860, 320
LINE_H = 92
LINES_ABOVE, LINES_BELOW = 2, 6

C_CURRENT = (255, 255, 255)
# C_ABOVE = (140, 140, 165)
# C_BELOW = (140, 140, 160)
C_ABOVE = (130, 130, 150)
C_BELOW = (130, 130, 150)
C_TITLE = (255, 255, 255)
C_ARTIST = (185, 185, 205)

# 图片背景
# BG_OVERLAY = 135
BG_OVERLAY = 65


SCROLL_DURATION = 0.32


# ════════════════════════════════════════════════════════
#  工具函数
# ════════════════════════════════════════════════════════
def _load_font(size: int, bold: bool = False, custom_path: str = None):
    size = int(size)
    if custom_path and os.path.exists(custom_path):
        try:
            return ImageFont.truetype(custom_path, size)
        except Exception as e:
            print(f"⚠️  无法加载字体 {custom_path}: {e}")

    candidates = [r"C:\Windows\Fonts\msyh.ttc", "/System/Library/Fonts/PingFang.ttc"]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


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


def _find_image(folder: str, name_hint: str = None):
    exts = [".jpg", ".jpeg", ".png", ".webp", ".bmp"]
    folder = Path(folder)
    if not folder.exists(): return None
    if name_hint:
        for ext in exts:
            p = folder / (name_hint + ext)
            if p.exists(): return str(p)
    return None


def _ease_out_cubic(t: float) -> float:
    return 1 - (1 - max(0.0, min(1.0, t))) ** 3


def _make_cover_frames(cover_src: Image.Image, duration: float, fps: int) -> list:
    total = int(duration * fps) + 1
    d = COVER_R * 2
    base = cover_src.resize((d, d), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (d, d), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d, d), fill=255)
    frames = []
    deg_per_frame = COVER_ROT_DEG_PER_SEC / fps
    for i in range(total):
        rotated = base.rotate(-i * deg_per_frame, resample=Image.BICUBIC, expand=False)
        result = Image.new("RGBA", (d, d), (0, 0, 0, 0))
        result.paste(rotated, mask=mask)
        frames.append(result)
    return frames


def _draw_text(draw, x, y, text, font, color, alpha=255):
    r, g, b = color[:3]
    draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, min(120, alpha // 2)))
    draw.text((x, y), text, font=font, fill=(r, g, b, alpha))


def _paste_cover(frame: Image.Image, cover_circle: Image.Image):
    cx, cy, r = COVER_CX, COVER_CY, COVER_R
    bw = COVER_BORDER
    bd = (r + bw) * 2
    border = Image.new("RGBA", (bd, bd), (0, 0, 0, 0))
    bmask = Image.new("L", (bd, bd), 0)
    ImageDraw.Draw(bmask).ellipse((0, 0, bd, bd), fill=255)
    # 保持白色透明边框
    border.paste(Image.new("RGBA", (bd, bd), (0, 0, 0, 255)), mask=bmask)
    frame.paste(border, (cx - r - bw, cy - r - bw), border)
    frame.paste(cover_circle, (cx - r, cy - r), cover_circle)


def _draw_ring_dots(layer: Image.Image, t: float):
    draw = ImageDraw.Draw(layer)
    cx, cy, r = COVER_CX, COVER_CY, COVER_R
    dist = r + COVER_BORDER + RING_GAP
    pulse = math.sin(t * RING_PULSE_FREQ * 2 * math.pi)
    alpha = int((RING_PULSE_MAX_ALPHA - RING_PULSE_MIN_ALPHA) / 2 * (pulse + 1) + RING_PULSE_MIN_ALPHA)
    for i in range(RING_DOTS):
        angle = 2 * math.pi * i / RING_DOTS
        x, y = cx + dist * math.cos(angle), cy + dist * math.sin(angle)
        draw.ellipse((x - RING_DOT_R, y - RING_DOT_R, x + RING_DOT_R, y + RING_DOT_R), fill=(255, 255, 255, alpha))


def _render_frame(t, bg_scaled, cover_frames, lyrics, song_title, artist, fonts):
    sway_x = int(round(math.sin(t * BG_SWAY_FREQ_X * 2 * math.pi) * BG_SWAY_AMP_X))
    sway_y = int(round(math.cos(t * BG_SWAY_FREQ_Y * 2 * math.pi) * BG_SWAY_AMP_Y))
    sw, sh = bg_scaled.size
    cx_crop = max(0, min((sw - VIDEO_W) // 2 + sway_x, sw - VIDEO_W))
    cy_crop = max(0, min((sh - VIDEO_H) // 2 + sway_y, sh - VIDEO_H))
    frame = bg_scaled.crop((cx_crop, cy_crop, cx_crop + VIDEO_W, cy_crop + VIDEO_H)).convert("RGBA")

    frame = Image.alpha_composite(frame, Image.new("RGBA", frame.size, (0, 0, 0, BG_OVERLAY)))
    _paste_cover(frame, cover_frames[min(int(t * FPS), len(cover_frames) - 1)])

    ring_layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    _draw_ring_dots(ring_layer, t)
    frame = Image.alpha_composite(frame, ring_layer)

    draw = ImageDraw.Draw(frame)
    _draw_text(draw, TITLE_X, TITLE_Y, f"【{song_title}】", fonts["title"], C_TITLE)
    if artist:
        _draw_text(draw, ARTIST_X, TITLE_Y + FS_TITLE + ARTIST_SPACING, artist, fonts["artist"], C_ARTIST)

    cur = -1
    for i, (ts, _) in enumerate(lyrics):
        if ts <= t: cur = i

    if cur == -1:
        scroll_offset, top_offset = 0, 0
    else:
        scroll_offset = LINE_H * (1.0 - _ease_out_cubic((t - lyrics[cur][0]) / SCROLL_DURATION))
        top_offset = max(0, LINES_ABOVE - cur) * LINE_H

    display_cur = max(cur, 0)
    for rel in range(-LINES_ABOVE, LINES_BELOW + 1):
        idx = display_cur + rel
        if idx < 0 or idx >= len(lyrics): continue
        y = int(LYRIC_CURRENT_Y - top_offset + rel * LINE_H + scroll_offset)
        is_current = (rel == 0 and cur >= 0)
        font = fonts["current"] if is_current else fonts["normal"]
        color = C_CURRENT if is_current else (C_ABOVE if rel < 0 else C_BELOW)
        alpha = 255 if is_current else max(0, int(200 * (1.0 - abs(rel) * 0.45))) if rel < 0 else max(0, int(150 * (
                1.0 - (rel - 1) * 0.13)))
        if alpha > 0:
            _draw_text(draw, LYRIC_X, y, lyrics[idx][1], font, color, alpha)

    return np.array(frame.convert("RGB"))


# ════════════════════════════════════════════════════════
#  🎯 主封装函数
# ════════════════════════════════════════════════════════
def generate_lyric_video(song_name: str,
                         artist_name: str = "",
                         bg_name: str = None,
                         cover_name: str = None,
                         font_paths: dict = None) -> str:
    target_bg = bg_name if bg_name else DEFAULT_BG_NAME
    target_cover = cover_name if cover_name else target_bg

    mp3_path = get_abs_path("input", f"{song_name}.mp3")
    lrc_path = get_abs_path("output", "lrcCorrection", f"{song_name}.lrc")
    img_dir = get_abs_path("resources", "imgs")
    out_dir = get_abs_path("output", "vedio")
    video_path = os.path.join(out_dir, f"{song_name}.mp4")
    os.makedirs(out_dir, exist_ok=True)

    fp = font_paths or {}
    fonts = {
        "current": _load_font(FS_CURRENT, bold=True, custom_path=fp.get("lyric", CUSTOM_FONT_LYRIC)),
        "normal": _load_font(FS_NORMAL, custom_path=fp.get("lyric", CUSTOM_FONT_LYRIC)),
        "title": _load_font(FS_TITLE, bold=True, custom_path=fp.get("title", CUSTOM_FONT_TITLE)),
        "artist": _load_font(FS_ARTIST, custom_path=fp.get("artist", CUSTOM_FONT_ARTIST)),
    }

    _tmp_mp3 = None
    if not all(ord(c) < 128 for c in mp3_path):
        _tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        _tmp.close()
        shutil.copy2(mp3_path, _tmp.name)
        _tmp_mp3 = _tmp.name

    audio = AudioFileClip(_tmp_mp3 if _tmp_mp3 else mp3_path)

    meta, lyrics = _parse_lrc(lrc_path)
    title = meta.get("ti", song_name)
    artist = artist_name or meta.get("ar", "")

    bg_p = _find_image(img_dir, target_bg)
    bg_full = Image.open(bg_p).resize((VIDEO_W, VIDEO_H), Image.LANCZOS) if bg_p else Image.new("RGB",
                                                                                                (VIDEO_W, VIDEO_H),
                                                                                                (20, 20, 30))
    bg_scaled = bg_full.resize((int(VIDEO_W * BG_SCALE_FACTOR), int(VIDEO_H * BG_SCALE_FACTOR)), Image.LANCZOS).convert(
        "RGBA")

    cp = _find_image(img_dir, target_cover)
    cover_src = Image.open(cp if cp else (bg_p if bg_p else None)).convert("RGB")
    w, h = cover_src.size
    sq = min(w, h)
    cover_src = cover_src.crop(((w - sq) // 2, (h - sq) // 2, (w + sq) // 2, (h + sq) // 2))
    cover_frames = _make_cover_frames(cover_src, audio.duration, FPS)

    render_dur = DEBUG_DURATION if DEBUG_MODE else audio.duration

    video = VideoClip(lambda t: _render_frame(t, bg_scaled, cover_frames, lyrics, title, artist, fonts),
                      duration=render_dur)
    video = video.set_audio(audio.subclip(0, render_dur))

    _tmp_v = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name

    try:
        video.write_videofile(_tmp_v, fps=FPS, codec="libx264", audio_codec="aac", preset="fast",
                              ffmpeg_params=["-crf", "18"])

        # ★ 关键：手动关闭句柄，防止 Windows 上的 PermissionError
        video.close()
        audio.close()

        if os.path.exists(video_path):
            os.remove(video_path)
        shutil.move(_tmp_v, video_path)

    finally:
        if _tmp_mp3 and os.path.exists(_tmp_mp3):
            try:
                os.remove(_tmp_mp3)
            except:
                pass
        if os.path.exists(_tmp_v):
            try:
                os.remove(_tmp_v)
            except:
                pass

    print(f"✅ 完成渲染: {video_path}")
    return video_path


# ════════════════════════════════════════════════════════
#  执行入口
# ════════════════════════════════════════════════════════
if __name__ == "__main__":
    ["江南", "可惜没如果", "关键词", "醉赤壁", "输了你赢了世界又如何", "茉莉雨"]
    song_list = ["阿楚姑娘", "月下煮茶", "十年人间", "想你和我们的以后"]
    # song_list = ["颜色", "春", "广东爱情故事", "这叫爱", "吹梦到西洲", "琵琶行", "人生路漫漫"]

    songs = [
        # ("阿楚姑娘", "倉木麻衣","time") , # time.jpg
        # ("月下煮茶", "陈佳", "zhucha"),
        # ("十年人间", "李常超", "biji"),
        ("那是你离开了北京的生活", "XueZhiQian", "beijing"),
        # ("想你和我们的以后", "苏运莹", "huayuan"),

        # ("梦回还", "呦猫UNEKO", "menghui"),
        # ("天行九歌", "霍尊", "jiuge"),
        # ("醉赤壁", "林俊杰", "yanshen"),
        # ("Time after time", "仓木麻衣", "timeAfter"),
        # ("输了你赢了世界又如何", "林俊杰", "shuni"),
        # ("茉莉雨", "林俊杰", "moni"),
        # ("陪你去流浪", "XueZhiQian", "liulang"),  # chuxian
    ]


    # songs = [
    #     # 最佳歌手
    #     # ("渡月橋", "倉木麻衣","timeAfter") , # time.jpg
    #     ("答案", "冒海飞 x 徐丽东", "daan"),
    #     # ("劫", "音频怪物", "dagu"),
    #     #  ("海屿你", "马也_Crabbit", "haiyuni"),
    #     # ("别错过", "程佳佳", "bg2"),
    #     ("想自由", "林宥嘉", "xiangziyou"),
    #     ("海屿你", "马也_Crabbit", "haiyuni"),
    #     ("雨爱", "杨丞琳", "yuai"),
    #     ("一样的月光", "徐佳莹", "yiyangyue"),
    #     ("入海", "毛不易", "ruHai"),
    #     ("出现又离开", "梁博", "chuxian"),  # chuxian
    # ]
    # songs = [
    #     # ("知我", "国风堂&哦漏", "jianlaihong")
    #     # ("世界上的另一个我", "阿肆/郭采洁", "shijie"),
    #     # ("残酷月光", "林宥嘉", "yueguang"),
    #     # # 最佳歌手
    #     # # ("渡月橋", "倉木麻衣","time") , # time.jpg
    #     # ("我怀念的", "孙燕姿", "wohuainian"),
    #     # ("颜色", "Gareth.T", "yanse"),
    #     # # ("劫", "音频怪物", "dagu"),
    #     # #  ("海屿你", "马也_Crabbit", "haiyuni"),
    #     # # ("别错过", "程佳佳", "bg2"),
    #     # ("春", "陈文非", "chun"),
    #     # ("广东爱情故事", "广东雨神", "guangdong"),
    #     # ("这叫爱", "BY2", "zhejiaoai"),
    #     # ("吹梦到西洲", "黄诗扶x妖扬", "chuimeng"),
    #     # ("琵琶行", "奇然 x 沈谧仁", "pipa"),
    #     # ("人生路漫漫", "岳云鹏", "rensheng"),  # chuxian
    #     # ("出现又离开", "梁博", "chuxian")
    # ]

    for s in songs:
        try:
            generate_lyric_video(*s)
        except Exception as e:
            print(f"❌ 歌曲 {s[0]} 渲染失败: {e}")
        finally:
            gc.collect()