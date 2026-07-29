#!/usr/bin/env python3
"""
MP3 片段截取工具
依赖: pip install pydub
     以及 ffmpeg（已安装完整版）
"""

import os
import re
import sys
from typing import Optional

# ffmpeg 完整路径（与 bili_bgm.py 保持一致）
FFMPEG_PATH = r"D:\AADownloads\Pffmpeg\ffmpeg\bin\ffmpeg.exe"


def parse_time(time_str: str) -> int:
    """
    将时间字符串解析为毫秒。
    支持格式：
      "1m23s"  →  83000 ms
      "30s"    →  30000 ms
      "2m"     →  120000 ms
      "90"     →  90000 ms（纯数字视为秒）
    """
    time_str = time_str.strip().lower()

    # 格式：1m23s / 1m / 23s
    match = re.fullmatch(r'(?:(\d+)m)?(?:(\d+)s)?', time_str)
    if match and (match.group(1) or match.group(2)):
        minutes = int(match.group(1) or 0)
        seconds = int(match.group(2) or 0)
        return (minutes * 60 + seconds) * 1000

    # 纯数字：视为秒
    if time_str.isdigit():
        return int(time_str) * 1000

    raise ValueError(
        f"无法解析时间格式：'{time_str}'，"
        "支持格式示例：'1m23s'、'30s'、'2m'、'90'"
    )


def find_mp3_file(song_name: str, input_dir: str) -> str:
    """
    在指定目录中查找 MP3 文件

    Args:
        song_name: 歌曲名（不含 .mp3 后缀）
        input_dir: 查找目录

    Returns:
        找到的 MP3 文件完整路径

    Raises:
        FileNotFoundError: 如果找不到文件
    """
    # 1. 精确匹配
    exact_path = os.path.join(input_dir, f"{song_name}.mp3")
    if os.path.isfile(exact_path):
        return exact_path

    # 2. 模糊匹配（包含歌曲名的文件）
    if os.path.isdir(input_dir):
        for file in os.listdir(input_dir):
            if file.endswith('.mp3') and song_name in file:
                return os.path.join(input_dir, file)

    # 3. 找不到文件
    raise FileNotFoundError(
        f"找不到 MP3 文件：{song_name}.mp3\n"
        f"搜索目录：{input_dir}\n"
        f"请确认文件名是否正确（支持模糊匹配）"
    )


def generate_output_filename(song_name: str, output_dir: str) -> str:
    """
    生成输出文件名，避免覆盖已存在的文件

    Args:
        song_name: 歌曲名
        output_dir: 输出目录

    Returns:
        完整的输出文件路径
    """
    out_path = os.path.join(output_dir, f"{song_name}.mp3")

    # 如果文件已存在，添加序号
    if os.path.exists(out_path):
        counter = 1
        while os.path.exists(os.path.join(output_dir, f"{song_name}_{counter}.mp3")):
            counter += 1
        out_path = os.path.join(output_dir, f"{song_name}_{counter}.mp3")
        print(f"📝 文件已存在，使用新名称: {os.path.basename(out_path)}")

    return out_path


def musicCut(
        song_name: str,
        start: str,
        end: str = None,
        input_dir: Optional[str] = None,
        output_dir: Optional[str] = None,
        output_name: Optional[str] = None
) -> str:
    """
    从 MP3 文件中按时间截取片段，生成新 MP3 文件。

    Args:
        song_name:   歌曲名（不含 .mp3 后缀）
        start:       起始时间，如 "1m10s"、"30s"
        end:         结束时间，如 "1m23s"、"90s"，不填则到音频结尾
        input_dir:   输入目录，默认为当前脚本目录
        output_dir:  输出目录，默认为输入目录
        output_name: 输出文件名（不含.mp3后缀），默认使用song_name

    Returns:
        生成的新 MP3 文件绝对路径

    Raises:
        FileNotFoundError: 找不到 MP3 文件
        ValueError:        时间格式错误或起止时间不合法
        RuntimeError:      截取失败

    Examples:
        # 基础用法（输出：绅士.mp3）
        musicCut("绅士", "1m10s", "1m23s")

        # 指定输出文件名（输出：绅士片段.mp3）
        musicCut("绅士", "1m10s", "1m23s", output_name="绅士片段")

        # 指定目录（输出：./output/绅士.mp3）
        musicCut("绅士", "1m10s", "1m23s",
                input_dir="./music", output_dir="./output")
    """
    # ── 1. 确定输入输出目录 ─────────────────────────────────────────────────
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 输入目录：优先使用传入的，否则使用脚本目录
    in_dir = input_dir if input_dir else script_dir
    in_dir = os.path.abspath(in_dir)

    # 输出目录：优先使用传入的，否则使用输入目录
    out_dir = output_dir if output_dir else in_dir
    out_dir = os.path.abspath(out_dir)

    # ── 2. 查找 MP3 文件 ─────────────────────────────────────────────────────
    input_path = find_mp3_file(song_name, in_dir)

    print(f"📁 输入文件: {input_path}")
    print(f"📁 输出目录: {out_dir}")

    # ── 3. 解析时间 ─────────────────────────────────────────────────────────
    start_ms = parse_time(start)

    # 如果没有指定结束时间，默认为音频结尾
    end_ms = None
    if end:
        end_ms = parse_time(end)

    if end_ms is not None and start_ms >= end_ms:
        raise ValueError(
            f"起始时间 ({start}) 必须早于结束时间 ({end})"
        )

    # ── 4. 加载音频 ─────────────────────────────────────────────────────────
    try:
        from pydub import AudioSegment
    except ImportError:
        raise RuntimeError("请先安装 pydub：pip install pydub")

    # 告诉 pydub 用指定的 ffmpeg
    if FFMPEG_PATH and os.path.isfile(FFMPEG_PATH):
        AudioSegment.converter = FFMPEG_PATH

    print(f"🎵 正在加载: {os.path.basename(input_path)}")
    audio = AudioSegment.from_mp3(input_path)

    duration_ms = len(audio)
    duration_str = f"{duration_ms // 60000}m{(duration_ms % 60000) // 1000}s"

    # 如果没有指定结束时间，使用音频总长度
    if end_ms is None:
        end_ms = duration_ms
        print(f"📝 未指定结束时间，使用音频结尾 ({duration_str})")

    # 验证时间范围
    if end_ms > duration_ms:
        print(f"⚠️  结束时间 ({end}) 超出歌曲总时长 ({duration_str})，已自动调整")
        end_ms = duration_ms

    # ── 5. 截取片段 ─────────────────────────────────────────────────────────
    segment = audio[start_ms:end_ms]
    segment_duration = (end_ms - start_ms) / 1000

    # ── 6. 构造输出路径 ─────────────────────────────────────────────────────
    os.makedirs(out_dir, exist_ok=True)

    # 使用指定的输出文件名，或默认使用歌曲名
    final_name = output_name if output_name else song_name
    out_path = generate_output_filename(final_name, out_dir)

    # ── 7. 导出 ─────────────────────────────────────────────────────────────
    print(f"✂️  截取: {start} → {end or '结尾'}  ({segment_duration:.1f} 秒)")
    segment.export(out_path, format="mp3", bitrate="192k")

    print(f"✅ 完成！已保存至: {out_path}")
    return out_path


# ── 批量截取函数 ─────────────────────────────────────────────────────────────
def musicCut_batch(
        cuts: list,
        input_dir: Optional[str] = None,
        output_dir: Optional[str] = None
):
    """
    批量截取多个音频片段

    Args:
        cuts: 截取列表，格式 [
            ("歌曲名", "起始时间", "结束时间"),
            ("歌曲名", "起始时间", "结束时间", "输出文件名"),  # 自定义输出名
            ("歌曲名", "起始时间"),  # 不指定结束时间
        ]
        input_dir:  输入目录，默认为当前脚本目录
        output_dir: 输出目录，默认为输入目录

    Returns:
        结果列表 [(成功, 输出路径或错误信息), ...]

    Examples:
        cuts = [
            ("绅士", "1m10s", "1m23s"),           # 输出：绅士.mp3
            ("绅士", "30s", "1m0s", "绅士片段2"),  # 输出：绅士片段2.mp3
            ("狐狸", "0s"),                        # 输出：狐狸.mp3（整首）
        ]
        musicCut_batch(cuts, input_dir="./music", output_dir="./output")
    """
    results = []
    total = len(cuts)

    print(f"\n🔄 批量截取 {total} 个片段...")

    for i, cut in enumerate(cuts, 1):
        song_name = cut[0]
        start = cut[1]
        end = cut[2] if len(cut) > 2 and not (
                    isinstance(cut[2], str) and not any(c.isdigit() for c in cut[2][:2])) else None
        output_name = cut[3] if len(cut) > 3 else None

        # 修正：如果第三个参数是输出名而不是时间
        if len(cut) > 2 and isinstance(cut[2], str) and end is None:
            # 检查第二个参数是否是时间格式
            if not any(c.isdigit() for c in cut[2][:2]):
                end = None
                output_name = cut[2]

        print(f"\n[{i}/{total}] 处理: {song_name} -> {output_name or song_name}.mp3")

        try:
            result = musicCut(
                song_name, start, end,
                input_dir=input_dir,
                output_dir=output_dir,
                output_name=output_name
            )
            results.append((True, result))
            print(f"  ✓ 成功")
        except Exception as e:
            results.append((False, str(e)))
            print(f"  ✗ 失败: {e}")

    # 汇总
    success_count = sum(1 for success, _ in results if success)
    print(f"\n{'=' * 50}")
    print(f"批量截取完成: {success_count}/{total} 成功")

    return results


# ── 命令行入口 ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MP3 片段截取工具")
    parser.add_argument("song", help="歌曲名（不含.mp3后缀）")
    parser.add_argument("start", help="起始时间，如 1m10s")
    parser.add_argument("end", nargs="?", default=None, help="结束时间，如 1m23s（可选）")
    parser.add_argument("-i", "--input-dir", default=None, help="输入目录")
    parser.add_argument("-o", "--output-dir", default=None, help="输出目录")
    parser.add_argument("-n", "--output-name", default=None, help="输出文件名（不含.mp3后缀）")

    args = parser.parse_args()

    try:
        path = musicCut(
            args.song,
            args.start,
            args.end,
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            output_name=args.output_name
        )
        print(f"\n✅ 成功生成: {path}")
    except Exception as e:
        print(f"❌ 错误: {e}")
        sys.exit(1)

    # 如果没有命令行参数，运行默认测试
    if len(sys.argv) == 1:
        print("=== 运行测试用例 ===\n")
        try:
            # 测试1：基本用法（输出：绅士.mp3）
            print("【测试1】基本截取")
            musicCut("绅士", "1m10s", "1m23s")

            print("\n" + "=" * 50 + "\n")

            # 测试2：自定义输出文件名（输出：绅士片段.mp3）
            print("【测试2】自定义输出文件名")
            musicCut("绅士", "1m10s", "1m23s", output_name="绅士片段")

            print("\n" + "=" * 50 + "\n")

            # 测试3：截取到结尾（输出：绅士.mp3）
            print("【测试3】截取到结尾")
            musicCut("绅士", "1m10s")

            print("\n" + "=" * 50 + "\n")

            # 测试4：指定目录
            print("【测试4】指定目录")
            musicCut(
                "绅士",
                "1m10s",
                "1m23s",
                input_dir="./MusicProcess/getMusic",
                output_dir="./MusicProcess/output"
            )

            print("\n" + "=" * 50 + "\n")

            # 测试5：批量处理
            print("【测试5】批量处理")
            cuts = [
                ("绅士", "1m10s", "1m23s"),
                ("绅士", "30s", "1m0s", "绅士片段"),  # 自定义输出名
                ("狐狸", "0s"),  # 整首
            ]
            musicCut_batch(cuts, output_dir="./MusicProcess/output")

        except Exception as e:
            print(f"测试出错: {e}")