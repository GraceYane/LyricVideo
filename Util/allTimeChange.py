#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
allTimeChange.py
批量调整 lrcCorrection 目录下所有 .lrc 文件的时间戳

用法：直接运行，会将 lrcCorrection 下所有 lrc 文件的时间戳统一偏移 OFFSET_SECONDS
"""

import os
import re
from pathlib import Path

# ════════════════════════════════════════════════════════
#  ★ 配置：改这里
# ════════════════════════════════════════════════════════
OFFSET_SECONDS = -0.7   # 时间偏移量（秒），正数=往后移，负数=往前移
                       # 例：2 表示每行时间戳加2秒，-1 表示减1秒

# ════════════════════════════════════════════════════════
#  路径配置（自动定位，无需手动修改）
# ════════════════════════════════════════════════════════
PROJECT_ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LRC_DIR       = os.path.join(PROJECT_ROOT, "output", "lrcCorrection")


# ════════════════════════════════════════════════════════
#  核心函数
# ════════════════════════════════════════════════════════
def _shift_timestamp(mm: str, ss: str, ms: str, offset: float) -> str:
    """将单个时间戳偏移 offset 秒，返回新的 [mm:ss.xx] 字符串"""
    # 解析为总毫秒数
    ms_padded  = ms.ljust(3, '0')[:3]   # 统一3位
    total_ms   = int(mm) * 60000 + int(ss) * 1000 + int(ms_padded)
    total_ms  += int(round(offset * 1000))

    # 防止时间戳变负
    total_ms   = max(total_ms, 0)

    # 重新拆分
    new_mm     = total_ms // 60000
    remainder  = total_ms % 60000
    new_ss     = remainder // 1000
    new_ms     = remainder % 1000

    # 保持原始毫秒位数（2位或3位）
    if len(ms) <= 2:
        return f"[{new_mm:02d}:{new_ss:02d}.{new_ms // 10:02d}]"
    else:
        return f"[{new_mm:02d}:{new_ss:02d}.{new_ms:03d}]"


def shift_lrc_file(lrc_path: str, offset: float) -> None:
    """处理单个 lrc 文件，原地修改"""
    time_pat = re.compile(r'\[(\d{2}):(\d{2})\.(\d{2,3})\]')

    with open(lrc_path, encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        # 替换行内所有时间戳
        def replace_ts(m):
            return _shift_timestamp(m.group(1), m.group(2), m.group(3), offset)

        new_line = time_pat.sub(replace_ts, line)
        new_lines.append(new_line)

    with open(lrc_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)


def batch_shift(lrc_dir: str, offset: float) -> None:
    """批量处理目录下所有 .lrc 文件"""
    lrc_dir = Path(lrc_dir)
    if not lrc_dir.exists():
        print(f"❌ 目录不存在: {lrc_dir}")
        return

    lrc_files = sorted(lrc_dir.glob("*.lrc"))
    if not lrc_files:
        print(f"⚠️  目录下没有找到 .lrc 文件: {lrc_dir}")
        return

    direction = "+" if offset >= 0 else ""
    print(f"📂 目录: {lrc_dir}")
    print(f"⏱  时间偏移: {direction}{offset}s")
    print(f"📄 共找到 {len(lrc_files)} 个 .lrc 文件\n")

    for lrc_path in lrc_files:
        try:
            shift_lrc_file(str(lrc_path), offset)
            print(f"  ✅ {lrc_path.name}")
        except Exception as e:
            print(f"  ❌ {lrc_path.name}  错误: {e}")

    print(f"\n🎉 完成！共处理 {len(lrc_files)} 个文件，每行时间戳 {direction}{offset}s")


# ════════════════════════════════════════════════════════
#  入口
# ════════════════════════════════════════════════════════
if __name__ == "__main__":
    batch_shift(LRC_DIR, OFFSET_SECONDS)