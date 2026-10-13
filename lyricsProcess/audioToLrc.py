"""单首音频转 LRC，以及 B 站收藏夹批量下载后生成 LRC。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from lyricsProcess.audioPreprocess import (
    PROJECT_ROOT,
    SUPPORTED_AUDIO_EXTENSIONS,
    clean_title_guess,
    inspect_audio,
    prepare_for_alignment,
)
from lyricsProcess.lyricsAligner import (
    align_document,
    source_timestamps_are_usable,
    transcript_to_lrc,
    transcribe_audio,
    use_source_timestamps,
)
from lyricsProcess.lyricsProvider import LyricsDocument, get_lyrics_document


DEFAULT_LRC_OUTPUT_DIR = PROJECT_ROOT / "output" / "lrcCorrection"
INVALID_OUTPUT_CHARS = r'<>:"/\\|?*'


@dataclass(frozen=True)
class LrcGenerationResult:
    audio_path: str
    lrc_path: str
    status: str
    mode: str
    lyrics_source: str | None
    confidence: float | None
    total_lines: int
    anchored_lines: int
    used_vocals: bool
    message: str


def _resolve_output_dir(output_dir: str | Path) -> Path:
    path = Path(output_dir).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _write_lrc(path: Path, content: str) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(content.rstrip() + "\n", encoding="utf-8-sig")
    temp_path.replace(path)


def _lrc_stem(audio_stem: str, title: str) -> str:
    """正常情况下与音频同名；文件名无有效文字时使用识别到的歌名。"""
    if any(character.isalnum() or "\u4e00" <= character <= "\u9fff" for character in audio_stem):
        return audio_stem
    cleaned = "".join("_" if character in INVALID_OUTPUT_CHARS else character for character in title)
    cleaned = cleaned.strip(" ._")
    return cleaned or "未知歌曲"


def generate_lrc_from_audio(
    audio_path: str | Path,
    *,
    title: str | None = None,
    artist: str | None = None,
    lyrics_path: str | Path | None = None,
    output_dir: str | Path = DEFAULT_LRC_OUTPUT_DIR,
    overwrite: bool = False,
    model_size: str = "medium",
    language: str = "zh",
    separate_vocals: bool | str = "auto",
) -> LrcGenerationResult:
    """从任意受支持音频生成同名 LRC，默认写入 output/lrcCorrection。"""
    info = inspect_audio(audio_path, title=title, artist=artist)
    target = _resolve_output_dir(output_dir) / f"{_lrc_stem(info.path.stem, info.title)}.lrc"
    if target.is_file() and not overwrite:
        return LrcGenerationResult(
            audio_path=str(info.path), lrc_path=str(target), status="skipped",
            mode="existing", lyrics_source=None, confidence=None,
            total_lines=0, anchored_lines=0, used_vocals=False,
            message="LRC 已存在，未覆盖",
        )

    document: LyricsDocument | None = None
    lyrics_error: Exception | None = None
    try:
        document = get_lyrics_document(
            info.title,
            artist=info.artist,
            audio_duration=info.duration,
            lyrics_path=lyrics_path,
        )
        print(
            f"[歌词] 候选：《{document.title}》"
            f"{f' - {document.artist}' if document.artist else ''} "
            f"({document.match_score:.0%})"
        )
    except (LookupError, RuntimeError, ValueError, FileNotFoundError) as error:
        lyrics_error = error
        print(f"[警告] 未取得可靠的完整歌词：{error}")

    if document is not None and source_timestamps_are_usable(document, info.duration):
        aligned = use_source_timestamps(document)
        used_vocals = False
    else:
        with prepare_for_alignment(info.path, separate_vocals=separate_vocals) as prepared:
            segments = transcribe_audio(
                prepared.path,
                model_size=model_size,
                language=language,
                prompt_lines=document.lines if document else None,
            )
            aligned = (
                align_document(
                    document,
                    segments,
                    info.duration,
                    voice_onset=prepared.voice_onset,
                )
                if document is not None
                else transcript_to_lrc(segments)
            )
            used_vocals = prepared.used_vocals

    _write_lrc(target, aligned.lrc_content)
    warning = f"；完整歌词获取失败：{lyrics_error}" if lyrics_error else ""
    anchor_coverage = (
        aligned.anchored_lines / aligned.total_lines
        if aligned.total_lines
        else 0.0
    )
    needs_review = (
        aligned.mode == "whisper_fallback"
        or (aligned.mode == "forced_alignment" and aligned.confidence < 0.55)
        or (aligned.mode == "forced_alignment" and anchor_coverage < 0.40)
    )
    status = "needs_review" if needs_review else "success"
    quality_message = (
        f"LRC 已生成，但建议人工检查（置信度 {aligned.confidence:.0%}，"
        f"语音锚点覆盖 {anchor_coverage:.0%}）"
        if needs_review
        else "LRC 生成成功"
    )
    return LrcGenerationResult(
        audio_path=str(info.path),
        lrc_path=str(target),
        status=status,
        mode=aligned.mode,
        lyrics_source=document.source if document else None,
        confidence=aligned.confidence,
        total_lines=aligned.total_lines,
        anchored_lines=aligned.anchored_lines,
        used_vocals=used_vocals,
        message=f"{quality_message}{warning}",
    )


def getLrcFromAudio(audio_path: str | Path, **kwargs: Any) -> str:
    """兼容项目命名风格的简洁入口，返回实际 LRC 路径。"""
    return generate_lrc_from_audio(audio_path, **kwargs).lrc_path


def _load_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_report(path: Path, report: dict[str, Any]) -> None:
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


def _find_existing_audio(audio_dir: Path, expected_stem: str) -> Path | None:
    """按下载器的目标文件名查找已存在的任意受支持音频格式。"""
    candidates = [
        item for item in audio_dir.iterdir()
        if item.is_file()
        and item.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
        and item.stem == expected_stem
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.stat().st_mtime)


def processFavoriteMusic(
    media_id: int,
    *,
    audio_output_dir: str | Path = "input",
    lrc_output_dir: str | Path = "output/lrcCorrection",
    max_count: int | None = None,
    skip_existing_audio: bool = True,
    overwrite_lrc: bool = False,
    model_size: str = "medium",
    separate_vocals: bool | str = "auto",
) -> dict[str, Any]:
    """收藏夹批量下载音频，再逐首生成 LRC；单首失败不会中断后续任务。"""
    from MusicProcess.getMusic.bill_bgm_lossless import (
        extract_bgm_lossless,
        extract_title_core,
        safe_filename,
    )
    from MusicProcess.getMusic.getFavoriteMusic import getFavoriteMusicItems

    audio_dir = _resolve_output_dir(audio_output_dir)
    lrc_dir = _resolve_output_dir(lrc_output_dir)
    report_path = lrc_dir / "batch_report.json"
    old_report = _load_report(report_path)
    old_items = {
        str(item.get("video_url")): item
        for item in old_report.get("items", [])
        if item.get("video_url")
    }

    favorite_items = getFavoriteMusicItems(media_id=media_id, max_count=max_count)
    print(f"[收藏夹] 共读取到 {len(favorite_items)} 个视频")
    report: dict[str, Any] = {
        "media_id": media_id,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "audio_output_dir": str(audio_dir),
        "lrc_output_dir": str(lrc_dir),
        "items": [],
        "summary": {},
    }

    for index, favorite in enumerate(favorite_items, 1):
        video_url = favorite.url
        print(f"\n[{index}/{len(favorite_items)}] 处理：{favorite.title}")
        item: dict[str, Any] = {
            "bvid": favorite.bvid,
            "video_url": video_url,
            "video_title": favorite.title,
            "upper_name": favorite.upper_name,
        }
        try:
            previous = old_items.get(video_url) or {}
            previous_audio = Path(str(previous.get("audio_path") or ""))
            if skip_existing_audio and previous_audio.is_file():
                audio_path = str(previous_audio.resolve())
                item["download_status"] = "reused"
                print(f"[跳过下载] 复用已下载音频：{audio_path}")
            else:
                expected_stem = safe_filename(extract_title_core(favorite.title))
                existing_audio = (
                    _find_existing_audio(audio_dir, expected_stem)
                    if skip_existing_audio
                    else None
                )
                if existing_audio:
                    audio_path = str(existing_audio.resolve())
                    item["download_status"] = "reused"
                    print(f"[跳过下载] 复用已下载音频：{audio_path}")
                else:
                    audio_path = extract_bgm_lossless(video_url, output_dir=str(audio_dir))
                    item["download_status"] = "success"
            item["audio_path"] = audio_path

            song_title, parsed_artist = clean_title_guess(favorite.title)

            lrc_result = generate_lrc_from_audio(
                audio_path,
                title=song_title,
                artist=parsed_artist,
                output_dir=lrc_dir,
                overwrite=overwrite_lrc,
                model_size=model_size,
                separate_vocals=separate_vocals,
            )
            item.update(asdict(lrc_result))
            label = "待检查" if lrc_result.status == "needs_review" else "成功"
            print(f"[{label}] {lrc_result.message}：{lrc_result.lrc_path}")
        except Exception as error:
            item.setdefault("download_status", "failed")
            item["status"] = "failed"
            item["error"] = f"{type(error).__name__}: {error}"
            print(f"[失败] 处理失败：{item['error']}")

        report["items"].append(item)
        _save_report(report_path, report)

    items = report["items"]
    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    report["summary"] = {
        "total": len(items),
        "audio_ready": sum(item.get("download_status") in {"success", "reused"} for item in items),
        "lrc_success": sum(item.get("status") == "success" for item in items),
        "lrc_needs_review": sum(item.get("status") == "needs_review" for item in items),
        "lrc_skipped": sum(item.get("status") == "skipped" for item in items),
        "failed": sum(item.get("status") == "failed" for item in items),
    }
    _save_report(report_path, report)
    summary = report["summary"]
    print(
        "\n[汇总] 批量处理完成："
        f"共 {summary['total']}，LRC 成功 {summary['lrc_success']}，"
        f"待检查 {summary['lrc_needs_review']}，跳过 {summary['lrc_skipped']}，"
        f"失败 {summary['failed']}"
    )
    print(f"[报告] 处理报告：{report_path}")
    return report
