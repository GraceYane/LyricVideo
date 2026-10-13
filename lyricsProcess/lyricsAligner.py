"""将完整歌词按演唱顺序对齐到音频时间轴。"""

from __future__ import annotations

import re
import wave
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from lyricsProcess.lyricsProvider import LyricLine, LyricsDocument, to_simplified


@dataclass(frozen=True)
class RecognitionWord:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class RecognitionSegment:
    start: float
    end: float
    text: str
    words: tuple[RecognitionWord, ...] = ()


@dataclass(frozen=True)
class AlignmentResult:
    lrc_content: str
    mode: str
    confidence: float
    total_lines: int
    anchored_lines: int


_MODEL_CACHE: dict[str, object] = {}


def format_lrc_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes = int(seconds // 60)
    return f"{minutes:02d}:{seconds % 60:05.2f}"


def _normalize(text: str) -> str:
    value = to_simplified(text)
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", value.lower())


def _similarity(left: str, right: str) -> float:
    a, b = _normalize(left), _normalize(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _load_normalized_wav(audio_path: str | Path):
    """读取预处理后的 PCM16 WAV，避免 Whisper 再从 PATH 查找 FFmpeg。"""
    try:
        import numpy as np
    except ImportError as error:
        raise EnvironmentError("Whisper 音频读取需要 numpy") from error

    path = Path(audio_path)
    with wave.open(str(path), "rb") as wav_file:
        if wav_file.getnchannels() != 1 or wav_file.getsampwidth() != 2:
            raise ValueError("传给 Whisper 的临时 WAV 必须是单声道 PCM16")
        frames = wav_file.readframes(wav_file.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def source_timestamps_are_usable(document: LyricsDocument, audio_duration: float) -> bool:
    timed = [line for line in document.lines if line.timestamp is not None]
    if len(timed) < max(4, int(len(document.lines) * 0.8)):
        return False
    times = [float(line.timestamp) for line in timed if line.timestamp is not None]
    if any(current < previous for previous, current in zip(times, times[1:])):
        return False
    if times[-1] > audio_duration + 4 or times[0] > min(60, audio_duration * 0.35):
        return False
    if document.reference_duration is not None:
        allowed_delta = max(8.0, audio_duration * 0.04)
        if abs(document.reference_duration - audio_duration) > allowed_delta:
            return False
    elif audio_duration - times[-1] > max(45.0, audio_duration * 0.25):
        return False
    return True


def use_source_timestamps(document: LyricsDocument) -> AlignmentResult:
    lines = [
        f"[{format_lrc_time(float(line.timestamp))}]{line.text}"
        for line in document.lines
        if line.timestamp is not None
    ]
    return AlignmentResult(
        lrc_content="\n".join(lines),
        mode="source_lrc",
        confidence=document.match_score,
        total_lines=len(lines),
        anchored_lines=len(lines),
    )


def transcribe_audio(
    audio_path: str | Path,
    *,
    model_size: str = "medium",
    language: str = "zh",
    prompt_lines: tuple[LyricLine, ...] | None = None,
) -> list[RecognitionSegment]:
    """延迟加载 Whisper，避免没有该依赖时影响直接使用在线 LRC。"""
    try:
        import torch
        import whisper
    except ImportError as error:
        raise EnvironmentError(
            "当前 Python 环境没有 Whisper/Torch。可使用项目的 douyin2 环境运行，"
            "或安装 openai-whisper 和 torch。"
        ) from error

    if model_size not in _MODEL_CACHE:
        print(f"[识别] 正在加载 Whisper {model_size} 模型……")
        _MODEL_CACHE[model_size] = whisper.load_model(model_size)
    model = _MODEL_CACHE[model_size]
    prompt = None
    if prompt_lines:
        prompt = "，".join(line.text for line in prompt_lines[:18])[:800]
    result = model.transcribe(
        _load_normalized_wav(audio_path),
        language=language,
        verbose=False,
        temperature=0,
        word_timestamps=True,
        condition_on_previous_text=False,
        initial_prompt=prompt,
        fp16=bool(torch.cuda.is_available()),
    )
    segments: list[RecognitionSegment] = []
    for item in result.get("segments", []):
        text = to_simplified(str(item.get("text") or "").strip())
        if text:
            words = tuple(
                RecognitionWord(
                    start=float(word.get("start") or item.get("start") or 0),
                    end=float(word.get("end") or word.get("start") or item.get("end") or 0),
                    text=to_simplified(str(word.get("word") or "").strip()),
                )
                for word in item.get("words") or []
                if str(word.get("word") or "").strip()
            )
            segments.append(
                RecognitionSegment(
                    start=float(item.get("start") or 0),
                    end=float(item.get("end") or item.get("start") or 0),
                    text=text,
                    words=words,
                )
            )
    return segments


def _ordered_matches(
    lyrics: tuple[LyricLine, ...],
    segments: list[RecognitionSegment],
    max_group: int = 4,
) -> list[tuple[int, int, int, float]]:
    """动态规划匹配，保证歌词索引只能向后移动，适合重复副歌。"""
    segment_count, lyric_count = len(segments), len(lyrics)
    negative = float("-inf")
    scores = [[negative] * (lyric_count + 1) for _ in range(segment_count + 1)]
    previous: list[list[tuple[int, int, str, int, float] | None]] = [
        [None] * (lyric_count + 1) for _ in range(segment_count + 1)
    ]
    scores[0][0] = 0.0

    for segment_index in range(segment_count + 1):
        for lyric_index in range(lyric_count + 1):
            current = scores[segment_index][lyric_index]
            if current == negative:
                continue
            if segment_index < segment_count:
                candidate = current - 0.34
                if candidate > scores[segment_index + 1][lyric_index]:
                    scores[segment_index + 1][lyric_index] = candidate
                    previous[segment_index + 1][lyric_index] = (
                        segment_index, lyric_index, "skip_segment", 0, 0.0
                    )
            if lyric_index < lyric_count:
                candidate = current - 0.16
                if candidate > scores[segment_index][lyric_index + 1]:
                    scores[segment_index][lyric_index + 1] = candidate
                    previous[segment_index][lyric_index + 1] = (
                        segment_index, lyric_index, "skip_lyric", 0, 0.0
                    )
            if segment_index < segment_count and lyric_index < lyric_count:
                for group_size in range(1, min(max_group, lyric_count - lyric_index) + 1):
                    combined = "".join(
                        line.text for line in lyrics[lyric_index:lyric_index + group_size]
                    )
                    similarity = _similarity(segments[segment_index].text, combined)
                    if similarity < 0.16:
                        continue
                    candidate = current + (similarity - 0.18) * 2.2 + 0.12
                    target_lyric = lyric_index + group_size
                    if candidate > scores[segment_index + 1][target_lyric]:
                        scores[segment_index + 1][target_lyric] = candidate
                        previous[segment_index + 1][target_lyric] = (
                            segment_index, lyric_index, "match", group_size, similarity
                        )

    end_lyric = max(
        range(lyric_count + 1),
        key=lambda index: scores[segment_count][index] - (lyric_count - index) * 0.12,
    )
    matches: list[tuple[int, int, int, float]] = []
    state = (segment_count, end_lyric)
    while state != (0, 0):
        step = previous[state[0]][state[1]]
        if step is None:
            break
        prev_segment, prev_lyric, action, group_size, similarity = step
        if action == "match":
            matches.append((prev_segment, prev_lyric, group_size, similarity))
        state = (prev_segment, prev_lyric)
    matches.reverse()
    return matches


def _fill_timestamps(
    lyrics: tuple[LyricLine, ...],
    anchors: dict[int, float],
    audio_duration: float,
    *,
    voice_onset: float | None = None,
) -> list[float]:
    if not anchors:
        raise RuntimeError("Whisper 没有生成足够的歌词时间锚点")
    times: list[float | None] = [None] * len(lyrics)
    for index, value in anchors.items():
        times[index] = max(0.0, min(value, max(0.0, audio_duration - 0.05)))

    known = sorted(anchors)
    first = known[0]
    if first > 0:
        weights = [max(1, len(_normalize(lyrics[index].text))) for index in range(first)]
        estimated = sum(weights) / 3.2
        estimated_start = max(0.0, float(times[first]) - estimated)
        start = (
            min(float(times[first]) - 0.05, max(0.0, voice_onset - 0.15))
            if voice_onset is not None
            else estimated_start
        )
        total = sum(weights)
        cumulative = 0
        for index, weight in zip(range(first), weights):
            times[index] = start + (float(times[first]) - start) * cumulative / max(1, total)
            cumulative += weight

    for left, right in zip(known, known[1:]):
        if right - left <= 1:
            continue
        indices = list(range(left + 1, right))
        weights = [max(1, len(_normalize(lyrics[index].text))) for index in indices]
        total = sum(weights)
        cumulative = 0
        for index, weight in zip(indices, weights):
            cumulative += weight
            times[index] = float(times[left]) + (
                float(times[right]) - float(times[left])
            ) * cumulative / (total + weights[-1])

    last = known[-1]
    if last < len(lyrics) - 1:
        indices = list(range(last + 1, len(lyrics)))
        weights = [max(1, len(_normalize(lyrics[index].text))) for index in indices]
        estimated_end = float(times[last]) + sum(weights) / 3.2
        end = min(max(float(times[last]) + 0.1, estimated_end), max(0.0, audio_duration - 0.05))
        total = sum(weights)
        cumulative = 0
        for index, weight in zip(indices, weights):
            cumulative += weight
            times[index] = float(times[last]) + (end - float(times[last])) * cumulative / max(1, total)

    final: list[float] = []
    previous_time = -0.01
    for value in times:
        current = float(value if value is not None else previous_time + 0.05)
        current = max(current, previous_time + 0.01)
        current = min(current, max(0.0, audio_duration - 0.01))
        final.append(current)
        previous_time = current
    return final


def _word_line_anchors(
    segment: RecognitionSegment,
    group: tuple[LyricLine, ...],
) -> dict[int, float]:
    """用 Whisper 逐词时间为一段中的多行歌词确定真实起点。"""
    if not segment.words:
        return {}
    recognized = ""
    recognized_times: list[float] = []
    for word in segment.words:
        normalized = _normalize(word.text)
        recognized += normalized
        recognized_times.extend([word.start] * len(normalized))
    lyric_parts = [_normalize(line.text) for line in group]
    lyric_text = "".join(lyric_parts)
    if not recognized or not lyric_text:
        return {}

    mapping: dict[int, float] = {}
    matcher = SequenceMatcher(None, recognized, lyric_text)
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            recognized_index = block.a + offset
            lyric_index = block.b + offset
            if recognized_index < len(recognized_times):
                mapping[lyric_index] = recognized_times[recognized_index]

    result: dict[int, float] = {}
    boundary = 0
    for line_index, part in enumerate(lyric_parts):
        matches = [
            (index, timestamp)
            for index, timestamp in mapping.items()
            if boundary <= index < boundary + len(part)
        ]
        if matches:
            first_index, first_time = min(matches, key=lambda item: item[0])
            missing_prefix = first_index - boundary
            result[line_index] = max(segment.start, first_time - missing_prefix / 3.5)
        boundary += len(part)
    return result


def _source_prior_anchors(
    document: LyricsDocument,
    speech_anchors: dict[int, float],
) -> dict[int, float]:
    """用可靠语音锚点拟合在线 LRC 的比例和偏移，补足漏识别歌词。"""
    pairs = [
        (float(document.lines[index].timestamp), audio_time)
        for index, audio_time in speech_anchors.items()
        if document.lines[index].timestamp is not None
    ]
    if len(pairs) < 2:
        return {}

    source_mean = sum(item[0] for item in pairs) / len(pairs)
    audio_mean = sum(item[1] for item in pairs) / len(pairs)
    denominator = sum((source - source_mean) ** 2 for source, _ in pairs)
    if denominator <= 1e-6:
        return {}
    scale = sum(
        (source - source_mean) * (audio - audio_mean)
        for source, audio in pairs
    ) / denominator
    scale = min(1.15, max(0.85, scale))
    offsets = sorted(audio - scale * source for source, audio in pairs)
    offset = offsets[len(offsets) // 2]
    residuals = sorted(abs(scale * source + offset - audio) for source, audio in pairs)
    median_residual = residuals[len(residuals) // 2]
    if median_residual > 3.5:
        return {}

    return {
        index: max(0.0, scale * float(line.timestamp) + offset)
        for index, line in enumerate(document.lines)
        if line.timestamp is not None and index not in speech_anchors
    }


def align_document(
    document: LyricsDocument,
    segments: list[RecognitionSegment],
    audio_duration: float,
    *,
    voice_onset: float | None = None,
) -> AlignmentResult:
    if not segments:
        raise RuntimeError("Whisper 未识别到有效人声，无法生成歌词时间轴")
    matches = _ordered_matches(document.lines, segments)
    reliable = [item for item in matches if item[3] >= 0.28]
    if not reliable:
        raise RuntimeError("识别结果与完整歌词相似度过低，可能选错了歌曲版本")

    anchors: dict[int, float] = {}
    similarities: list[float] = []
    for segment_index, lyric_index, group_size, similarity in reliable:
        segment = segments[segment_index]
        group = document.lines[lyric_index:lyric_index + group_size]
        word_anchors = _word_line_anchors(segment, group)
        weights = [max(1, len(_normalize(line.text))) for line in group]
        total = sum(weights)
        cumulative = 0
        duration = max(0.1, segment.end - segment.start)
        for offset, weight in enumerate(weights):
            anchors[lyric_index + offset] = word_anchors.get(
                offset,
                segment.start + duration * cumulative / max(1, total),
            )
            cumulative += weight
        similarities.append(similarity)

    speech_anchor_count = len(anchors)
    anchors.update(_source_prior_anchors(document, anchors))
    if voice_onset is not None and 0 in anchors:
        # 在线 LRC 的版本差异可能把第一句推到前奏中；首句不能早于分离人声的起点。
        anchors[0] = max(anchors[0], voice_onset)
    times = _fill_timestamps(
        document.lines,
        anchors,
        audio_duration,
        voice_onset=voice_onset,
    )
    lrc_lines = [
        f"[{format_lrc_time(timestamp)}]{line.text}"
        for timestamp, line in zip(times, document.lines)
    ]
    return AlignmentResult(
        lrc_content="\n".join(lrc_lines),
        mode="forced_alignment",
        confidence=sum(similarities) / len(similarities),
        total_lines=len(lrc_lines),
        anchored_lines=speech_anchor_count,
    )


def transcript_to_lrc(
    segments: list[RecognitionSegment],
) -> AlignmentResult:
    """没有任何完整歌词来源时的最后兜底。"""
    if not segments:
        raise RuntimeError("未识别到有效人声")
    lines = [
        f"[{format_lrc_time(item.start)}]{to_simplified(item.text.strip())}"
        for item in segments
    ]
    return AlignmentResult(
        lrc_content="\n".join(lines),
        mode="whisper_fallback",
        confidence=0.35,
        total_lines=len(lines),
        anchored_lines=len(lines),
    )
