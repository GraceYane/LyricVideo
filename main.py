import re
import os
from moviepy.editor import *
from moviepy.video.tools.subtitles import SubtitlesClip

# --- 配置区域 ---
MP3_FILE = "input/天龙八部之宿敌.mp3"  # 你的mp3文件名
LRC_FILE = "auto_generated.lrc"  # 你的lrc文件名
OUTPUT_FILE = "output_video.mp4"  # 输出视频名
SONG_TITLE = "《天龙八部之宿敌》-许嵩"
FONT_PATH = "msyh.ttc"  # 字体路径，Windows通常是 msyh.ttc (微软雅黑)，Mac可能需要修改

# 图标定义 (使用Emoji代替图片，方便运行)
# 如果想用原图那种精致的黄色圆圈，建议准备 check.png 和 circle.png 图片并用 ImageClip
ICON_CHECK = "✅"  # 已唱/高亮
ICON_CIRCLE = "⚪️"  # 未唱


# 注意：Emoji在不同系统显示可能不同，如果需要精确的“黄色圆圈”，请下载图片替换逻辑

# --- 1. 解析LRC文件 ---
def parse_lrc(lrc_path):
    lyrics = []
    with open(lrc_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        for line in lines:
            # 匹配 [mm:ss.xx] 格式
            match = re.match(r'\[(\d+):(\d+)(?:\.(\d+))?\](.*)', line)
            if match:
                m, s, ms, text = match.groups()
                ms = ms or '0'
                # 计算秒数
                time_sec = int(m) * 60 + int(s) + float(ms) / 1000.0
                # 清理歌词文本（去除可能的空格）
                text = text.strip()
                if text:
                    lyrics.append((time_sec, text))
    return sorted(lyrics, key=lambda x: x[0])


# --- 2. 生成每一行歌词的动画片段 ---
def create_lyric_line(line_index, start_time, text, total_duration):
    """
    为每一句歌词创建一个独立的VideoClip。
    逻辑：
    - 如果当前时间 t >= start_time: 显示黄勾 + 亮色文字
    - 如果当前时间 t < start_time: 显示白圈 + 暗色文字
    """

    # 计算该行在屏幕上的Y坐标 (假设每行高度60)
    y_pos = 250 + line_index * 70

    def make_frame(t):
        # 判断状态
        # 这里做一个微调：通常歌词是“唱到的时候”变色。
        # 为了符合你的截图（累积打勾），我们设定：
        # 只要时间超过了这句歌词的开始时间，这句就变成“黄勾”。

        is_active = (t >= start_time)

        icon = ICON_CHECK if is_active else ICON_CIRCLE
        color = '#FFFFFF' if is_active else '#666666'  # 亮白 vs 暗灰
        font_size = 35 if is_active else 35

        # 构建文本：图标 + 歌词
        full_text = f"{icon}  {text}"

        # 创建文本对象
        # 注意：MoviePy的TextClip可能在某些系统对Emoji支持不好
        # 如果Emoji显示为方块，建议使用图片 (ImageClip) 替代 icon 变量
        try:
            txt_clip = TextClip(full_text, fontsize=font_size, color=color, font=FONT_PATH, stroke_color='black',
                                stroke_width=1)
        except Exception:
            # 如果字体报错，尝试去掉 font 参数
            txt_clip = TextClip(full_text, fontsize=font_size, color=color)

        # 设置位置 (x居中, y固定)
        # 假设视频宽度 1080
        txt_clip = txt_clip.set_position(('center', y_pos))
        return txt_clip

    # 创建一个持续整个视频时长的 Clip，但内容随时间变化
    # 这里用一种取巧的方法：创建一个白底/黑底透明Clip，然后在 Composite 中叠加
    # 但更简单的方法是：为每个时间点生成帧 (这很慢)
    # 或者：利用 MoviePy 的 lambda 特性

    # 这里使用一个持续整个视频的黑底透明Clip作为容器
    duration_clip = ColorClip(size=(1080, 100), color=(0, 0, 0, 0)).set_duration(total_duration)

    # 我们需要重写 make_frame 来返回 ImageClip 或 TextClip
    # 由于 TextClip 是静态的，我们需要用 VideoClip
    line_video = VideoClip(make_frame=make_frame, duration=total_duration)
    line_video = line_video.set_position(('center', y_pos))  # 这里位置设置可能无效，需要在Composite时设置

    return line_video, y_pos


# --- 3. 主程序 ---
def main():
    if not os.path.exists(MP3_FILE):
        print(f"找不到文件 {MP3_FILE}, 请确保文件在同目录下")
        return

    # 获取音频时长
    audio = AudioFileClip(MP3_FILE)
    duration = audio.duration

    # 解析歌词
    lyrics = parse_lrc(LRC_FILE)

    # 创建背景
    bg = ColorClip(size=(1080, 1920), color=(0, 0, 0))  # 黑色背景，竖屏
    bg = bg.set_duration(duration)

    # 添加标题
    title_clip = TextClip(SONG_TITLE, fontsize=50, color='white', font=FONT_PATH, stroke_color='black', stroke_width=2)
    title_clip = title_clip.set_position(('center', 150)).set_duration(duration)

    # 添加顶部模拟信息 (可选)
    # 这里省略，保持简洁

    clips = [bg, title_clip]

    # 生成每一行歌词
    # 为了模拟截图中的列表效果，我们需要把所有歌词都显示出来
    # 截图显示大约显示7-8行。如果歌词很多，可能需要滚动。
    # 简单版：假设歌词不多，或者只显示当前附近的歌词。
    # 但看截图，它是“清单”模式，所有歌词都在，只是状态在变。

    # 如果歌词太多，屏幕放不下，我们只显示前10行作为演示，或者你需要做滚动逻辑
    # 这里假设歌词较少，或者我们只取前8行

    # 修正：看截图，歌词是静态列表。
    # 我们遍历所有歌词，生成Clip
    for i, (time_sec, text) in enumerate(lyrics):
        # 限制一下行数，防止超出屏幕 (例如只显示前8行，或者你可以做滚动)
        # 这里为了演示截图效果，我们假设只处理前8行，或者你可以调整 y_pos 的算法
        if i < 10:
            line_clip, y_pos = create_lyric_line(i, time_sec, text, duration)
            line_clip = line_clip.set_position(('center', 250 + i * 80))  # 重新设置位置
            clips.append(line_clip)

    # 合成
    final_video = CompositeVideoClip(clips, size=(1080, 1920))
    final_video = final_video.set_audio(audio)

    print("正在渲染视频，请稍候...")
    final_video.write_videofile(OUTPUT_FILE, fps=24, codec='libx264', audio_codec='aac')
    print(f"完成！视频已保存为 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
