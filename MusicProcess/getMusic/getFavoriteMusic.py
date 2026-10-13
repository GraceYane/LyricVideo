"""读取哔哩哔哩收藏夹中的视频链接。"""

from __future__ import annotations

from dataclasses import dataclass
from http.cookiejar import MozillaCookieJar
from pathlib import Path

import requests


FAVORITE_LIST_API = "https://api.bilibili.com/x/v3/fav/resource/list"
DEFAULT_COOKIES_PATH = Path(__file__).resolve().parent / "www.bilibili.com_cookies.txt"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
}


@dataclass(frozen=True)
class FavoriteMusicItem:
    """收藏夹中的一个视频，保留批量任务需要的元数据。"""

    bvid: str
    title: str
    upper_name: str | None

    @property
    def url(self) -> str:
        return f"https://www.bilibili.com/video/{self.bvid}"


def _load_cookies(cookies_path: Path) -> MozillaCookieJar:
    """从 Netscape cookies.txt 中加载 B 站登录信息。"""
    if not cookies_path.is_file():
        raise FileNotFoundError(f"未找到 B 站 Cookie 文件：{cookies_path}")

    cookie_jar = MozillaCookieJar(str(cookies_path))
    try:
        cookie_jar.load(ignore_discard=True, ignore_expires=True)
    except OSError as error:
        raise RuntimeError(f"读取 B 站 Cookie 文件失败：{cookies_path}") from error
    except Exception as error:
        raise RuntimeError(f"B 站 Cookie 文件格式不正确：{cookies_path}") from error

    return cookie_jar


def getFavoriteMusicItems(
    media_id: int,
    max_count: int | None = None,
    cookies_path: str | Path | None = None,
) -> list[FavoriteMusicItem]:
    """
    获取一个 B 站收藏夹内的视频及其标题等元数据。

    Args:
        media_id: 收藏夹 ID，也就是收藏夹页面地址中的 ``fid``。
        max_count: 最多返回多少条；为 ``None`` 时读取整个收藏夹。
        cookies_path: Netscape cookies.txt 路径；默认复用本目录现有文件。

    Returns:
        按收藏夹接口返回顺序排列的视频信息列表。

    Raises:
        ValueError: 参数无效，或者 B 站接口返回业务错误。
        FileNotFoundError: Cookie 文件不存在。
        RuntimeError: 网络、Cookie 读取或接口数据解析失败。
    """
    if isinstance(media_id, bool) or not isinstance(media_id, int) or media_id <= 0:
        raise ValueError("media_id 必须是一个正整数")
    if max_count is not None and (
        isinstance(max_count, bool)
        or not isinstance(max_count, int)
        or max_count <= 0
    ):
        raise ValueError("max_count 必须是正整数或 None")

    resolved_cookies_path = (
        Path(cookies_path).expanduser().resolve()
        if cookies_path is not None
        else DEFAULT_COOKIES_PATH
    )

    session = requests.Session()
    session.headers.update(
        {
            **DEFAULT_HEADERS,
            "Referer": f"https://space.bilibili.com/favlist?fid={media_id}",
        }
    )
    session.cookies.update(_load_cookies(resolved_cookies_path))

    items: list[FavoriteMusicItem] = []
    seen_bvids: set[str] = set()
    page_number = 1

    try:
        while True:
            params = {
                "media_id": media_id,
                "pn": page_number,
                "ps": 20,
                "keyword": "",
                "order": "mtime",
                "type": 0,
                "tid": 0,
                "platform": "web",
            }

            try:
                response = session.get(
                    FAVORITE_LIST_API,
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
            except requests.RequestException as error:
                raise RuntimeError(
                    f"读取 B 站收藏夹失败（第 {page_number} 页）：{error}"
                ) from error

            try:
                payload = response.json()
            except requests.exceptions.JSONDecodeError as error:
                raise RuntimeError("B 站收藏夹接口返回了无法解析的数据") from error

            if payload.get("code") != 0:
                message = payload.get("message") or "未知错误"
                raise ValueError(
                    f"B 站收藏夹接口返回错误：{message}（code={payload.get('code')}）。"
                    "请检查收藏夹 ID 和 Cookie 是否有效。"
                )

            data = payload.get("data") or {}
            medias = data.get("medias") or []

            for media in medias:
                bvid = media.get("bvid")
                if not bvid or bvid in seen_bvids:
                    continue

                seen_bvids.add(bvid)
                upper = media.get("upper") or {}
                upper_name = str(upper.get("name") or "").strip() or None
                items.append(
                    FavoriteMusicItem(
                        bvid=str(bvid),
                        title=str(media.get("title") or bvid).strip(),
                        upper_name=upper_name,
                    )
                )

                if max_count is not None and len(items) >= max_count:
                    return items

            if not data.get("has_more") or not medias:
                break

            page_number += 1
    finally:
        session.close()

    return items


def getFavoriteMusic(
    media_id: int,
    max_count: int | None = None,
    cookies_path: str | Path | None = None,
) -> list[str]:
    """兼容原有调用方式，仅返回收藏夹视频链接列表。"""
    return [
        item.url
        for item in getFavoriteMusicItems(
            media_id=media_id,
            max_count=max_count,
            cookies_path=cookies_path,
        )
    ]
