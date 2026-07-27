"""抖音下载器。

历史实现走 www.douyin.com/aweme/v1/web/aweme/detail + a_bogus 签名。
该 Web API 对非浏览器请求常返回 HTTP 200 空 body，进而触发：

    ('请求失败:', JSONDecodeError('Expecting value: line 1 column 1 (char 0)'))

修复方案（对齐 issue #162 评论 https://github.com/JefferyHcool/BiliNote/issues/162#issuecomment-4333005118）：
改用 iesdouyin.com/share/video/{id}/ 分享页。该页服务端渲染，把作品数据内嵌在
window._ROUTER_DATA / RENDER_DATA 中，无需 a_bogus、无需 Cookie。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.parse
from abc import ABC
from typing import Any, Dict, List, Optional, Union

import requests

from app.downloaders.base import Downloader
from app.enmus.note_enums import DownloadQuality
from app.models.audio_model import AudioDownloadResult
from app.utils.logger import get_logger
from app.utils.path_helper import get_data_dir

logger = get_logger(__name__)

DOUYIN_SHORT_URL = re.compile(r"https?://v\.douyin\.com/[\w\-]+/?", re.I)
DOUYIN_LONG_URL = re.compile(r"https?://(?:www\.)?douyin\.com/(?:video|note)/(\d+)", re.I)
IESDOUYIN_URL = re.compile(r"https?://(?:www\.)?iesdouyin\.com/share/(?:video|note)/(\d+)", re.I)
URL_IN_TEXT = re.compile(r"https?://[^\s<>\"']+")

# 桌面 UA：解析短链重定向
DESKTOP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.douyin.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 移动 UA：iesdouyin 分享页才带完整 SSR
MOBILE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/16.6 Mobile/15E148 Safari/604.1"
    ),
    "Referer": "https://www.douyin.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _first_url(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    urls = node.get("url_list") or node.get("urlList") or []
    if isinstance(urls, list) and urls:
        return str(urls[0])
    uri = node.get("uri") or node.get("url")
    return str(uri) if uri else ""


def _best_play_url(video: dict) -> str:
    """无水印播放地址：优先 bit_rate 最高档，再 play_addr。"""
    bit_rate = video.get("bit_rate") or video.get("bitRateList") or []
    if isinstance(bit_rate, list) and bit_rate:
        sorted_rates = sorted(
            bit_rate,
            key=lambda x: x.get("bit_rate", x.get("bitRate", 0)) if isinstance(x, dict) else 0,
            reverse=True,
        )
        for item in sorted_rates:
            if not isinstance(item, dict):
                continue
            play = item.get("play_addr") or item.get("playAddr")
            url = _first_url(play) if play else ""
            # bit_rate 里常把最高清放在 url_list 末尾
            if isinstance(play, dict):
                urls = play.get("url_list") or play.get("urlList") or []
                if urls:
                    url = str(urls[-1])
            if url:
                return url.replace("playwm", "play")

    for key in ("play_addr", "playAddr", "download_addr", "downloadAddr"):
        play = video.get(key)
        if not play:
            continue
        urls = []
        if isinstance(play, dict):
            urls = play.get("url_list") or play.get("urlList") or []
        if urls:
            return str(urls[-1]).replace("playwm", "play")
        url = _first_url(play)
        if url:
            return url.replace("playwm", "play")
    return ""


def _music_url(aweme: dict) -> str:
    music = aweme.get("music") or {}
    if not isinstance(music, dict):
        return ""
    play = music.get("play_url") or music.get("playUrl") or {}
    if isinstance(play, str) and play.startswith("http"):
        return play
    url = _first_url(play)
    if url:
        return url
    # 部分结构只有 uri
    uri = play.get("uri") if isinstance(play, dict) else None
    if isinstance(uri, str) and uri.startswith("http"):
        return uri
    return ""


def _parse_render_data(html: str) -> dict:
    """从分享页 HTML 解析 SSR JSON。"""
    match = re.search(
        r'<script[^>]+id=["\']RENDER_DATA["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.I,
    )
    if match:
        try:
            decoded = urllib.parse.unquote(match.group(1).strip())
            data = json.loads(decoded)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            pass

    # 非贪婪对大 JSON 不可靠；用括号平衡截取 window._ROUTER_DATA = {...}
    marker = "window._ROUTER_DATA"
    idx = html.find(marker)
    if idx < 0:
        marker = "window._ROUTER_DATA"
        idx = html.find("_ROUTER_DATA")
    if idx >= 0:
        eq = html.find("=", idx)
        if eq > 0:
            start = html.find("{", eq)
            if start > 0:
                depth = 0
                in_str = False
                escape = False
                end = -1
                for i in range(start, len(html)):
                    ch = html[i]
                    if in_str:
                        if escape:
                            escape = False
                        elif ch == "\\":
                            escape = True
                        elif ch == '"':
                            in_str = False
                        continue
                    if ch == '"':
                        in_str = True
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                if end > start:
                    try:
                        data = json.loads(html[start:end])
                        if isinstance(data, dict):
                            return data
                    except json.JSONDecodeError:
                        pass

    # 宽松正则兜底
    match = re.search(
        r"window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*;?\s*</script>",
        html,
        re.DOTALL,
    )
    if match:
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}


def _find_aweme_detail(data: dict) -> dict:
    """从 _ROUTER_DATA / RENDER_DATA 嵌套结构里取出作品对象。"""
    loader_data = data.get("loaderData") or {}
    if isinstance(loader_data, dict):
        for _key, value in loader_data.items():
            if not isinstance(value, dict):
                continue
            video_info_res = value.get("videoInfoRes") or value.get("video_info_res") or {}
            if isinstance(video_info_res, dict):
                item_list = video_info_res.get("item_list") or video_info_res.get("itemList")
                if isinstance(item_list, list) and item_list and isinstance(item_list[0], dict):
                    return item_list[0]

    if "aweme" in data and isinstance(data["aweme"], dict):
        detail = data["aweme"]
        if "detail" in detail and isinstance(detail["detail"], dict):
            return detail["detail"]
        return detail

    # 广度优先找 item_list / aweme_detail
    stack: List[Any] = [data]
    seen = 0
    while stack and seen < 200:
        seen += 1
        cur = stack.pop()
        if not isinstance(cur, dict):
            continue
        for k, v in cur.items():
            if k in ("item_list", "itemList") and isinstance(v, list) and v and isinstance(v[0], dict):
                return v[0]
            if k in ("aweme_detail", "awemeDetail") and isinstance(v, dict):
                return v
            if isinstance(v, (dict, list)):
                if isinstance(v, dict):
                    stack.append(v)
                else:
                    stack.extend(x for x in v if isinstance(x, dict))
    return {}


def _normalize_duration(raw: Any) -> float:
    try:
        val = float(raw or 0)
    except (TypeError, ValueError):
        return 0.0
    # 抖音常见毫秒
    if val > 1000:
        return val / 1000.0
    return val


class DouyinDownloader(Downloader, ABC):
    def __init__(self, cookie=None):
        super().__init__()
        self.session = requests.Session()
        self.session.headers.update(DESKTOP_HEADERS)

    @staticmethod
    def find_url(string: str) -> list:
        return URL_IN_TEXT.findall(string or "")

    def extract_video_id(self, url: str) -> str:
        """从分享文案 / 短链 / 长链中解析 aweme_id。"""
        text = (url or "").strip()
        if not text:
            return ""

        for pattern in (DOUYIN_LONG_URL, IESDOUYIN_URL):
            m = pattern.search(text)
            if m:
                return m.group(1)

        # 文案里的短链 / 任意 douyin 链接
        candidates = self.find_url(text)
        if not candidates and text.startswith("http"):
            candidates = [text]
        # 优先短链
        ordered = sorted(
            candidates,
            key=lambda u: (0 if "v.douyin.com" in u else 1, len(u)),
        )
        for link in ordered:
            m = DOUYIN_SHORT_URL.search(link) or (link if "v.douyin.com" in link else None)
            target = m.group(0) if hasattr(m, "group") else link
            try:
                resp = self.session.get(
                    target,
                    allow_redirects=True,
                    timeout=20,
                    headers=DESKTOP_HEADERS,
                )
                final = str(resp.url)
                for pattern in (DOUYIN_LONG_URL, IESDOUYIN_URL):
                    mm = pattern.search(final)
                    if mm:
                        return mm.group(1)
                # 有时仍停在短链页，再扫 Location 链
                for pattern in (DOUYIN_LONG_URL, IESDOUYIN_URL):
                    mm = pattern.search(resp.text or "")
                    if mm:
                        return mm.group(1)
            except requests.RequestException as e:
                logger.warning(f"解析抖音短链失败: {target} ({e})")
                continue

            for pattern in (DOUYIN_LONG_URL, IESDOUYIN_URL):
                mm = pattern.search(link)
                if mm:
                    return mm.group(1)
        return ""

    def fetch_video_info(self, video_url: str) -> dict:
        """拉取作品详情，返回兼容旧字段的包装：{"aweme_detail": {...}}。"""
        aweme_id = self.extract_video_id(video_url)
        if not aweme_id:
            raise ValueError("无法从链接中提取抖音视频 ID，请检查链接是否有效")

        share_url = f"https://www.iesdouyin.com/share/video/{aweme_id}/"
        logger.info(f"抖音分享页解析: id={aweme_id}, url={share_url}")
        try:
            resp = self.session.get(
                share_url,
                headers=MOBILE_HEADERS,
                timeout=30,
                allow_redirects=True,
            )
        except requests.RequestException as e:
            raise ValueError(f"请求抖音分享页失败: {e}") from e

        if resp.status_code != 200:
            raise ValueError(f"抖音分享页 HTTP {resp.status_code}，视频可能不存在或需登录")

        html = resp.text or ""
        if not html.strip():
            raise ValueError("抖音分享页返回空内容")

        render_data = _parse_render_data(html)
        if not render_data:
            raise ValueError(
                "无法解析抖音页面数据（缺少 _ROUTER_DATA/RENDER_DATA）。"
                "抖音可能已改版，或当前网络被拦截。"
            )

        aweme = _find_aweme_detail(render_data)
        if not aweme:
            raise ValueError("无法提取作品信息，视频可能为私密、已删除或页面结构变更")

        # 补齐 id
        if not aweme.get("aweme_id"):
            aweme["aweme_id"] = aweme.get("awemeId") or aweme_id

        return {"aweme_detail": aweme}

    def _resolve_output_dir(self, output_dir: Optional[str]) -> str:
        if output_dir:
            path = output_dir
        else:
            try:
                path = get_data_dir()
            except Exception:
                path = self.cache_data
        if not path:
            path = self.cache_data or "data"
        os.makedirs(path, exist_ok=True)
        return path

    def _build_meta(self, aweme: dict) -> Dict[str, Any]:
        aweme_id = str(aweme.get("aweme_id") or aweme.get("awemeId") or "")
        title = (
            aweme.get("item_title")
            or aweme.get("itemTitle")
            or aweme.get("desc")
            or aweme.get("preview_title")
            or aweme_id
            or "douyin_video"
        )
        title = str(title).strip().replace("\n", " ")[:80]

        video = aweme.get("video") or {}
        duration = _normalize_duration(
            video.get("duration")
            or aweme.get("duration")
            or (aweme.get("video") or {}).get("duration")
        )

        cover = ""
        for key in ("cover_original_scale", "origin_cover", "originCover", "cover", "dynamic_cover", "dynamicCover"):
            node = video.get(key) if isinstance(video, dict) else None
            cover = _first_url(node)
            if cover:
                break

        tags: List[str] = []
        for tag in aweme.get("video_tag") or aweme.get("videoTag") or []:
            if isinstance(tag, dict) and tag.get("tag_name"):
                tags.append(str(tag["tag_name"]))
        caption = aweme.get("caption") or aweme.get("desc") or ""
        raw_tags = (str(caption) + " " + " ".join(tags)).strip()

        return {
            "aweme_id": aweme_id,
            "title": title,
            "duration": duration,
            "cover_url": cover,
            "tags": raw_tags,
            "music_url": _music_url(aweme),
            "video_url": _best_play_url(video if isinstance(video, dict) else {}),
        }

    def _download_binary(self, url: str, dest: str, referer: str = "https://www.douyin.com/") -> None:
        headers = {
            **MOBILE_HEADERS,
            "Referer": referer,
        }
        with self.session.get(url, headers=headers, stream=True, timeout=120, allow_redirects=True) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(1024 * 256):
                    if chunk:
                        f.write(chunk)

    def _ffmpeg_to_mp3(self, src: str, dest: str) -> None:
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    src,
                    "-vn",
                    "-acodec",
                    "libmp3lame",
                    "-q:a",
                    "4",
                    dest,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError as e:
            raise ValueError("未找到 ffmpeg，无法从视频提取音频，请先安装并配置 FFMPEG_BIN_PATH") from e
        except subprocess.CalledProcessError as e:
            raise ValueError(f"ffmpeg 转码失败: {e}") from e

    def download(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
        quality: DownloadQuality = "fast",
        need_video: Optional[bool] = False,
        skip_download: bool = False,
    ) -> AudioDownloadResult:
        output_dir = self._resolve_output_dir(output_dir)
        logger.info(f"抖音下载: url={video_url!r}, dir={output_dir}, skip_download={skip_download}")

        payload = self.fetch_video_info(video_url)
        aweme = payload["aweme_detail"]
        meta = self._build_meta(aweme)
        aweme_id = meta["aweme_id"]
        if not aweme_id:
            raise ValueError("作品缺少 aweme_id")

        mp3_path = os.path.join(output_dir, f"{aweme_id}.mp3")
        mp4_path = os.path.join(output_dir, f"{aweme_id}.mp4")

        if skip_download:
            return AudioDownloadResult(
                file_path=mp3_path if os.path.exists(mp3_path) else "",
                title=meta["title"],
                duration=meta["duration"],
                cover_url=meta["cover_url"] or None,
                platform="douyin",
                video_id=aweme_id,
                raw_info={"tags": meta["tags"]},
                video_path=mp4_path if os.path.exists(mp4_path) else None,
            )

        # 已有音频缓存
        if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0:
            logger.info(f"复用已有抖音音频: {mp3_path}")
            return AudioDownloadResult(
                file_path=mp3_path,
                title=meta["title"],
                duration=meta["duration"],
                cover_url=meta["cover_url"] or None,
                platform="douyin",
                video_id=aweme_id,
                raw_info={"tags": meta["tags"]},
                video_path=mp4_path if os.path.exists(mp4_path) else None,
            )

        video_path_out: Optional[str] = None
        music_url = meta["music_url"]
        video_url_cdn = meta["video_url"]

        # 1) 优先背景音乐直链（体积小）
        if music_url:
            try:
                logger.info("下载抖音背景音乐…")
                self._download_binary(music_url, mp3_path)
                if os.path.getsize(mp3_path) > 0:
                    if need_video and video_url_cdn and not os.path.exists(mp4_path):
                        try:
                            self._download_binary(video_url_cdn, mp4_path)
                            video_path_out = mp4_path
                        except Exception as e:
                            logger.warning(f"视频附件下载失败（音频已成功）: {e}")
                    return AudioDownloadResult(
                        file_path=mp3_path,
                        title=meta["title"],
                        duration=meta["duration"],
                        cover_url=meta["cover_url"] or None,
                        platform="douyin",
                        video_id=aweme_id,
                        raw_info={"tags": meta["tags"]},
                        video_path=video_path_out or (mp4_path if os.path.exists(mp4_path) else None),
                    )
            except Exception as e:
                logger.warning(f"背景音乐下载失败，将回退视频抽音: {e}")
                if os.path.exists(mp3_path):
                    try:
                        os.remove(mp3_path)
                    except OSError:
                        pass

        # 2) 下视频再 ffmpeg 抽音
        if not video_url_cdn:
            raise ValueError("分享页未提供可下载的音频或视频地址")

        logger.info("下载抖音视频并提取音频…")
        self._download_binary(video_url_cdn, mp4_path)
        video_path_out = mp4_path
        self._ffmpeg_to_mp3(mp4_path, mp3_path)

        if need_video is False and os.path.exists(mp4_path):
            # 与历史行为接近：默认只要音频；保留 mp4 供截图链路，不强制删
            pass

        return AudioDownloadResult(
            file_path=mp3_path,
            title=meta["title"],
            duration=meta["duration"],
            cover_url=meta["cover_url"] or None,
            platform="douyin",
            video_id=aweme_id,
            raw_info={"tags": meta["tags"]},
            video_path=video_path_out,
        )

    def download_video(self, video_url: str, output_dir: Union[str, None] = None) -> str:
        output_dir = self._resolve_output_dir(output_dir)
        payload = self.fetch_video_info(video_url)
        meta = self._build_meta(payload["aweme_detail"])
        aweme_id = meta["aweme_id"]
        mp4_path = os.path.join(output_dir, f"{aweme_id}.mp4")
        if os.path.exists(mp4_path) and os.path.getsize(mp4_path) > 0:
            return mp4_path
        if not meta["video_url"]:
            raise ValueError("无法获取抖音视频下载地址")
        self._download_binary(meta["video_url"], mp4_path)
        return mp4_path


if __name__ == "__main__":
    dy = DouyinDownloader()
    print(
        dy.fetch_video_info(
            "https://www.iesdouyin.com/share/video/7123456789012345678/"
        )
    )
