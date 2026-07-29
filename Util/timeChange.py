#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
timeChange.py
调整单个 lrc 文件的时间戳

用法：修改底部 shift_single("歌曲名", 偏移秒数) 直接运行
"""

import os
import re
from pathlib import Path

# ════════════════════════════════════════════════════════
#  路径配置（自动定位，无需手动修改）
# ════════════════════════════════════════════════════════
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LRC_DIR      = os.path.join(PROJECT_ROOT, "output", "lrcCorrection")


# ════════════════════════════════════════════════════════
#  核心函数
# ════════════════════════════════════════════════════════
def _shift_timestamp(mm: str, ss: str, ms: str, offset: float) -> str:
    """将单个时间戳偏移 offset 秒，返回新的 [mm:ss.xx] 字符串"""
    ms_padded = ms.ljust(3, '0')[:3]
    total_ms  = int(mm) * 60000 + int(ss) * 1000 + int(ms_padded)
    total_ms += int(round(offset * 1000))
    total_ms  = max(total_ms, 0)   # 防止时间戳变负

    new_mm    = total_ms // 60000
    remainder = total_ms % 60000
    new_ss    = remainder // 1000
    new_ms    = remainder % 1000

    # 保持原始毫秒位数（2位或3位）
    if len(ms) <= 2:
        return f"[{new_mm:02d}:{new_ss:02d}.{new_ms // 10:02d}]"
    else:
        return f"[{new_mm:02d}:{new_ss:02d}.{new_ms:03d}]"


def shift_single(song_name: str, offset: float) -> None:
    """
    处理单个 lrc 文件的时间戳

    :param song_name: 歌曲名（不含后缀），对应 lrcCorrection/{song_name}.lrc
    :param offset:    时间偏移量（秒），正数=往后移，负数=往前移
                      例：2.0 表示每行加2秒，-1.5 表示每行减1.5秒
    """
    lrc_path = os.path.join(LRC_DIR, f"{song_name}.lrc")

    if not os.path.exists(lrc_path):
        print(f"❌ 找不到文件: {lrc_path}")
        return

    time_pat = re.compile(r'\[(\d{2}):(\d{2})\.(\d{2,3})\]')

    with open(lrc_path, encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        def replace_ts(m):
            return _shift_timestamp(m.group(1), m.group(2), m.group(3), offset)
        new_lines.append(time_pat.sub(replace_ts, line))

    with open(lrc_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    direction = "+" if offset >= 0 else ""
    print(f"✅ [{song_name}.lrc] 时间戳已偏移 {direction}{offset}s")


# ════════════════════════════════════════════════════════
#  ★ 在这里填写歌曲名和偏移秒数，然后运行
# ════════════════════════════════════════════════════════
if __name__ == "__main__":
    # shift_single("Time After Time", -0.15)   # ← 改这里：歌曲名, 偏移秒数
    # shift_single("天行九歌", 1)
    # shift_single("主角", 0.15)
    shift_single("游山恋", -0.18)
    # shift_single("出现又离开", 0.1)
    # ("武家坡2021", "", "wujiapo"),  # -0.2
    # ## ("知否知否", "胡夏&郁可唯", "haitang"),
    # ("不谓侠", "萧忆情Alex", "buweixia"),  # -0.8
    # ("溺水三千", "石头&张晓棠", "nishuisanq"),
    # ("杨花落尽子规啼", "G2er&黄诗扶", "nishuisanq"),  # -0.8