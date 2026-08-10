import os
import sys

from lyricsProcess.audioToLrc import processFavoriteMusic
from lyricsProcess.getLyrics import getLyrics
from vedioProcess.vedioProduceIOS1 import  vedioProduceIOS1

# 动态添加 lyricsProcess 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lyricsProcess"))


def main():
    print("🎵 网易云歌词下载 + Whisper 时间轴校准工具")
    print("=" * 45)



    if(1==1):
        processFavoriteMusic(
            media_id=4081105827,
            audio_output_dir="./input",
            lrc_output_dir="./output/lrcCorrection",
            skip_existing_audio=False,
            overwrite_lrc=False,
            # medium 对中文演唱识别更稳；首次使用会下载对应模型。
            model_size="medium",
            separate_vocals="auto",
            max_count=1,
        )

    # 待处理歌曲列表
    # npc song_list = ["颜色","春","广东爱情故事","这叫爱","吹梦到西洲","琵琶行","人生路漫漫"]  # 可继续添加
    song_list = ["夏天的风"]  # 可继续添加

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
    print("\n🎉 测试dev分支改动")



if __name__ == "__main__":
    main()
