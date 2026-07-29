import os
import re
import time
import requests
from bs4 import BeautifulSoup

# 配置基础URL和请求头，模拟浏览器访问
BASE_URL = "https://www.ufanv.cn"
SINGER_URL = "https://www.ufanv.cn/singer/2"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def sanitize_filename(name):
    """清理文件名中的非法字符，防止保存文件时报错"""
    return re.sub(r'[\\/:*?"<>|]', '_', name)


def extract_song_name(title):
    """从形如 'XueZhiQian《其实》' 的标题中，只提取出书名号内部的歌曲名字 '其实'"""
    match = re.search(r'《([^》]+)》', title)
    if match:
        return match.group(1)
    return title  # 如果没匹配到书名号，则返回原标题


def get_song_list(singer_url):
    """从歌手页面获取所有歌曲的名称和详情页链接"""
    print(f"正在读取歌手页面: {singer_url}")
    try:
        response = requests.get(singer_url, headers=HEADERS, timeout=30)
        response.encoding = response.apparent_encoding
        if response.status_code != 200:
            print(f"无法访问页面，状态码: {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        songs = []

        # 寻找所有包含歌词页面的超链接（匹配形如 /lyric/xxxxx 的链接）
        links = soup.find_all('a', href=re.compile(r'/lyric/\d+'))

        for link in links:
            title = link.get_text(strip=True)
            href = link.get('href')
            full_url = BASE_URL + href if href.startswith('/') else href

            # 去重处理
            if title and full_url not in [s['url'] for s in songs]:
                songs.append({'title': title, 'url': full_url})

        print(f"成功解析出 {len(songs)} 首歌曲")
        return songs
    except Exception as e:
        print(f"解析歌手页面出错: {e}")
        return []


def download_lrc(song_title, song_url, output_dir="lyrics"):
    """进入歌曲详情页并下载LRC歌词内容（含超时重试机制，已优化文件名提取）"""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 【优化点】提取书名号内部的名字，再清理非法字符
    pure_song_name = extract_song_name(song_title)
    safe_title = sanitize_filename(pure_song_name)
    file_path = os.path.join(output_dir, f"{safe_title}.lrc")

    # 如果文件已存在则跳过，方便断点续传
    if os.path.exists(file_path):
        print(f"已存在，跳过: {safe_title}.lrc")
        return

    max_retries = 3  # 最大重试次数
    for attempt in range(max_retries):
        try:
            response = requests.get(song_url, headers=HEADERS, timeout=30)
            response.encoding = response.apparent_encoding

            if response.status_code != 200:
                print(f"服务器返回错误状态码: {response.status_code}")
                return

            soup = BeautifulSoup(response.text, 'html.parser')
            page_text = soup.get_text()

            # 匹配带时间戳的 LRC 歌词行
            lrc_lines = re.findall(r'\[\d{2}:\d{2}\.\d{2}\].*', page_text)

            if lrc_lines:
                lrc_content = "\n".join(lrc_lines)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(lrc_content)
                print(f"成功下载: {safe_title}.lrc")
                return  # 下载成功，退出重试循环
            else:
                print(f"未能提取到LRC格式歌词: {safe_title}.lrc")
                return

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            print(f"连接超时 (第 {attempt + 1}/{max_retries} 次尝试)...")
            if attempt < max_retries - 1:
                time.sleep(3)  # 等待 3 秒后再次尝试
            else:
                print(f"下载歌曲【{safe_title}】失败: 连续 {max_retries} 次超时。")
        except Exception as e:
            print(f"下载歌曲【{safe_title}】遇到未知错误: {e}")
            return


def main():
    # 1. 获取歌曲列表
    songs = get_song_list(SINGER_URL)

    if not songs:
        print("未获取到歌曲列表，请检查网络或URL是否正确。")
        return

    # 2. 循环下载每首歌曲的歌词
    for idx, song in enumerate(songs, 1):
        print(f"[{idx}/{len(songs)}] ", end="")
        download_lrc(song['title'], song['url'])

        # 稍微拉长等待时间到 2 秒，温柔抓取防止被封
        time.sleep(2)


if __name__ == "__main__":
    main()