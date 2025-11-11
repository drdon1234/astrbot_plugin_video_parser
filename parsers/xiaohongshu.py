# -*- coding: utf-8 -*-
import asyncio
import json
import os
import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from urllib.parse import unquote

import aiohttp

from .base_parser import BaseVideoParser


ANDROID_UA = (
    "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/142.0.0.0 Mobile Safari/537.36 Edg/142.0.0.0"
)


class XiaohongshuParser(BaseVideoParser):
    """小红书视频解析器。"""

    def __init__(
        self,
        max_media_size_mb: float = 0.0,
        large_media_threshold_mb: float = 50.0,
        cache_dir: str = "/app/sharedFolder/video_parser/cache",
        pre_download_all_media: bool = False,
        max_concurrent_downloads: int = 3
    ):
        """初始化小红书解析器。

        Args:
            max_media_size_mb: 最大允许的媒体大小(MB)
            large_media_threshold_mb: 大媒体阈值(MB)
            cache_dir: 媒体缓存目录
            pre_download_all_media: 是否预先下载所有媒体到本地
            max_concurrent_downloads: 最大并发下载数
        """
        super().__init__(
            "小红书",
            max_media_size_mb,
            large_media_threshold_mb,
            cache_dir,
            pre_download_all_media,
            max_concurrent_downloads
        )
        self.headers = {
            "User-Agent": ANDROID_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        self.semaphore = asyncio.Semaphore(10)

    def can_parse(self, url: str) -> bool:
        """判断是否可以解析此URL。

        Args:
            url: 视频链接

        Returns:
            如果可以解析返回True，否则返回False
        """
        if not url:
            return False
        url_lower = url.lower()
        if 'xhslink.com' in url_lower or 'xiaohongshu.com' in url_lower:
            return True
        return False

    def extract_links(self, text: str) -> List[str]:
        """从文本中提取小红书链接。

        Args:
            text: 输入文本

        Returns:
            小红书链接列表
        """
        result_links = []
        seen_urls = set()
        short_pattern = r'https?://xhslink\.com/[^\s<>"\'()]+'
        short_links = re.findall(short_pattern, text, re.IGNORECASE)
        for link in short_links:
            normalized = link.lower()
            if normalized not in seen_urls:
                seen_urls.add(normalized)
                result_links.append(link)
        long_pattern = (
            r'https?://(?:www\.)?xiaohongshu\.com/'
            r'(?:explore|discovery/item)/[^\s<>"\'()]+'
        )
        long_links = re.findall(long_pattern, text, re.IGNORECASE)
        for link in long_links:
            normalized = link.lower()
            if normalized not in seen_urls:
                seen_urls.add(normalized)
                if not link.startswith("http://") and not link.startswith("https://"):
                    link = "https://" + link
                result_links.append(link)
        return result_links

    async def _get_redirect_url(
        self,
        session: aiohttp.ClientSession,
        short_url: str
    ) -> str:
        """获取短链接重定向后的完整URL。

        Args:
            session: aiohttp会话
            short_url: 短链接URL

        Returns:
            重定向后的完整URL

        Raises:
            RuntimeError: 当无法获取重定向URL时
        """
        async with session.get(
            short_url,
            headers=self.headers,
            allow_redirects=False
        ) as response:
            if response.status == 302:
                redirect_url = response.headers.get("Location", "")
                if not redirect_url:
                    raise RuntimeError("无法获取重定向URL")
                return unquote(redirect_url)
            else:
                raise RuntimeError(
                    f"无法获取重定向URL，状态码: {response.status}"
                )

    async def _fetch_page(
        self,
        session: aiohttp.ClientSession,
        url: str
    ) -> str:
        """获取页面HTML内容。

        Args:
            session: aiohttp会话
            url: 页面URL

        Returns:
            HTML内容

        Raises:
            RuntimeError: 当无法获取页面内容时
        """
        async with session.get(url, headers=self.headers) as response:
            if response.status == 200:
                return await response.text()
            else:
                raise RuntimeError(
                    f"无法获取页面内容，状态码: {response.status}"
                )

    def _extract_initial_state(self, html: str) -> dict:
        """从HTML中提取window.__INITIAL_STATE__的JSON数据。

        Args:
            html: HTML内容

        Returns:
            JSON数据字典

        Raises:
            RuntimeError: 当无法提取JSON数据时
        """
        pattern = r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>'
        match = re.search(pattern, html, re.DOTALL)

        if match:
            json_str = match.group(1)
            json_str = re.sub(r'\bundefined\b', 'null', json_str)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        start_marker = 'window.__INITIAL_STATE__'
        start_idx = html.find(start_marker)
        if start_idx == -1:
            raise RuntimeError("无法找到window.__INITIAL_STATE__数据")

        json_start = html.find('{', start_idx)
        if json_start == -1:
            raise RuntimeError("无法找到JSON开始位置")

        script_end = html.find('</script>', start_idx)
        if script_end == -1:
            script_end = len(html)

        brace_count = 0
        json_end = json_start
        in_string = False
        escape_next = False
        in_single_quote = False

        search_end = min(script_end, len(html))
        for i in range(json_start, search_end):
            char = html[i]

            if escape_next:
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                continue

            if char == '"' and not escape_next and not in_single_quote:
                in_string = not in_string
                continue

            if char == "'" and not escape_next and not in_string:
                in_single_quote = not in_single_quote
                continue

            if not in_string and not in_single_quote:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i + 1
                        break

        if brace_count != 0:
            raise RuntimeError("无法找到完整的JSON对象")

        json_str = html[json_start:json_end]
        json_str = re.sub(r'\bundefined\b', 'null', json_str)

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            error_pos = getattr(e, 'pos', 0)
            start_debug = max(0, error_pos - 200)
            end_debug = min(len(json_str), error_pos + 200)
            error_msg = (
                f"JSON解析失败: {e}\n"
                f"错误位置: {error_pos}\n"
                f"附近内容: {json_str[start_debug:end_debug]}"
            )
            raise RuntimeError(error_msg)

    def _parse_note_data(self, data: dict) -> dict:
        """从JSON数据中提取所需信息。

        Args:
            data: JSON数据字典

        Returns:
            包含笔记信息的字典

        Raises:
            RuntimeError: 当数据提取失败时
        """
        try:
            note_data = data["noteData"]["data"]["noteData"]
            user_data = note_data["user"]

            note_type = note_data.get("type", "normal")
            title = note_data.get("title", "")
            desc = note_data.get("desc", "")

            author_name = user_data.get("nickName", "")
            author_id = user_data.get("userId", "")

            timestamp = note_data.get("time", 0)
            if timestamp:
                dt = datetime.fromtimestamp(timestamp / 1000)
                publish_time = dt.strftime("%Y-%m-%d")
            else:
                publish_time = ""

            video_url = ""
            image_urls = []

            if note_type == "video":
                video_info = note_data.get("video", {})
                if video_info:
                    video_url = (
                        video_info.get("media", {})
                        .get("stream", {})
                        .get("h264", [{}])[0]
                        .get("masterUrl", "")
                    )
                    if not video_url:
                        video_url = (
                            video_info.get("media", {})
                            .get("stream", {})
                            .get("h264", [{}])[0]
                            .get("backupUrl", "")
                        )
                    if not video_url:
                        video_url = (
                            video_info.get("media", {})
                            .get("stream", {})
                            .get("h264", [{}])[0]
                            .get("url", "")
                        )

                if not video_url:
                    stream_info = note_data.get("stream", {})
                    if stream_info:
                        video_url = (
                            stream_info.get("h264", [{}])[0].get("masterUrl", "")
                        )
                        if not video_url:
                            video_url = (
                                stream_info.get("h264", [{}])[0].get("backupUrl", "")
                            )
                        if not video_url:
                            video_url = (
                                stream_info.get("h264", [{}])[0].get("url", "")
                            )

                if not video_url:
                    def find_video_url(obj, depth=0):
                        if depth > 5:
                            return ""
                        if isinstance(obj, dict):
                            for key, value in obj.items():
                                if isinstance(value, str) and (
                                    ".mp4" in value or "sns-video" in value
                                ):
                                    return value
                                result = find_video_url(value, depth + 1)
                                if result:
                                    return result
                        elif isinstance(obj, list):
                            for item in obj:
                                result = find_video_url(item, depth + 1)
                                if result:
                                    return result
                        return ""

                    video_url = find_video_url(note_data)

                if video_url and video_url.startswith("http://"):
                    video_url = video_url.replace("http://", "https://", 1)
            else:
                image_list = note_data.get("imageList", [])
                image_urls = [
                    img.get("url", "") for img in image_list if img.get("url")
                ]

            return {
                "type": note_type,
                "title": title,
                "desc": desc,
                "author_name": author_name,
                "author_id": author_id,
                "publish_time": publish_time,
                "video_url": video_url,
                "image_urls": image_urls,
            }
        except KeyError as e:
            raise RuntimeError(f"数据提取失败，缺少字段: {e}")

    def _extract_media_id(self, url: str) -> str:
        """从URL中提取媒体ID。

        Args:
            url: 小红书URL

        Returns:
            媒体ID，如果无法提取则返回"xiaohongshu"
        """
        match = re.search(r'/([a-zA-Z0-9]+)(?:\?|$)', url)
        if match:
            return match.group(1)
        return "xiaohongshu"

    async def get_video_size(
        self,
        video_url: str,
        session: aiohttp.ClientSession,
        referer: str = None
    ) -> Optional[float]:
        """获取视频文件大小(MB)（小红书专用，需要Referer请求头）。

        Args:
            video_url: 视频URL
            session: aiohttp会话
            referer: 引用页面URL（可选，默认使用xiaohongshu.com）

        Returns:
            视频大小(MB)，如果无法获取返回None
        """
        try:
            headers = self.headers.copy()
            if referer:
                headers["Referer"] = referer
            else:
                headers["Referer"] = 'https://www.xiaohongshu.com/'
            async with session.head(
                video_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                content_range = resp.headers.get("Content-Range")
                if content_range:
                    match = re.search(r'/\s*(\d+)', content_range)
                    if match:
                        size_bytes = int(match.group(1))
                        size_mb = size_bytes / (1024 * 1024)
                        return size_mb
                content_length = resp.headers.get("Content-Length")
                if content_length:
                    size_bytes = int(content_length)
                    size_mb = size_bytes / (1024 * 1024)
                    return size_mb
            headers["Range"] = "bytes=0-1"
            async with session.get(
                video_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                content_range = resp.headers.get("Content-Range")
                if content_range:
                    match = re.search(r'/\s*(\d+)', content_range)
                    if match:
                        size_bytes = int(match.group(1))
                        size_mb = size_bytes / (1024 * 1024)
                        return size_mb
                content_length = resp.headers.get("Content-Length")
                if content_length:
                    size_bytes = int(content_length)
                    size_mb = size_bytes / (1024 * 1024)
                    return size_mb
        except Exception:
            pass
        return None

    async def get_image_size(
        self,
        image_url: str,
        session: aiohttp.ClientSession,
        headers: dict = None
    ) -> Optional[float]:
        """获取图片文件大小(MB)（小红书专用，需要Referer请求头）。

        Args:
            image_url: 图片URL
            session: aiohttp会话
            headers: 请求头（可选，如果不提供则使用默认headers）

        Returns:
            图片大小(MB)，如果无法获取返回None
        """
        try:
            request_headers = headers or self.headers.copy()
            if "Referer" not in request_headers:
                request_headers["Referer"] = 'https://www.xiaohongshu.com/'
            async with session.head(
                image_url,
                headers=request_headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                content_range = resp.headers.get("Content-Range")
                if content_range:
                    match = re.search(r'/\s*(\d+)', content_range)
                    if match:
                        size_bytes = int(match.group(1))
                        size_mb = size_bytes / (1024 * 1024)
                        return size_mb
                content_length = resp.headers.get("Content-Length")
                if content_length:
                    size_bytes = int(content_length)
                    size_mb = size_bytes / (1024 * 1024)
                    return size_mb
        except Exception:
            pass
        return None

    def _normalize_url(self, url: str) -> Optional[str]:
        """规范化小红书URL，支持短链接和长链接。

        Args:
            url: 原始URL

        Returns:
            规范化后的URL，如果是短链接返回None（表示需要重定向）
        """
        if "xhslink.com" in url:
            return None
        if "www.xiaohongshu.com" in url:
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "https://" + url
            return url
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return "https://" + url

    async def _parse_video(
        self,
        session: aiohttp.ClientSession,
        url: str,
        note_info: dict,
        downloaded_files: List[str],
        page_url: str = None
    ) -> Optional[Dict[str, Any]]:
        """解析视频。

        Args:
            session: aiohttp会话
            url: 小红书链接（原始URL，可能是短链接）
            note_info: 笔记信息字典
            downloaded_files: 下载的文件列表（用于跟踪清理）
            page_url: 完整的小红书页面URL，用于下载时的referer

        Returns:
            解析结果字典，如果解析失败返回None

        Raises:
            RuntimeError: 当本地缓存路径无效时
        """
        video_url = note_info.get("video_url")
        if not video_url:
            return None

        # 使用完整的小红书页面URL作为referer，如果没有则使用原始URL
        referer_url = page_url if page_url else url

        video_size = await self.get_video_size(video_url, session, referer=referer_url)
        if self.max_media_size_mb > 0 and video_size is not None:
            if video_size > self.max_media_size_mb:
                return None

        has_large_video = False
        video_file_path = None
        if (self.large_media_threshold_mb > 0 and
                video_size is not None and
                video_size > self.large_media_threshold_mb):
            if not self.cache_dir_available:
                raise RuntimeError("解析失败：本地缓存路径无效")
            if (self.max_media_size_mb <= 0 or
                    video_size <= self.max_media_size_mb):
                has_large_video = True
                video_id = self._extract_media_id(url)
                video_file_path = await self._download_large_media_to_cache(
                    session,
                    video_url,
                    video_id,
                    index=0,
                    headers=self.headers,
                    is_video=True,
                    referer=referer_url
                )
                if video_file_path:
                    downloaded_files.append(video_file_path)

        author = note_info.get("author_name", "")
        author_id = note_info.get("author_id", "")
        if author and author_id:
            author = f"{author}(主页id:{author_id})"
        elif author:
            author = author
        elif author_id:
            author = f"(主页id:{author_id})"

        parse_result = {
            "video_url": url,
            "title": note_info.get("title", ""),
            "desc": note_info.get("desc", ""),
            "author": author,
            "timestamp": note_info.get("publish_time", ""),
            "direct_url": video_url,
            "file_size_mb": video_size
        }

        if has_large_video:
            parse_result['force_separate_send'] = True
            if video_file_path:
                parse_result['video_files'] = [
                    {'file_path': video_file_path}
                ]

        if (self.pre_download_all_media and
                self.cache_dir_available and
                not has_large_video):
            media_items = []
            if video_url:
                video_id = self._extract_media_id(url)
                media_items.append({
                    'url': video_url,
                    'media_id': video_id,
                    'index': 0,
                    'is_video': True,
                    'headers': self.headers,
                    'referer': referer_url
                })
            if media_items:
                download_results = await self._pre_download_media(
                    session,
                    media_items,
                    self.headers
                )
                for download_result in download_results:
                    if (download_result.get('success') and
                            download_result.get('file_path')):
                        parse_result['video_files'] = [{
                            'file_path': download_result['file_path']
                        }]
                        parse_result['direct_url'] = None
                        downloaded_files.append(
                            download_result['file_path']
                        )
                        break

        return parse_result

    async def _parse_gallery(
        self,
        session: aiohttp.ClientSession,
        url: str,
        note_info: dict,
        downloaded_files: List[str],
        page_url: str = None
    ) -> Optional[Dict[str, Any]]:
        """解析图集。

        Args:
            session: aiohttp会话
            url: 小红书链接（原始URL，可能是短链接）
            note_info: 笔记信息字典
            downloaded_files: 下载的文件列表（用于跟踪清理）
            page_url: 完整的小红书页面URL，用于下载时的referer

        Returns:
            解析结果字典，如果解析失败返回None

        Raises:
            RuntimeError: 当本地缓存路径无效时
        """
        images = note_info.get("image_urls", [])
        if not images:
            return None

        if not self.cache_dir_available:
            raise RuntimeError("解析失败：本地缓存路径无效")

        # 使用完整的小红书页面URL作为referer，如果没有则使用原始URL
        referer_url = page_url if page_url else url

        author = note_info.get("author_name", "")
        author_id = note_info.get("author_id", "")
        if author and author_id:
            author = f"{author}(主页id:{author_id})"
        elif author:
            author = author
        elif author_id:
            author = f"(主页id:{author_id})"

        image_files = []
        if (self.pre_download_all_media and
                self.cache_dir_available):
            media_items = []
            for idx, img_url in enumerate(images):
                if (img_url and
                        isinstance(img_url, str) and
                        img_url.startswith(('http://', 'https://'))):
                    # 确保headers包含正确的referer
                    image_headers = self.headers.copy()
                    image_headers["Referer"] = referer_url
                    image_size = await self.get_image_size(
                        img_url,
                        session,
                        headers=image_headers
                    )
                    if (self.max_media_size_mb > 0 and
                            image_size is not None):
                        if image_size > self.max_media_size_mb:
                            continue
                    image_id = self._extract_media_id(url)
                    media_items.append({
                        'url': img_url,
                        'media_id': image_id,
                        'index': idx,
                        'is_video': False,
                        'headers': self.headers,
                        'referer': referer_url,
                        'default_referer': 'https://www.xiaohongshu.com/'
                    })
            if media_items:
                download_results = await self._pre_download_media(
                    session,
                    media_items,
                    self.headers
                )
                for download_result in download_results:
                    if (download_result.get('success') and
                            download_result.get('file_path')):
                        image_files.append(download_result['file_path'])
                        downloaded_files.append(download_result['file_path'])
                if image_files:
                    images = []
        else:
            for idx, img_url in enumerate(images):
                if (not img_url or
                        not isinstance(img_url, str) or
                        not img_url.startswith(('http://', 'https://'))):
                    continue
                # 确保headers包含正确的referer
                image_headers = self.headers.copy()
                image_headers["Referer"] = referer_url
                image_size = await self.get_image_size(
                    img_url,
                    session,
                    headers=image_headers
                )
                if (self.max_media_size_mb > 0 and
                        image_size is not None):
                    if image_size > self.max_media_size_mb:
                        continue
                image_file = None
                if (self.large_media_threshold_mb > 0 and
                        image_size is not None and
                        image_size > self.large_media_threshold_mb):
                    if (self.max_media_size_mb <= 0 or
                            image_size <= self.max_media_size_mb):
                        image_id = self._extract_media_id(url)
                        image_file = await self._download_large_media_to_cache(
                            session,
                            img_url,
                            image_id,
                            index=idx,
                            headers=self.headers,
                            is_video=False,
                            referer=referer_url,
                            default_referer='https://www.xiaohongshu.com/'
                        )
                        if image_file:
                            downloaded_files.append(image_file)
                if not image_file:
                    image_id = self._extract_media_id(url)
                    image_file = await self._download_image_to_file(
                        session,
                        img_url,
                        index=idx,
                        headers=self.headers,
                        referer=referer_url,
                        default_referer='https://www.xiaohongshu.com/'
                    )
                    if image_file:
                        downloaded_files.append(image_file)
                if image_file:
                    image_files.append(image_file)

        if not image_files and not images:
            return None

        return {
            "video_url": url,
            "title": note_info.get("title", ""),
            "desc": note_info.get("desc", ""),
            "author": author,
            "timestamp": note_info.get("publish_time", ""),
            "images": images,
            "image_files": image_files,
            "is_gallery": True
        }

    async def parse(
        self,
        session: aiohttp.ClientSession,
        url: str
    ) -> Optional[Dict[str, Any]]:
        """解析单个小红书链接。

        Args:
            session: aiohttp会话
            url: 小红书链接

        Returns:
            解析结果字典，如果解析失败返回None
        """
        async with self.semaphore:
            downloaded_files = []
            try:
                normalized_url = self._normalize_url(url)

                if normalized_url is None:
                    full_url = await self._get_redirect_url(session, url)
                else:
                    full_url = normalized_url

                html = await self._fetch_page(session, full_url)
                initial_state = self._extract_initial_state(html)
                note_info = self._parse_note_data(initial_state)

                note_type = note_info.get("type", "normal")
                if note_type == "video":
                    parse_result = await self._parse_video(
                        session,
                        url,
                        note_info,
                        downloaded_files,
                        page_url=full_url
                    )
                else:
                    parse_result = await self._parse_gallery(
                        session,
                        url,
                        note_info,
                        downloaded_files,
                        page_url=full_url
                    )

                if parse_result:
                    # 保存完整的小红书页面URL，用于下载时的referer
                    parse_result["page_url"] = full_url
                    downloaded_files = []
                return parse_result
            except Exception as e:
                if downloaded_files:
                    for file_path in downloaded_files:
                        if file_path and os.path.exists(file_path):
                            try:
                                os.unlink(file_path)
                            except Exception:
                                pass
                raise RuntimeError(f"解析失败：{str(e)}")

    def build_media_nodes(
        self,
        result: Dict[str, Any],
        sender_name: str,
        sender_id: Any,
        is_auto_pack: bool
    ) -> List:
        """构建媒体节点（视频或图片）。

        优先使用下载的图片文件，避免发送时下载失败。
        如果解析结果中有video_files（大视频已下载到缓存目录），
        优先使用文件方式构建节点。

        Args:
            result: 解析结果
            sender_name: 发送者名称
            sender_id: 发送者ID
            is_auto_pack: 是否打包为Node

        Returns:
            媒体节点列表
        """
        nodes = []
        if result.get('video_files'):
            return self._build_video_gallery_nodes_from_files(
                result['video_files'],
                sender_name,
                sender_id,
                is_auto_pack
            )
        if result.get('is_gallery') and result.get('image_files'):
            gallery_nodes = self._build_gallery_nodes_from_files(
                result['image_files'],
                sender_name,
                sender_id,
                is_auto_pack
            )
            nodes.extend(gallery_nodes)
        elif result.get('is_gallery') and result.get('images'):
            gallery_nodes = self._build_gallery_nodes_from_urls(
                result['images'],
                sender_name,
                sender_id,
                is_auto_pack
            )
            nodes.extend(gallery_nodes)
        elif result.get('direct_url'):
            video_node = self._build_video_node_from_url(
                result['direct_url'],
                sender_name,
                sender_id,
                is_auto_pack,
                result.get('thumb_url')
            )
            if video_node:
                nodes.append(video_node)
        return nodes

