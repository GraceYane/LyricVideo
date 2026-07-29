# 🎵 LRC 歌词视频生成器 使用说明

仿 **iPhone 备忘录** 风格，黑底白字，随歌词时间轴逐行变为 **金色勾选圆** ✓

---

## 效果预览

- 黑色背景，顶栏金色文字
- 歌名作为大标题
- 前 N 行（前奏/副歌说明）用实心圆点 ●
- 歌词行：未播放 → 空心圆 ○，已播放 → 金色勾选 ✓
- 竖屏 1080×1920（抖音/快手标准）

---

## 安装依赖

```bash
pip install Pillow moviepy numpy
```

> moviepy 会自动使用系统 ffmpeg，如报错请先安装：  
> Windows: https://ffmpeg.org/download.html  并加入 PATH

---

## 使用方法

### 基本用法（最简单）
```bash
python lrc_video_generator.py --mp3 你的歌曲.mp3 --lrc 你的歌词.lrc --font "C:/Windows/Fonts/msyh.ttc"
```



```bash
python lrc_video_generator.py --mp3 天龙八部之宿敌.mp3 --lrc 天龙八部之宿敌.lrc 
```

生成的视频与 mp3 同目录，同名，扩展名 `.mp4`

---

### 完整参数

```bash
python lrc_video_generator.py \
  --mp3   天龙八部之宿敌.mp3 \
  --lrc   auto_generated.lrc \
  --output  output.mp4 \
  --header  "< 一个小橘子🍊" \
  --bullet  2
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--mp3` | MP3 音频文件路径 | **必填** |
| `--lrc` | LRC 歌词文件路径 | **必填** |
| `--output` | 输出视频路径 | 与 mp3 同名 .mp4 |
| `--header` | 顶栏文字 | `< 一个小橘子🍊` |
| `--bullet` | 前 N 行用实心圆点（前奏歌词行数） | `2` |

---

## LRC 格式说明

标准 LRC 格式，支持元信息标签：

```lrc
[ti:天龙八部之宿敌]
[ar:许嵩]
[al:专辑名]
[00:15.00]染指江湖结悲局
[00:19.50]无人逃得过宿命
[00:24.00]当恩怨各一半 我怎么圈揽
```

若 LRC 包含 `[ti:]` 和 `[ar:]` 标签，脚本会自动提取生成标题  
格式：`《歌名》-歌手名`

---

## 自定义样式

打开 `lrc_video_generator.py`，修改顶部配置区：

```python
VIDEO_W = 1080       # 宽度
VIDEO_H = 1920       # 高度（改为 1280 可做横屏）
FPS = 30

TITLE_FONT_SIZE = 62    # 标题字号
LYRIC_FONT_SIZE = 50    # 歌词字号
CIRCLE_DONE = (255, 195, 0)  # 金色，可改为其他颜色
```

---

## 常见问题

**Q: 字体显示方块 / 不显示中文？**  
A: 确保系统安装了中文字体。Windows 用户通常已有微软雅黑，无需操作。  
如有问题，在脚本 `load_font()` 函数的 `candidates_normal` 列表中添加你的字体路径。

**Q: moviepy 报 ffmpeg 错误？**  
A: 安装 ffmpeg 并加入系统 PATH，或运行：  
```bash
pip install imageio[ffmpeg]
```

**Q: 渲染很慢？**  
A: 正常，每帧都要重新绘制。5分钟歌曲大约需要 2-5 分钟渲染时间。  
可以先用短歌词测试。
