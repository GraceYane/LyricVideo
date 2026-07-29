import os
import sys

from MusicProcess.getMusic.bili_bgm import extract_bgm
from MusicProcess.getMusic.hires import extract_bgmHires
from lyricsProcess.getLyrics import getLyrics
from vedioProcess.vedioProduceIOS1 import  vedioProduceIOS1

# 动态添加 lyricsProcess 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lyricsProcess"))


def main():
    print("🎵 网易云歌词下载 + Whisper 时间轴校准工具")
    print("=" * 45)

    if(1==1):
        mp3_paths = [


              "https://www.bilibili.com/video/BV1TnUkBSEKk/?spm_id_from=333.1387.favlist.content.click&vd_source=e29259537f15576fed15e2ba7fcc511a"

                     ]

        # 指定目录输出
        for i in mp3_paths:
            # extract_bgm(i,output_dir="./biblMusic")
            # extract_bgmHires(i, output_dir="./input")
            extract_bgm(i, output_dir="./input")

    # 待处理歌曲列表
    # npc song_list = ["颜色","春","广东爱情故事","这叫爱","吹梦到西洲","琵琶行","人生路漫漫"]  # 可继续添加
    song_list = ["借过一下"]  # 可继续添加

    for song in song_list:
        if(1==11):
            print(f"\n📥 步骤 1/2：下载歌词 《{song}》")
            getLyrics(song, include_translation=False, keep_timestamp=True)

            print(f"\n🎙️ 步骤 2/2：Whisper 解析并校准时间轴")
            # print(getLyricsWithTime(song))
            # print(correct_lrc_with_txt(song, enable_correct=False))

        # shift_single("阿楚姑娘", 2)
        if(1==11):
            print("-" * 45)
            video_path = vedioProduceIOS1(song)
            print(f"📥 视频已保存: {video_path}")



    print("\n🎉 全部流程结束！请查看 output/ 文件夹下的 .lrc 文件")



if __name__ == "__main__":
    main()
