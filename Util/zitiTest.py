import sys
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ── 核心配置 ──────────────────────────────────────────
FONT_NAME = "fanti.ttf"
FONT_SIZE = 40
LINE_HEIGHT = 60
IMG_WIDTH = 900
PADDING = 20

COLOR_BG = (30, 30, 30)  # 暗色背景
COLOR_TITLE = (180, 180, 60)  # 金黄色歌名
COLOR_TEXT = (255, 255, 255)  # 白色歌词


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """加载指定的字体文件"""
    current_dir = Path(__file__).resolve().parent
    font_path = current_dir.parent / "resources" / "fonts" / FONT_NAME
    if not font_path.exists():
        raise FileNotFoundError(f"字体文件不存在: {font_path}")
    return ImageFont.truetype(str(font_path), size)


def _parse_lrc_text(lrc_path: Path) -> list:
    """提取纯歌词文本（清洗掉时间戳标签和空行）"""
    lines = []
    with open(lrc_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            text = re.sub(r"\[[\d:.]+\]", "", line).strip()
            if text:
                lines.append(text)
    return lines


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list:
    """长歌词自动切分换行，防止超出图片边界"""
    lines = []
    current_line = ""
    for char in text:
        test_line = current_line + char
        width = font.getlength(test_line) if hasattr(font, "getlength") else font.getsize(test_line)[0]
        if width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = char
    if current_line:
        lines.append(current_line)
    return lines


def generate_single_lrc_image(target_name: str, output_dir: str = "lrc_font_test"):
    """精准定位单个 lrc 文件并输出对应的渲染图片"""
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent
    lrc_dir = project_root / "output" / "lrcCorrection"
    out_dir = current_dir / output_dir

    # 1. 确保目标歌词文件存在
    filename = target_name if target_name.endswith(".lrc") else f"{target_name}.lrc"
    lrc_path = lrc_dir / filename

    if not lrc_path.exists():
        print(f"❌ 错误：找不到文件 [{filename}]，请检查名称是否正确。")
        return

    # 2. 读取并解析歌词
    font = _load_font(FONT_SIZE)
    raw_lyrics = _parse_lrc_text(lrc_path)

    if not raw_lyrics:
        print(f"⚠ 提示：文件 [{filename}] 内没有找到有效的歌词文本。")
        return

    # 3. 处理文本自动折行并计算高度
    render_lines = []
    max_text_width = IMG_WIDTH - (PADDING * 2)
    for line in raw_lyrics:
        render_lines.extend(wrap_text(line, font, max_text_width))

    title_height = 50
    img_height = title_height + (len(render_lines) * LINE_HEIGHT) + PADDING

    # 4. 绘制图片
    img = Image.new("RGB", (IMG_WIDTH, img_height), COLOR_BG)
    draw = ImageDraw.Draw(img)

    # 画歌名标题
    draw.text((PADDING, 15), f"[{filename}]", font=font, fill=COLOR_TITLE)

    # 循环画歌词
    for idx, line in enumerate(render_lines):
        y_pos = title_height + (idx * LINE_HEIGHT)
        draw.text((PADDING, y_pos), line, font=font, fill=COLOR_TEXT)

    # 5. 保存并输出单条结果
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = f"{lrc_path.stem}_font_test.png"
    final_out_path = out_dir / out_name
    img.save(final_out_path)

    print(f"✓ 成功生成：{final_out_path.name}")


# ── 主入口流程 ──────────────────────────────────────────
if __name__ == "__main__":
    # 情况 A：如果用户在命令行传入了参数，则精准只输出那一个参数的歌曲
    if len(sys.argv) > 1:
        song_name = " ".join(sys.argv[1:])
        try:
            generate_single_lrc_image(song_name)
        except Exception as e:
            print(f"❌ 运行失败: {e}")

    # 情况 B：如果直接右键运行（无参数），则执行内置的这几个示例
    else:
        print("💡 [提示] 未检测到命令行参数，正在运行代码内配置的示例歌单...\n")

        # ─── 在这里修改/增减你想测试的歌名示例 ───
        examples = [
            "武家坡2021",
        ]
        # ─────────────────────────────────────────

        for sample in examples:
            try:
                generate_single_lrc_image(sample)
            except Exception as e:
                print(f"❌ 示例 [{sample}] 运行失败: {e}")

        print("\n✨ 所有示例处理完毕！")
        print("💡 小技巧：你可以在终端使用 `python zitiTest.py 歌名` 来单独生成指定图片。")