import os
from pydub import AudioSegment
from pydub.effects import high_pass_filter, low_pass_filter
import numpy as np
from pathlib import Path


def time_to_milliseconds(time_str):
    """
    将时间字符串转换为毫秒
    支持格式：'1m10s', '10s', '1m', '1m10s'
    """
    minutes = 0
    seconds = 0

    time_str = time_str.lower().replace(' ', '')

    if 'm' in time_str:
        parts = time_str.split('m')
        minutes = int(parts[0])
        if 's' in parts[1]:
            seconds = int(parts[1].replace('s', ''))
    elif 's' in time_str:
        seconds = int(time_str.replace('s', ''))

    return (minutes * 60 + seconds) * 1000


def reduce_vocals_segment(audio_segment, strength=0.7):
    """
    降低人声，制作伴奏效果
    通过相位抵消和频率处理来减少人声
    """
    # 方法1：中频削减（人声通常在300-3000Hz范围内）
    # 将音频分割成不同频段
    samples = np.array(audio_segment.get_array_of_samples())

    # 如果是立体声，尝试相位抵消
    if audio_segment.channels == 2:
        left = audio_segment.split_to_mono()[0]
        right = audio_segment.split_to_mono()[1]

        # 人声通常在中央声道，通过左右声道相减可以减弱人声
        left_array = np.array(left.get_array_of_samples())
        right_array = np.array(right.get_array_of_samples())

        # 创建人声减弱的版本
        vocal_reduced = (left_array - right_array) * strength

        # 混合原始音频和处理后的音频
        mixed_left = (left_array * (1 - strength) + vocal_reduced * strength).astype(np.int16)
        mixed_right = (right_array * (1 - strength) - vocal_reduced * strength).astype(np.int16)

        # 重新创建立体声音频
        processed_segment = AudioSegment(
            data=np.column_stack((mixed_left, mixed_right)).tobytes(),
            sample_width=audio_segment.sample_width,
            frame_rate=audio_segment.frame_rate,
            channels=2
        )
    else:
        # 单声道处理：使用带阻滤波器减弱人声频率
        # 先高通滤波去除低频噪音
        processed = high_pass_filter(audio_segment, 150)
        # 在1000-3000Hz范围降低增益（人声主要频段）
        processed = processed.low_pass_filter(3000)
        # 混合原始和处理后的音频
        processed_segment = audio_segment * (1 - strength) + processed * strength

    return processed_segment


def pitchDown(song_name, start_time, end_time=None, vocal_reduction_strength=1):
    """
    处理MP3文件，降低指定时间段的人声（制作伴奏效果）

    参数:
        song_name: 歌曲名（不含.mp3后缀）
        start_time: 起始时间，如 "1m10s"
        end_time: 结束时间，如 "1m23s"，不填则为音频结尾
        vocal_reduction_strength: 人声降低强度 (0-1)，越大降低越多

    返回:
        处理后的音频文件路径

    使用示例:
        pitchDown("绅士", "1m10s", "1m23s")
        pitchDown("绅士", "1m10s")  # 处理到结尾
        pitchDown("绅士", "1m10s", "1m23s", vocal_reduction_strength=0.9)
    """
    # 获取当前脚本所在目录
    current_dir = Path(__file__).parent if '__file__' in dir() else Path.cwd()

    # 构建输入文件路径（与pitchDown.py同目录）
    input_file = current_dir / f"{song_name}.mp3"

    # 检查文件是否存在
    if not input_file.exists():
        # 尝试在getMusic目录下查找
        input_file = current_dir / "getMusic" / f"{song_name}.mp3"
        if not input_file.exists():
            # 尝试在父目录查找
            input_file = current_dir.parent / f"{song_name}.mp3"
            if not input_file.exists():
                raise FileNotFoundError(
                    f"找不到文件: {song_name}.mp3\n搜索路径:\n  {current_dir}\\{song_name}.mp3\n  {current_dir}\\getMusic\\{song_name}.mp3")

    print(f"正在处理: {input_file}")

    # 加载MP3文件
    audio = AudioSegment.from_mp3(str(input_file))

    # 转换时间
    start_ms = time_to_milliseconds(start_time)

    if end_time:
        end_ms = time_to_milliseconds(end_time)
    else:
        end_ms = len(audio)  # 默认到音频结尾

    # 验证时间范围
    audio_length_seconds = len(audio) / 1000
    if start_ms >= len(audio):
        raise ValueError(f"起始时间 {start_time} ({start_ms / 1000}秒) 超出音频长度 {audio_length_seconds}秒")
    if end_ms > len(audio):
        print(f"警告: 结束时间超出音频长度，自动调整为音频结尾")
        end_ms = len(audio)
    if start_ms >= end_ms:
        raise ValueError(f"起始时间必须小于结束时间")

    print(f"音频总长度: {audio_length_seconds:.1f}秒")
    print(f"处理时间段: {start_ms / 1000:.1f}s - {end_ms / 1000:.1f}s (时长: {(end_ms - start_ms) / 1000:.1f}s)")

    # 分割音频为三部分
    before_segment = audio[:start_ms]  # 处理前的部分
    middle_segment = audio[start_ms:end_ms]  # 需要处理的部分
    after_segment = audio[end_ms:]  # 处理后的部分

    # 对中间部分进行人声降低处理
    print("正在降低人声...")
    processed_middle = reduce_vocals_segment(middle_segment, vocal_reduction_strength)

    # 合并音频：前部分 + 处理后部分 + 后部分
    final_audio = before_segment + processed_middle + after_segment

    # 生成输出文件名
    output_filename = f"{song_name}_pitchDown_{start_time}_{end_time or 'end'}.mp3"
    output_file = current_dir / output_filename

    # 如果文件已存在，添加序号
    counter = 1
    while output_file.exists():
        output_filename = f"{song_name}_pitchDown_{start_time}_{end_time or 'end'}_{counter}.mp3"
        output_file = current_dir / output_filename
        counter += 1

    # 导出处理后的音频
    print(f"正在导出: {output_filename}")
    final_audio.export(
        str(output_file),
        format="mp3",
        bitrate="192k",
        parameters=["-q:a", "0"]  # 高质量编码
    )

    print(f"✓ 完成！文件已保存至: {output_file}")
    return str(output_file)


# 高级版本：使用更专业的音频处理
def pitchDown_advanced(song_name, start_time, end_time=None, vocal_reduction_strength=0.8):
    """
    高级版本的人声降低处理
    需要安装scipy: pip install scipy
    """
    try:
        from scipy import signal

        def advanced_vocal_reduction(audio_segment, strength=0.8):
            """更高级的人声降低处理"""
            samples = np.array(audio_segment.get_array_of_samples())
            sample_rate = audio_segment.frame_rate

            if audio_segment.channels == 2:
                # 立体声处理
                left = samples[::2]  # 左声道采样
                right = samples[1::2]  # 右声道采样

                # 1. 中置声道提取和减弱
                center = (left + right) / 2  # 人声通常在中置
                sides = (left - right) / 2  # 环境声在两侧

                # 2. 减弱中置声道（人声），保留侧声道（伴奏）
                vocal_reduced_center = center * (1 - strength)

                # 3. 设计中频滤波器进一步减弱人声
                nyquist = sample_rate / 2
                low_freq = 300 / nyquist  # 人声低频截止
                high_freq = 3000 / nyquist  # 人声高频截止

                # 带阻滤波器减弱人声频段
                b, a = signal.butter(4, [low_freq, high_freq], btype='bandstop')
                vocal_reduced_center = signal.lfilter(b, a, vocal_reduced_center)

                # 4. 重新混合
                new_left = (vocal_reduced_center * strength + sides * (2 - strength)).astype(np.int16)
                new_right = (vocal_reduced_center * strength - sides * (2 - strength)).astype(np.int16)

                # 重建立体声
                stereo_data = np.column_stack((new_left, new_right)).flatten()

                return AudioSegment(
                    data=stereo_data.tobytes(),
                    sample_width=audio_segment.sample_width,
                    frame_rate=sample_rate,
                    channels=2
                )
            else:
                # 单声道处理
                nyquist = sample_rate / 2
                low_freq = 300 / nyquist
                high_freq = 3000 / nyquist

                b, a = signal.butter(4, [low_freq, high_freq], btype='bandstop')
                filtered = signal.lfilter(b, a, samples)

                processed = (samples * (1 - strength) + filtered * strength).astype(np.int16)

                return AudioSegment(
                    data=processed.tobytes(),
                    sample_width=audio_segment.sample_width,
                    frame_rate=sample_rate,
                    channels=1
                )

        # 使用高级处理方法重新实现pitchDown
        current_dir = Path(__file__).parent if '__file__' in dir() else Path.cwd()
        input_file = current_dir / f"{song_name}.mp3"

        if not input_file.exists():
            input_file = current_dir / "getMusic" / f"{song_name}.mp3"
            if not input_file.exists():
                raise FileNotFoundError(f"找不到文件: {song_name}.mp3")

        print(f"正在处理(高级模式): {input_file}")
        audio = AudioSegment.from_mp3(str(input_file))

        start_ms = time_to_milliseconds(start_time)
        end_ms = time_to_milliseconds(end_time) if end_time else len(audio)

        if end_ms > len(audio):
            end_ms = len(audio)

        before_segment = audio[:start_ms]
        middle_segment = audio[start_ms:end_ms]
        after_segment = audio[end_ms:]

        print("正在降低人声(高级处理)...")
        processed_middle = advanced_vocal_reduction(middle_segment, vocal_reduction_strength)

        final_audio = before_segment + processed_middle + after_segment

        output_filename = f"{song_name}_pitchDown_advanced_{start_time}_{end_time or 'end'}.mp3"
        output_file = current_dir / output_filename

        final_audio.export(str(output_file), format="mp3", bitrate="192k")
        print(f"✓ 完成！文件已保存至: {output_file}")
        return str(output_file)

    except ImportError:
        print("scipy未安装，使用基础pitchDown方法")
        return pitchDown(song_name, start_time, end_time, vocal_reduction_strength)


# 批量处理函数
def pitchDown_batch(song_list, vocal_reduction_strength=0.8):
    """
    批量处理多首歌曲

    参数:
        song_list: 歌曲处理列表，格式 [("歌曲名", "起始时间", "结束时间"), ...]
        vocal_reduction_strength: 人声降低强度

    示例:
        songs = [
            ("绅士", "1m10s", "1m23s"),
            ("绅士", "30s", "1m0s"),
            ("XueZhiQian《狐狸》百万豪装录音棚大声听", "0s", "45s")
        ]
        pitchDown_batch(songs)
    """
    results = []
    total = len(song_list)

    print(f"\n开始批量处理 {total} 首歌曲...")

    for i, (song_name, start_time, end_time) in enumerate(song_list, 1):
        print(f"\n[{i}/{total}] 处理: {song_name}")
        try:
            result = pitchDown(song_name, start_time, end_time, vocal_reduction_strength)
            results.append((song_name, True, result))
        except Exception as e:
            results.append((song_name, False, str(e)))
            print(f"✗ 处理失败: {e}")

    # 打印结果汇总
    print("\n" + "=" * 50)
    print("批量处理结果汇总")
    print("=" * 50)
    success_count = 0
    for song_name, success, message in results:
        status = "✓" if success else "✗"
        if success:
            success_count += 1
        print(f"{status} {song_name}: {message}")

    print(f"\n成功: {success_count}/{total}")
    return results


if __name__ == "__main__":
    # 使用示例
    print("=== pitchDown 人声降低处理工具 ===")
    print("使用说明:")
    print("  1. 将 pitchDown.py 放在与MP3文件相同的目录")
    print("  2. 调用 pitchDown('歌曲名', '起始时间', '结束时间')")
    print()

    # 示例调用
    try:
        # 示例1: 处理绅士的1分10秒到1分23秒

        # result1 = pitchDown("绅士", "10s", "1m23s")

        # 示例2: 处理到结尾
        result2 = pitchDown("绅士", "10s")

        # 示例3: 批量处理
        # songs = [
        #     ("绅士", "1m10s", "1m23s"),
        #     ("绅士_1m10s-1m43s", "0s", "33s"),
        # ]
        # pitchDown_batch(songs)

    except Exception as e:
        print(f"运行出错: {e}")