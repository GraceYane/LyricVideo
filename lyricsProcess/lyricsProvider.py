"""从本地文件或网易云候选中选择完整歌词。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEARCH_API = "https://music.163.com/api/search/get/web"
LYRIC_API = "https://music.163.com/api/song/lyric"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://music.163.com/",
    "Accept": "application/json, text/plain, */*",
}
TIME_TAG_RE = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
METADATA_RE = re.compile(r"^\[(?:ar|ti|al|by|offset|re|ve|length):", re.IGNORECASE)
CREDIT_RE = re.compile(
    r"^(?:作词|作曲|编曲|制作人|监制|混音|录音|母带|吉他|贝斯|和声|统筹|出品)\s*[：:]"
)

# OpenCC 是首选；这个小型兜底表保证没有安装依赖时，常见歌曲候选仍能完成繁简匹配。
_FALLBACK_T2S = str.maketrans({
    "遺": "遗", "憾": "憾", "潔": "洁", "儀": "仪", "陳": "陈",
    "愛": "爱", "風": "风", "雲": "云", "飛": "飞", "夢": "梦",
    "聲": "声", "還": "还", "會": "会", "時": "时", "間": "间",
    "過": "过", "來": "来", "無": "无", "與": "与", "為": "为",
    "讓": "让", "這": "这", "裡": "里", "後": "后", "萬": "万",
    "長": "长", "開": "开", "關": "关", "難": "难", "歸": "归",
    "聽": "听", "說": "说", "錯": "错", "總": "总", "隨": "随",
    "誰": "谁", "該": "该", "覺": "觉", "實": "实", "際": "际",
    "會": "会", "盡": "尽", "真": "真", "貴": "贵", "別": "别",
    "淚": "泪", "體": "体", "機": "机", "應": "应", "記": "记",
    "點": "点", "歲": "岁", "處": "处", "樣": "样", "親": "亲",
    "舊": "旧", "願": "愿", "終": "终", "話": "话", "詞": "词",
})
_OPENCC = None
_OPENCC_CHECKED = False


def to_simplified(value: str) -> str:
    """统一转换成简体；候选比较和最终歌词输出都调用此函数。"""
    global _OPENCC, _OPENCC_CHECKED
    if not _OPENCC_CHECKED:
        try:
            from opencc import OpenCC
            _OPENCC = OpenCC("t2s")
        except ImportError:
            _OPENCC = None
        _OPENCC_CHECKED = True
    if _OPENCC is not None:
        return _OPENCC.convert(value)
    return value.translate(_FALLBACK_T2S)


@dataclass(frozen=True)
class LyricLine:
    text: str
    timestamp: float | None = None


@dataclass(frozen=True)
class LyricsDocument:
    title: str
    artist: str | None
    lines: tuple[LyricLine, ...]
    source: str
    match_score: float
    reference_duration: float | None = None


def _read_text(path: Path) -> str:
    last_error: UnicodeError | None = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeError as error:
            last_error = error
    raise RuntimeError(f"无法识别歌词文件编码：{path}") from last_error


def parse_lyrics_text(content: str) -> tuple[LyricLine, ...]:
    """同时解析标准 LRC 和每行一句的 TXT。"""
    result: list[LyricLine] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or METADATA_RE.match(line):
            continue
        tags = list(TIME_TAG_RE.finditer(line))
        text = to_simplified(TIME_TAG_RE.sub("", line).strip())
        if not text or CREDIT_RE.match(text):
            continue
        if tags:
            for tag in tags:
                fraction = tag.group(3) or "0"
                timestamp = int(tag.group(1)) * 60 + int(tag.group(2))
                timestamp += int(fraction) / (10 ** len(fraction))
                result.append(LyricLine(text=text, timestamp=timestamp))
        else:
            result.append(LyricLine(text=text))
    result.sort(key=lambda item: item.timestamp if item.timestamp is not None else float("inf"))
    return tuple(result)


def load_lyrics_file(path: str | Path, *, title: str | None = None) -> LyricsDocument:
    lyric_path = Path(path).expanduser()
    if not lyric_path.is_absolute():
        lyric_path = (PROJECT_ROOT / lyric_path).resolve()
    if not lyric_path.is_file():
        raise FileNotFoundError(f"找不到歌词文件：{lyric_path}")
    lines = parse_lyrics_text(_read_text(lyric_path))
    if not lines:
        raise ValueError(f"歌词文件中没有有效歌词：{lyric_path}")
    return LyricsDocument(
        title=to_simplified(title or lyric_path.stem),
        artist=None,
        lines=lines,
        source=f"local:{lyric_path}",
        match_score=1.0,
    )


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", to_simplified(value).lower())


def _similarity(left: str, right: str) -> float:
    a, b = _normalize(left), _normalize(right)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return min(len(a), len(b)) / max(len(a), len(b)) * 0.25 + 0.75
    return SequenceMatcher(None, a, b).ratio()


def _candidate_score(
    requested_title: str,
    requested_artist: str | None,
    audio_duration: float,
    song: dict,
) -> float:
    title_score = _similarity(requested_title, str(song.get("name") or ""))
    artists = "/".join(str(item.get("name") or "") for item in song.get("artists") or [])
    artist_score = _similarity(requested_artist or "", artists) if requested_artist else 0.0
    candidate_duration = float(song.get("duration") or 0) / 1000
    duration_delta = abs(candidate_duration - audio_duration) if candidate_duration else 999
    duration_score = max(0.0, 1.0 - duration_delta / max(20.0, audio_duration * 0.12))
    if requested_artist:
        if artist_score < 0.55:
            return -1.0
        return title_score * 0.70 + artist_score * 0.25 + duration_score * 0.05
    return title_score * 0.80 + duration_score * 0.20


def _find_exact_local(title: str) -> Path | None:
    # output/lrc 是旧版 Whisper 的粗识别结果，不能当作“完整正确歌词”。
    candidate = PROJECT_ROOT / "output" / "txt" / f"{title}.txt"
    if candidate.is_file():
        return candidate
    return None


def get_lyrics_document(
    title: str,
    *,
    artist: str | None = None,
    audio_duration: float,
    lyrics_path: str | Path | None = None,
    minimum_score: float = 0.58,
) -> LyricsDocument:
    """获取完整歌词；显式文件优先，其次精确本地文件，最后搜索在线候选。"""
    if lyrics_path is not None:
        return load_lyrics_file(lyrics_path, title=title)

    local_path = _find_exact_local(title)
    if local_path:
        return load_lyrics_file(local_path, title=title)

    query = " ".join(part for part in (title, artist) if part)
    try:
        response = requests.get(
            SEARCH_API,
            params={"s": query, "type": 1, "limit": 10, "offset": 0},
            headers=HEADERS,
            timeout=15,
        )
        response.raise_for_status()
        songs = (response.json().get("result") or {}).get("songs") or []
    except (requests.RequestException, ValueError) as error:
        raise RuntimeError(f"搜索歌词失败：{error}") from error
    if not songs:
        raise LookupError(f"没有找到歌曲《{title}》的歌词候选")

    ranked = sorted(
        ((_candidate_score(title, artist, audio_duration, song), song) for song in songs),
        key=lambda item: item[0],
        reverse=True,
    )
    score, song = ranked[0]
    if artist and score < 0:
        raise LookupError(f"没有找到歌手“{to_simplified(artist)}”演唱的《{to_simplified(title)}》")
    if score < minimum_score:
        raise LookupError(
            f"《{title}》的歌词候选置信度过低（{score:.0%}），为避免匹配错歌已停止自动选择"
        )

    try:
        response = requests.get(
            LYRIC_API,
            params={"id": song["id"], "lv": 1, "kv": 1, "tv": -1},
            headers=HEADERS,
            timeout=15,
        )
        response.raise_for_status()
        raw_lrc = ((response.json().get("lrc") or {}).get("lyric") or "").strip()
    except (requests.RequestException, ValueError, KeyError) as error:
        raise RuntimeError(f"下载歌词失败：{error}") from error
    lines = parse_lyrics_text(raw_lrc)
    if not lines:
        raise LookupError(f"歌曲《{song.get('name') or title}》没有可用歌词")

    artists = "/".join(
        to_simplified(str(item.get("name") or "")) for item in song.get("artists") or []
    )
    duration = float(song.get("duration") or 0) / 1000 or None
    return LyricsDocument(
        title=to_simplified(str(song.get("name") or title)),
        artist=artists or None,
        lines=lines,
        source=f"netease:{song.get('id')}",
        match_score=score,
        reference_duration=duration,
    )
