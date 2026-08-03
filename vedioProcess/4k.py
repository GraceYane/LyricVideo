#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import gc
import os, re, math, shutil, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from moviepy.editor import VideoClip, AudioFileClip
from sympy import true

# ════════════════════════════════════════════════════════
#  1. 路径自动对齐
# ════════════════════════════════════════════════════════
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_abs_path(*rel_path):
    return os.path.join(PROJECT_ROOT, *rel_path)


# ════════════════════════════════════════════════════════
#  全局默认配置  ★ 4K (3840×2160) 版本
# ════════════════════════════════════════════════════════
SCALE = 2

VIDEO_W = 3840
VIDEO_H = 2160
FPS = 55

DEFAULT_BG_NAME = "jianlaihong"
DEFAULT_COVER_NAME = "jianlaihong"

CUSTOM_FONT_TITLE = get_abs_path("resources", "fonts", "msyh.ttc")
# CUSTOM_FONT_TITLE = get_abs_path("resources", "fonts", "3.ttf")
CUSTOM_FONT_ARTIST = get_abs_path("resources", "fonts", "shoujin.TTF")
CUSTOM_FONT_LYRIC = get_abs_path("resources", "fonts", "msyh.ttc")
# CUSTOM_FONT_LYRIC = get_abs_path("resources", "fonts", "4.ttf")

DEBUG_DURATION = 0.04
DEBUG_MODE = False

FS_CURRENT = 52 * SCALE
FS_NORMAL = 42 * SCALE
# FS_CURRENT = 68 * SCALE
# FS_NORMAL = 52 * SCALE
FS_TITLE = 80 * SCALE
FS_TITLE = 74 * SCALE
FS_ARTIST = 52 * SCALE

COVER_CX, COVER_CY, COVER_R = 320 * SCALE, 600 * SCALE, 200 * SCALE
COVER_BORDER = 18 * SCALE
RING_DOTS = 80
RING_DOT_R = 4.5 * SCALE
RING_GAP = 14 * SCALE
COVER_ROT_DEG_PER_SEC = 3.0

RING_PULSE_FREQ = 0.5
RING_PULSE_MIN_ALPHA = 80
RING_PULSE_MAX_ALPHA = 255

BG_SCALE_FACTOR = 1.05
BG_SWAY_FREQ_X, BG_SWAY_FREQ_Y = 0.25, 0.18
BG_SWAY_AMP_X = 10.0 * SCALE
BG_SWAY_AMP_Y = 8.0 * SCALE

TITLE_X, TITLE_Y = 80 * SCALE, 90 * SCALE
ARTIST_X, ARTIST_SPACING = 140 * SCALE, 30 * SCALE
LYRIC_X, LYRIC_CURRENT_Y = 860 * SCALE, 320 * SCALE
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


def _draw_text(draw, x, y, text, font, color, alpha=255):
    r, g, b = color[:3]
    offset = 2 * SCALE
    draw.text((x + offset, y + offset), text, font=font, fill=(0, 0, 0, min(120, alpha // 2)))
    draw.text((x, y), text, font=font, fill=(r, g, b, alpha))


def _paste_cover(frame: Image.Image, cover_base: Image.Image, t: float):
    cx, cy, r = COVER_CX, COVER_CY, COVER_R
    bw = COVER_BORDER
    bd = (r + bw) * 2

    current_deg = (t * COVER_ROT_DEG_PER_SEC) % 360
    rotated = cover_base.rotate(-current_deg, resample=Image.BICUBIC, expand=False)

    d = r * 2
    mask = Image.new("L", (d, d), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d, d), fill=255)
    cover_circle = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    cover_circle.paste(rotated, mask=mask)

    border = Image.new("RGBA", (bd, bd), (0, 0, 0, 0))
    bmask = Image.new("L", (bd, bd), 0)
    ImageDraw.Draw(bmask).ellipse((0, 0, bd, bd), fill=255)
    border.paste(Image.new("RGBA", (bd, bd), (0, 0, 0, 255)), mask=bmask)

    frame.paste(border, (cx - r - bw, cy - r - bw), border)
    frame.paste(cover_circle, (cx - r, cy - r), cover_circle)

    mask.close()
    cover_circle.close()
    border.close()
    bmask.close()
    rotated.close()


def _draw_ring_dots(layer: Image.Image, t: float):
    draw = ImageDraw.Draw(layer)
    cx, cy, r = COVER_CX, COVER_CY, COVER_R
    dist = r + COVER_BORDER + RING_GAP
    pulse = math.sin(t * RING_PULSE_FREQ * 2 * math.pi)
    alpha = int((RING_PULSE_MAX_ALPHA - RING_PULSE_MIN_ALPHA) / 2 * (pulse + 1) + RING_PULSE_MIN_ALPHA)
    for i in range(RING_DOTS):
        angle = 2 * math.pi * i / RING_DOTS
        x = cx + dist * math.cos(angle)
        y = cy + dist * math.sin(angle)
        draw.ellipse(
            (x - RING_DOT_R, y - RING_DOT_R, x + RING_DOT_R, y + RING_DOT_R),
            fill=(255, 255, 255, alpha)
        )


def _render_frame(t, bg_scaled, cover_base, lyrics, song_title, artist, fonts):
    sway_x = int(round(math.sin(t * BG_SWAY_FREQ_X * 2 * math.pi) * BG_SWAY_AMP_X))
    sway_y = int(round(math.cos(t * BG_SWAY_FREQ_Y * 2 * math.pi) * BG_SWAY_AMP_Y))
    sw, sh = bg_scaled.size
    cx_crop = max(0, min((sw - VIDEO_W) // 2 + sway_x, sw - VIDEO_W))
    cy_crop = max(0, min((sh - VIDEO_H) // 2 + sway_y, sh - VIDEO_H))

    frame = bg_scaled.crop((cx_crop, cy_crop, cx_crop + VIDEO_W, cy_crop + VIDEO_H)).convert("RGBA")
    frame = Image.alpha_composite(frame, Image.new("RGBA", frame.size, (0, 0, 0, BG_OVERLAY)))

    _paste_cover(frame, cover_base, t)

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
        alpha = (255 if is_current
                 else max(0, int(200 * (1.0 - abs(rel) * 0.45))) if rel < 0
        else max(0, int(150 * (1.0 - (rel - 1) * 0.13))))
        if alpha > 0:
            _draw_text(draw, LYRIC_X, y, lyrics[idx][1], font, color, alpha)

    ret_array = np.array(frame.convert("RGB"))

    frame.close()
    ring_layer.close()

    return ret_array


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

    # ──── 动态探测音频格式 ────
    audio_ext = ".mp3"
    if os.path.exists(get_abs_path("input", f"{song_name}.flac")):
        audio_ext = ".flac"
    elif os.path.exists(get_abs_path("input", f"{song_name}.wav")):
        audio_ext = ".wav"
    elif not os.path.exists(get_abs_path("input", f"{song_name}.mp3")):
        raise FileNotFoundError(f"❌ 找不到歌曲音频文件：{song_name} (.flac/.mp3/.wav)")

    audio_path = get_abs_path("input", f"{song_name}{audio_ext}")
    lrc_path = get_abs_path("output", "lrcCorrection", f"{song_name}.lrc")

    #薛之谦定制
    # audio_ext = ".mp3"
    # if os.path.exists(get_abs_path("input", "XueZhiQian", f"{song_name}.flac")):
    #     audio_ext = ".flac"
    # elif os.path.exists(get_abs_path("input", "XueZhiQian", f"{song_name}.wav")):
    #     audio_ext = ".wav"
    # elif not os.path.exists(get_abs_path("input", "XueZhiQian", f"{song_name}.mp3")):
    #     raise FileNotFoundError(f"❌ 找不到歌曲音频文件：{song_name} (.flac/.mp3/.wav)")
    #
    # audio_path = get_abs_path("input", "XueZhiQian", f"{song_name}{audio_ext}")
    # lrc_path = get_abs_path("output", "lrcCorrection", "XueZhiQian", f"{song_name}.lrc")

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

    # ──── 动态处理中文路径与对应的临时文件 ────
    _tmp_audio_path = None
    if not all(ord(c) < 128 for c in audio_path):
        _tmp = tempfile.NamedTemporaryFile(suffix=audio_ext, delete=False)
        _tmp.close()
        shutil.copy2(audio_path, _tmp.name)
        _tmp_audio_path = _tmp.name

    audio = AudioFileClip(_tmp_audio_path if _tmp_audio_path else audio_path)

    meta, lyrics = _parse_lrc(lrc_path)
    title = meta.get("ti", song_name)
    artist = artist_name or meta.get("ar", "")

    # ──── 背景图动态适配与裁剪部分 ────
    bg_p = _find_image(img_dir, target_bg)
    if bg_p:
        with Image.open(bg_p) as img_raw:
            orig_w, orig_h = img_raw.size
            target_aspect = VIDEO_W / VIDEO_H
            orig_aspect = orig_w / orig_h

            if orig_aspect > target_aspect:
                new_w = int(orig_h * target_aspect)
                left = (orig_w - new_w) // 2
                crop_box = (left, 0, left + new_w, orig_h)
            else:
                new_h = int(orig_w / target_aspect)
                top = (orig_h - new_h) // 2
                crop_box = (0, top, orig_w, top + new_h)

            bg_full = img_raw.crop(crop_box).resize((VIDEO_W, VIDEO_H), Image.LANCZOS)
    else:
        bg_full = Image.new("RGB", (VIDEO_W, VIDEO_H), (20, 20, 30))

    bg_scaled = bg_full.resize(
        (int(VIDEO_W * BG_SCALE_FACTOR), int(VIDEO_H * BG_SCALE_FACTOR)),
        Image.LANCZOS
    ).convert("RGBA")
    bg_full.close()

    # ──── 封面图逻辑 ────
    cp = _find_image(img_dir, target_cover)
    cover_src = Image.open(cp if cp else (bg_p if bg_p else None)).convert("RGB")
    w, h = cover_src.size
    sq = min(w, h)
    cover_src = cover_src.crop(((w - sq) // 2, (h - sq) // 2, (w + sq) // 2, (h + sq) // 2))

    d = COVER_R * 2
    cover_base = cover_src.resize((d, d), Image.LANCZOS).convert("RGBA")
    cover_src.close()

    render_dur = DEBUG_DURATION if DEBUG_MODE else audio.duration

    video = VideoClip(
        lambda t: _render_frame(t, bg_scaled, cover_base, lyrics, title, artist, fonts),
        duration=render_dur
    )
    video = video.set_audio(audio.subclip(0, render_dur))

    _tmp_v = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name

    try:
        # ──── ★ B站黄金优化：统一采用主流兼容的高规格 AAC 编码，强制锁死 320k 超高码率 ────
        v_audio_codec = "aac"

        video.write_videofile(
            _tmp_v, fps=FPS, codec="libx264", audio_codec=v_audio_codec, preset="fast",
            ffmpeg_params=["-crf", "18", "-threads", "4", "-b:a", "320k"]
        )

        video.close()
        audio.close()

        if os.path.exists(video_path):
            os.remove(video_path)
        shutil.move(_tmp_v, video_path)
    finally:
        bg_scaled.close()
        cover_base.close()

        if _tmp_audio_path and os.path.exists(_tmp_audio_path):
            try:
                os.remove(_tmp_audio_path)
            except:
                pass
        if os.path.exists(_tmp_v):
            try:
                os.remove(_tmp_v)
            except:
                pass

    print(f"✅ B站专属渲染完成 (4K录制标准): {video_path}")
    return video_path


# ════════════════════════════════════════════════════════
#  执行入口
# ════════════════════════════════════════════════════════
if __name__ == "__main__":
    # 这里把你之前删掉或者想跑的歌曲都在这里补全
    # songs = [
    #     # ("春庭雪", "等什么君", "chuntingxue"),
    #     # ("谪仙", "伊格赛听&叶里", "zhexian"),
    #     # ("十年人间", "李常超", "shinianrenjian1"),
    #     # ("难却", "平生不晚", "nanque2"),
    #     # ("答案", "杨坤&郭采洁 &叶里", "dnan"),
    #     # ("下雨了", "薛之谦", "xiayule"),
    #     ("来自天堂的魔鬼", "邓紫棋", "tiantang"),
    #     ("其实", "薛之谦", "qishi","qishi1"),
    #     # ("怪咖", "薛之谦", "guaika"),
    #     ("演员", "薛之谦", "yanyuan","qishi1"),
    #     # ("聊表心意", "薛之谦", "liaobiaoxinyi"),
    #     # ("肆无忌惮", "薛之谦", "siwujidan"),
    #     ("认真的雪", "薛之谦","yanyuan","qishi1"),
    #     # ("迟迟", "薛之谦", "chichi"),
    #     # ("金斧子银斧子", "薛之谦", "chichi"),
    #     ("霸王别姬", "薛之谦", "bawang","qishi1"),
    #
    #     # ("春庭雪", "等什么君", "chuntingxue"),
    #     # ("谪仙", "伊格赛听&叶里", "zhexian"),
    #     # ("十年人间", "李常超", "shinianrenjian1"),
    #     # ("难却", "平生不晚", "nanque2"),
    #     # ("答案", "杨坤&郭采洁 &叶里", "dnan"),
    #
    #
    #     ("一半", "薛之谦", "xiayule"),
    #     ("丑八怪", "薛之谦", "chichi"),
    #     ("你还要我怎样", "薛之谦", "chichi"),
    #     ("像风一样", "薛之谦", "xiayule"),
    #     ("刚刚好", "薛之谦", "chichi"),
    #     ("初学者", "薛之谦", "chichi"),
    #     ("动物世界", "薛之谦", "xiayule"),
    #     ("变废为宝", "薛之谦", "chichi"),
    #     ("可", "薛之谦", "chichi"),
    #     ("天外来物", "薛之谦", "xiayule"),
    #     ("小尖尖", "薛之谦", "chichi"),
    #     ("情书", "薛之谦", "chichi"),
    #
    #     ("念", "薛之谦", "xiayule"),
    #     ("意外", "薛之谦", "chichi"),
    #     ("我好像在哪见过你", "薛之谦", "chichi"),
    #     ("方圆几里", "薛之谦", "xiayule"),
    #     ("无数", "薛之谦", "chichi"),
    #     ("暧昧", "薛之谦", "chichi"),
    #
    #     ("最好", "薛之谦", "xiayule"),
    #     ("木偶人", "薛之谦", "chichi"),
    #     ("落城", "薛之谦", "chichi"),
    #     ("狐狸", "薛之谦", "xiayule"),
    #     ("男二号", "薛之谦", "chichi"),
    #     ("租购", "薛之谦", "chichi"),
    #
    #     ("绅士", "薛之谦", "xiayule"),
    #     ("违背的青春", "薛之谦", "chichi"),
    #     ("野心", "薛之谦", "chichi"),
    #
    #     ("等我回家", "薛之谦", "xiayule"),
    #     ("有没有", "薛之谦", "chichi"),
    #     ("友情提示", "薛之谦", "chichi"),
    #     ("为了遇见你", "薛之谦", "xiayule"),
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #     # ("顽疾", "薛之谦", "chichi"),
    #     # ("虞兮叹", "闻人听书", "yuxitan"),
    #     # ("莫问归期", "蒋雪儿", "fengcuiyu"),
    #     # ("江湖之间", "曹雨航", "jianghuzhijian"),
    #     # ("晚夜微雨问海棠", "镜予歌&喧笑&陈亦洺", "haitang"),
    #     # ("风催雨", "费戚戚", "fengcuiyu"),
    #     # ("望", "张碧晨&赵丽颖", "wang"),
    #     # ("浸春芜", " ", "fagnzhou"),
    #     # ("青衣", "琪大妈", "qingyi"), shinianrenjian1
    #     # ("何以歌", "Aki阿杰", "heyige"),  # 改过了直接跑
    #     # ("春不晚", "冰洁", "chunbuwan"),
    #     # ("云与海", "阿YueYue", "yun1"),
    #     # ("十年人间", "李常超", "shinianrenjian1"),
    # ]

    songs = [
        # ("庙堂之外", "陈楚生", "miaotang"),
        # # ("一路生花", "温奕心", "yilushegnhua"),
        # ("云烟成雨", "房东的猫", "yunyanchengyu"),
        # ("像鱼", "王贰浪", "xiangyu"),
        # ("可不可以", "张紫豪", "kebukeyi"),
        # ("吻得太逼真", "张敬轩", "chengquan"),
        #  ("天亮以前说再见", "曲肖冰", "tianliangyiq"),
        # # ("忽而今夏", "汪苏泷", "huerjinxia"),
        #  ("把回忆拼好给你", "王贰浪", "huiyipinh"),
        ("夏天的风", "温岚", "yilushegnhua"),
        # ("无名的人", "毛不易", "wumingderen"),
        # ("时光洪流", "程响", "shiguanhongl"),

             ]
    for s in songs:
        try:
            generate_lyric_video(*s)
        except Exception as e:
            print(f"❌ 歌曲 {s[0]} 渲染失败: {e}")
        finally:
            gc.collect()



# #!/usr/bin/env python3
# # -*- coding: utf-8 -*-
# import gc
# import os, re, math, shutil, tempfile
# from pathlib import Path
# from PIL import Image, ImageDraw, ImageFont
# import numpy as np
# from moviepy.editor import VideoClip, AudioFileClip
#
# # ════════════════════════════════════════════════════════
# #  1. 路径自动对齐
# # ════════════════════════════════════════════════════════
# PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#
#
# def get_abs_path(*rel_path):
#     return os.path.join(PROJECT_ROOT, *rel_path)
#
#
# # ════════════════════════════════════════════════════════
# #  全局默认配置  ★ 4K (3840×2160) 版本
# # ════════════════════════════════════════════════════════
# SCALE = 2
#
# VIDEO_W = 3840
# VIDEO_H = 2160
# FPS = 55
#
# DEFAULT_BG_NAME = "jianlaihong"
# DEFAULT_COVER_NAME = "jianlaihong"
#
# CUSTOM_FONT_TITLE = get_abs_path("resources", "fonts", "msyh.ttc")
# CUSTOM_FONT_ARTIST = get_abs_path("resources", "fonts", "shoujin.TTF")
# CUSTOM_FONT_LYRIC = get_abs_path("resources", "fonts", "msyh.ttc")
#
# DEBUG_DURATION = 45
# DEBUG_MODE = False
#
# FS_CURRENT = 52 * SCALE
# FS_NORMAL = 42 * SCALE
# FS_TITLE = 80 * SCALE
# FS_ARTIST = 52 * SCALE
#
# COVER_CX, COVER_CY, COVER_R = 320 * SCALE, 600 * SCALE, 200 * SCALE
# COVER_BORDER = 18 * SCALE
# RING_DOTS = 80
# RING_DOT_R = 4.5 * SCALE
# RING_GAP = 14 * SCALE
# COVER_ROT_DEG_PER_SEC = 3.0
#
# RING_PULSE_FREQ = 0.5
# RING_PULSE_MIN_ALPHA = 80
# RING_PULSE_MAX_ALPHA = 255
#
# BG_SCALE_FACTOR = 1.05
# BG_SWAY_FREQ_X, BG_SWAY_FREQ_Y = 0.25, 0.18
# BG_SWAY_AMP_X = 10.0 * SCALE
# BG_SWAY_AMP_Y = 8.0 * SCALE
#
# TITLE_X, TITLE_Y = 80 * SCALE, 90 * SCALE
# ARTIST_X, ARTIST_SPACING = 140 * SCALE, 30 * SCALE
# LYRIC_X, LYRIC_CURRENT_Y = 860 * SCALE, 320 * SCALE
# LINE_H = 92 * SCALE
# LINES_ABOVE = 2
# LINES_BELOW = 6
#
# C_CURRENT = (255, 255, 255)
# C_ABOVE = (130, 130, 150)
# C_BELOW = (130, 130, 150)
# C_TITLE = (255, 255, 255)
# C_ARTIST = (185, 185, 205)
#
# BG_OVERLAY = 85
# SCROLL_DURATION = 0.32
#
#
# # ════════════════════════════════════════════════════════
# #  工具函数
# # ════════════════════════════════════════════════════════
# def _load_font(size: int, bold: bool = False, custom_path: str = None):
#     size = int(size)
#     if custom_path and os.path.exists(custom_path):
#         try:
#             return ImageFont.truetype(custom_path, size)
#         except Exception as e:
#             print(f"⚠️  无法加载字体 {custom_path}: {e}")
#
#     candidates = [r"C:\Windows\Fonts\msyh.ttc", "/System/Library/Fonts/PingFang.ttc"]
#     for p in candidates:
#         if os.path.exists(p):
#             return ImageFont.truetype(p, size)
#     return ImageFont.load_default()
#
#
# def _parse_lrc(lrc_path: str):
#     meta, lines = {}, []
#     time_pat = re.compile(r'\[(\d{2}):(\d{2})\.(\d{2,3})\]')
#     meta_pat = re.compile(r'\[(\w+):(.*)\]')
#     with open(lrc_path, encoding='utf-8', errors='replace') as f:
#         for raw in f:
#             raw = raw.strip()
#             if not raw: continue
#             m = meta_pat.match(raw)
#             if m and not time_pat.search(raw):
#                 meta[m.group(1).lower()] = m.group(2).strip()
#                 continue
#             times = time_pat.findall(raw)
#             text = time_pat.sub('', raw).strip()
#             if not text: continue
#             for mm, ss, ms in times:
#                 t = int(mm) * 60 + int(ss) + int(ms.ljust(3, '0')[:3]) / 1000.0
#                 lines.append((t, text))
#     lines.sort(key=lambda x: x[0])
#     return meta, lines
#
#
# def _find_image(folder: str, name_hint: str = None):
#     exts = [".jpg", ".jpeg", ".png", ".webp", ".bmp"]
#     folder = Path(folder)
#     if not folder.exists(): return None
#     if name_hint:
#         for ext in exts:
#             p = folder / (name_hint + ext)
#             if p.exists(): return str(p)
#     return None
#
#
# def _ease_out_cubic(t: float) -> float:
#     return 1 - (1 - max(0.0, min(1.0, t))) ** 3
#
#
# def _draw_text(draw, x, y, text, font, color, alpha=255):
#     r, g, b = color[:3]
#     offset = 2 * SCALE
#     draw.text((x + offset, y + offset), text, font=font, fill=(0, 0, 0, min(120, alpha // 2)))
#     draw.text((x, y), text, font=font, fill=(r, g, b, alpha))
#
#
# def _paste_cover(frame: Image.Image, cover_base: Image.Image, t: float):
#     cx, cy, r = COVER_CX, COVER_CY, COVER_R
#     bw = COVER_BORDER
#     bd = (r + bw) * 2
#
#     current_deg = (t * COVER_ROT_DEG_PER_SEC) % 360
#     rotated = cover_base.rotate(-current_deg, resample=Image.BICUBIC, expand=False)
#
#     d = r * 2
#     mask = Image.new("L", (d, d), 0)
#     ImageDraw.Draw(mask).ellipse((0, 0, d, d), fill=255)
#     cover_circle = Image.new("RGBA", (d, d), (0, 0, 0, 0))
#     cover_circle.paste(rotated, mask=mask)
#
#     border = Image.new("RGBA", (bd, bd), (0, 0, 0, 0))
#     bmask = Image.new("L", (bd, bd), 0)
#     ImageDraw.Draw(bmask).ellipse((0, 0, bd, bd), fill=255)
#     border.paste(Image.new("RGBA", (bd, bd), (0, 0, 0, 255)), mask=bmask)
#
#     frame.paste(border, (cx - r - bw, cy - r - bw), border)
#     frame.paste(cover_circle, (cx - r, cy - r), cover_circle)
#
#     mask.close()
#     cover_circle.close()
#     border.close()
#     bmask.close()
#     rotated.close()
#
#
# def _draw_ring_dots(layer: Image.Image, t: float):
#     draw = ImageDraw.Draw(layer)
#     cx, cy, r = COVER_CX, COVER_CY, COVER_R
#     dist = r + COVER_BORDER + RING_GAP
#     pulse = math.sin(t * RING_PULSE_FREQ * 2 * math.pi)
#     alpha = int((RING_PULSE_MAX_ALPHA - RING_PULSE_MIN_ALPHA) / 2 * (pulse + 1) + RING_PULSE_MIN_ALPHA)
#     for i in range(RING_DOTS):
#         angle = 2 * math.pi * i / RING_DOTS
#         x = cx + dist * math.cos(angle)
#         y = cy + dist * math.sin(angle)
#         draw.ellipse(
#             (x - RING_DOT_R, y - RING_DOT_R, x + RING_DOT_R, y + RING_DOT_R),
#             fill=(255, 255, 255, alpha)
#         )
#
#
# def _render_frame(t, bg_scaled, cover_base, lyrics, song_title, artist, fonts):
#     sway_x = int(round(math.sin(t * BG_SWAY_FREQ_X * 2 * math.pi) * BG_SWAY_AMP_X))
#     sway_y = int(round(math.cos(t * BG_SWAY_FREQ_Y * 2 * math.pi) * BG_SWAY_AMP_Y))
#     sw, sh = bg_scaled.size
#     cx_crop = max(0, min((sw - VIDEO_W) // 2 + sway_x, sw - VIDEO_W))
#     cy_crop = max(0, min((sh - VIDEO_H) // 2 + sway_y, sh - VIDEO_H))
#
#     frame = bg_scaled.crop((cx_crop, cy_crop, cx_crop + VIDEO_W, cy_crop + VIDEO_H)).convert("RGBA")
#     frame = Image.alpha_composite(frame, Image.new("RGBA", frame.size, (0, 0, 0, BG_OVERLAY)))
#
#     _paste_cover(frame, cover_base, t)
#
#     ring_layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
#     _draw_ring_dots(ring_layer, t)
#     frame = Image.alpha_composite(frame, ring_layer)
#
#     draw = ImageDraw.Draw(frame)
#     _draw_text(draw, TITLE_X, TITLE_Y, f"【{song_title}】", fonts["title"], C_TITLE)
#     if artist:
#         _draw_text(draw, ARTIST_X, TITLE_Y + FS_TITLE + ARTIST_SPACING, artist, fonts["artist"], C_ARTIST)
#
#     cur = -1
#     for i, (ts, _) in enumerate(lyrics):
#         if ts <= t: cur = i
#
#     if cur == -1:
#         scroll_offset, top_offset = 0, 0
#     else:
#         scroll_offset = LINE_H * (1.0 - _ease_out_cubic((t - lyrics[cur][0]) / SCROLL_DURATION))
#         top_offset = max(0, LINES_ABOVE - cur) * LINE_H
#
#     display_cur = max(cur, 0)
#     for rel in range(-LINES_ABOVE, LINES_BELOW + 1):
#         idx = display_cur + rel
#         if idx < 0 or idx >= len(lyrics): continue
#         y = int(LYRIC_CURRENT_Y - top_offset + rel * LINE_H + scroll_offset)
#         is_current = (rel == 0 and cur >= 0)
#         font = fonts["current"] if is_current else fonts["normal"]
#         color = C_CURRENT if is_current else (C_ABOVE if rel < 0 else C_BELOW)
#         alpha = (255 if is_current
#                  else max(0, int(200 * (1.0 - abs(rel) * 0.45))) if rel < 0
#         else max(0, int(150 * (1.0 - (rel - 1) * 0.13))))
#         if alpha > 0:
#             _draw_text(draw, LYRIC_X, y, lyrics[idx][1], font, color, alpha)
#
#     ret_array = np.array(frame.convert("RGB"))
#
#     frame.close()
#     ring_layer.close()
#
#     return ret_array
#
#
# # ════════════════════════════════════════════════════════
# #  🎯 主封装函数
# # ════════════════════════════════════════════════════════
# def generate_lyric_video(song_name: str,
#                          artist_name: str = "",
#                          bg_name: str = None,
#                          cover_name: str = None,
#                          font_paths: dict = None) -> str:
#     target_bg = bg_name if bg_name else DEFAULT_BG_NAME
#     target_cover = cover_name if cover_name else target_bg
#
#     mp3_path = get_abs_path("input", f"{song_name}.mp3")
#     lrc_path = get_abs_path("output", "lrcCorrection", f"{song_name}.lrc")
#     img_dir = get_abs_path("resources", "imgs")
#     out_dir = get_abs_path("output", "vedio")
#     video_path = os.path.join(out_dir, f"{song_name}.mp4")
#     os.makedirs(out_dir, exist_ok=True)
#
#     fp = font_paths or {}
#     fonts = {
#         "current": _load_font(FS_CURRENT, bold=True, custom_path=fp.get("lyric", CUSTOM_FONT_LYRIC)),
#         "normal": _load_font(FS_NORMAL, custom_path=fp.get("lyric", CUSTOM_FONT_LYRIC)),
#         "title": _load_font(FS_TITLE, bold=True, custom_path=fp.get("title", CUSTOM_FONT_TITLE)),
#         "artist": _load_font(FS_ARTIST, custom_path=fp.get("artist", CUSTOM_FONT_ARTIST)),
#     }
#
#     _tmp_mp3 = None
#     if not all(ord(c) < 128 for c in mp3_path):
#         _tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
#         _tmp.close()
#         shutil.copy2(mp3_path, _tmp.name)
#         _tmp_mp3 = _tmp.name
#
#     audio = AudioFileClip(_tmp_mp3 if _tmp_mp3 else mp3_path)
#
#     meta, lyrics = _parse_lrc(lrc_path)
#     title = meta.get("ti", song_name)
#     artist = artist_name or meta.get("ar", "")
#
#     # ──── ★ 背景图动态适配与裁剪部分 (核心修改) ────
#     bg_p = _find_image(img_dir, target_bg)
#     if bg_p:
#         with Image.open(bg_p) as img_raw:
#             orig_w, orig_h = img_raw.size
#             target_aspect = VIDEO_W / VIDEO_H  # 16:9 = 1.7778
#             orig_aspect = orig_w / orig_h
#
#             if orig_aspect > target_aspect:
#                 # 图片太宽，裁剪左右
#                 new_w = int(orig_h * target_aspect)
#                 left = (orig_w - new_w) // 2
#                 crop_box = (left, 0, left + new_w, orig_h)
#             else:
#                 # 图片太高/太窄（包括手机竖屏9:16），裁剪上下
#                 new_h = int(orig_w / target_aspect)
#                 top = (orig_h - new_h) // 2
#                 crop_box = (0, top, orig_w, top + new_h)
#
#             bg_full = img_raw.crop(crop_box).resize((VIDEO_W, VIDEO_H), Image.LANCZOS)
#     else:
#         bg_full = Image.new("RGB", (VIDEO_W, VIDEO_H), (20, 20, 30))
#
#     bg_scaled = bg_full.resize(
#         (int(VIDEO_W * BG_SCALE_FACTOR), int(VIDEO_H * BG_SCALE_FACTOR)),
#         Image.LANCZOS
#     ).convert("RGBA")
#     bg_full.close()
#
#     # ──── 封面图逻辑保持不变 ────
#     cp = _find_image(img_dir, target_cover)
#     cover_src = Image.open(cp if cp else (bg_p if bg_p else None)).convert("RGB")
#     w, h = cover_src.size
#     sq = min(w, h)
#     cover_src = cover_src.crop(((w - sq) // 2, (h - sq) // 2, (w + sq) // 2, (h + sq) // 2))
#
#     d = COVER_R * 2
#     cover_base = cover_src.resize((d, d), Image.LANCZOS).convert("RGBA")
#     cover_src.close()
#
#     render_dur = DEBUG_DURATION if DEBUG_MODE else audio.duration
#
#     video = VideoClip(
#         lambda t: _render_frame(t, bg_scaled, cover_base, lyrics, title, artist, fonts),
#         duration=render_dur
#     )
#     video = video.set_audio(audio.subclip(0, render_dur))
#
#     _tmp_v = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
#
#     try:
#         video.write_videofile(
#             _tmp_v, fps=FPS, codec="libx264", audio_codec="aac", preset="fast",
#             ffmpeg_params=["-crf", "18", "-threads", "4"]
#         )
#
#         video.close()
#         audio.close()
#
#         if os.path.exists(video_path):
#             os.remove(video_path)
#         shutil.move(_tmp_v, video_path)
#
#     finally:
#         bg_scaled.close()
#         cover_base.close()
#
#         if _tmp_mp3 and os.path.exists(_tmp_mp3):
#             try:
#                 os.remove(_tmp_mp3)
#             except:
#                 pass
#         if os.path.exists(_tmp_v):
#             try:
#                 os.remove(_tmp_v)
#             except:
#                 pass
#
#     print(f"✅ 完成渲染 (4K): {video_path}")
#     return video_path
#
#
# # ════════════════════════════════════════════════════════
# #  执行入口
# # ════════════════════════════════════════════════════════
# if __name__ == "__main__":
#     songs = [




#         ("谪仙", "伊格赛听&叶里", "zhexian"),
#         ("青衣", "琪大妈", "qingyi"),
#         # # ("红昭愿", "音阙诗听", "hongzhao"),
#         # ("春庭雪", "等什么君", "chuntingxue"),
#         ("春不晚", "冰洁", "chunbuwan"),
#         # ("沈园外", " ", "shenyuan1"),
#         ("云与海", "阿YueYue", "yun1"),
#         # ("不凡", "王铮亮", "fanren4"),
#         ("十年人间", "李常超", "biji"),
#         # ("想你和我们的以后", "苏运莹", "huayuan"),
#         # ("何以歌", "Aki阿杰", "heyige"),
#         # ("一花一剑", "李鑫一", "huajian"),
#         # ("陪你去流浪", "XueZhiQian", "liulang"),
#     ]
#
#     for s in songs:
#         try:
#             generate_lyric_video(*s)
#         except Exception as e:
#             print(f"❌ 歌曲 {s[0]} 渲染失败: {e}")
#         finally:
#             gc.collect()