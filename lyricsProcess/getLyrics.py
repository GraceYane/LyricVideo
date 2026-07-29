import re
import requests
from pathlib import Path


def clean_filename(filename: str) -> str:
    """清除文件名中的非法字符，防止创建文件报错"""
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    return re.sub(invalid_chars, '_', filename).strip()


def save_lyrics(song_name: str, lyrics_content: str, folder_path: str, ext: str = ".txt") -> str:
    """
    保存歌词到指定文件夹，自动创建目录
    :param song_name: 歌曲名
    :param lyrics_content: 歌词内容
    :param folder_path: 保存目录
    :param ext: 文件扩展名（如 .lrc 或 .txt）
    :return: 保存结果信息
    """
    save_dir = Path(folder_path)
    save_dir.mkdir(parents=True, exist_ok=True)

    clean_name = clean_filename(song_name)
    file_path = save_dir / f"{clean_name}{ext}"

    try:
        # utf-8-sig 编码可防止 Windows 记事本打开乱码
        with open(file_path, 'w', encoding='utf-8-sig') as f:
            f.write(lyrics_content)
        return f"✅ 成功保存至: {file_path.resolve()}"
    except Exception as e:
        return f"❌ 保存文件失败: {e}"


def getLyrics(song_name: str, include_translation: bool = False, keep_timestamp: bool = True) -> str:
    """
    获取网易云歌词并自动保存（支持 .lrc 带时间戳 或 .txt 纯文本）
    :param song_name: 歌名
    :param include_translation: 是否包含翻译歌词
    :param keep_timestamp: True=保留时间戳保存为 .lrc，False=删除时间戳保存为 .txt
    :return: 执行结果信息
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://music.163.com/',
        'Accept': 'application/json, text/plain, */*'
    }

    # 1. 搜索歌曲获取 ID
    search_url = f"https://music.163.com/api/search/get/web?s={requests.utils.quote(song_name)}&type=1&limit=1&offset=0"
    try:
        res = requests.get(search_url, headers=headers, timeout=10)
        data = res.json()
        if not data.get('result') or not data['result'].get('songs'):
            return f"❌ 未找到歌曲 [{song_name}]"

        real_song_name = data['result']['songs'][0]['name']
        song_id = data['result']['songs'][0]['id']
        print(f"🔍 找到歌曲: {real_song_name} (ID: {song_id})")

    except Exception as e:
        return f"❌ 搜索失败: {e}"

    # 2. 获取歌词数据
    lyric_url = f"https://music.163.com/api/song/lyric?id={song_id}&lv=1&kv=1&tv=-1"
    try:
        res_lyric = requests.get(lyric_url, headers=headers, timeout=10)
        res_lyric.raise_for_status()
        lyric_data = res_lyric.json()

        raw_lrc = lyric_data.get('lrc', {}).get('lyric', '')
        if not raw_lrc:
            return "⚠️ 该歌曲暂无歌词"

        # 定义要过滤的制作信息关键词行
        filter_keywords = {"作词", "作曲", "编曲", "制作人", "监制", "混音", "录音", "贝斯", "吉他"}

        # 辅助函数：提取时间戳和原文
        def split_lrc_line(line: str):
            """返回 (timestamp_part, content_part)  timestamp_part 可能为空字符串"""
            match = re.match(r'^(\[\d+:\d+(?:\.\d+)?\])+(.*)$', line)
            if match:
                return match.group(1), match.group(2).strip()
            else:
                return "", line.strip()

        # 逐行处理原始 LRC（保留时间戳）
        processed_lines = []
        for raw_line in raw_lrc.splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            ts_part, content = split_lrc_line(raw_line)
            if not content:
                # 只有时间戳没有文字的行，保留（某些 LRC 可能有空行）
                processed_lines.append(raw_line)
                continue
            # 检查正文是否包含过滤关键词（完全匹配单词，避免误伤）
            content_lower = content.lower()
            if any(keyword.lower() in content_lower for keyword in filter_keywords):
                continue  # 跳过这一整行
            processed_lines.append(raw_line)

        # 处理翻译（如果需要）
        if include_translation:
            raw_tlyric = lyric_data.get('tlyric', {}).get('lyric', '')
            if raw_tlyric:
                # 将翻译也拆分为行，并建立时间戳->翻译文本的映射
                trans_map = {}
                for trans_line in raw_tlyric.splitlines():
                    trans_line = trans_line.strip()
                    if not trans_line:
                        continue
                    ts_part, trans_content = split_lrc_line(trans_line)
                    if ts_part and trans_content:
                        trans_map[ts_part] = trans_content
                # 合并到处理好的行
                merged_lines = []
                for lrc_line in processed_lines:
                    ts_part, content = split_lrc_line(lrc_line)
                    if ts_part and ts_part in trans_map:
                        merged_lines.append(lrc_line + " (" + trans_map[ts_part] + ")")
                    else:
                        merged_lines.append(lrc_line)
                processed_lines = merged_lines

        # 根据 keep_timestamp 决定最终内容
        if keep_timestamp:
            final_content = "\n".join(processed_lines)
            folder = "output/lrcCorrection"
            ext = ".lrc"
        else:
            # 删除时间戳，只保留正文
            clean_lines = []
            for line in processed_lines:
                _, content = split_lrc_line(line)
                if content:
                    clean_lines.append(content)
            final_content = "\n".join(clean_lines)
            folder = "output/txt"
            ext = ".txt"

        # 保存文件
        save_result = save_lyrics(real_song_name, final_content, folder_path=folder, ext=ext)
        return f"{save_result}"

    except Exception as e:
        return f"❌ 获取歌词失败: {e}"


# === 测试代码 ===
if __name__ == "__main__":
    target_song = "天龙八部之宿敌"

    print("🚀 测试1：保留时间戳，保存为 .lrc（默认）")
    print("-" * 40)
    result1 = getLyrics(target_song, include_translation=False, keep_timestamp=True)
    print(result1)

    print("\n🚀 测试2：删除时间戳，保存为 .txt")
    print("-" * 40)
    result2 = getLyrics(target_song, include_translation=False, keep_timestamp=False)
    print(result2)