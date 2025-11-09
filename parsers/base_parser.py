# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import aiohttp
import os
import re


class BaseVideoParser(ABC):

    def __init__(self, name: str, max_video_size_mb: float = 0.0, large_video_threshold_mb: float = 50.0, cache_dir: str = "/app/sharedFolder/video_parser/cache"):
        """
        初始化插件
        Args:
            name: 解析器名称
            max_video_size_mb: 最大允许的视频大小(MB)
            large_video_threshold_mb: 大视频阈值(MB)
            cache_dir: 视频缓存目录
        """
        self.name = name
        self.max_video_size_mb = max_video_size_mb
        self.cache_dir = cache_dir
        self.semaphore = None
        if large_video_threshold_mb > 0:
            self.large_video_threshold_mb = min(large_video_threshold_mb, 100.0)
        else:
            self.large_video_threshold_mb = 0.0
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)

    @abstractmethod
    def can_parse(self, url: str) -> bool:
        """
        判断是否可以解析此URL
        Args:
            url: 视频链接
        Returns:
            bool: 布尔值
        """
        pass

    @abstractmethod
    def extract_links(self, text: str) -> List[str]:
        """
        从文本中提取链接
        Args:
            text: 输入文本
        Returns:
            List[str]: 字符串列表
        """
        pass

    @abstractmethod
    async def parse(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict[str, Any]]:
        """
        解析单个视频链接
        Args:
            session: aiohttp会话
            url: 视频链接
        Returns:
            Optional: 返回值
        """
        pass

    async def get_video_size(self, video_url: str, session: aiohttp.ClientSession) -> Optional[float]:
        """
        获取视频文件大小
        Args:
            video_url: 视频URL
            session: aiohttp会话
        Returns:
            Optional[float]: 浮点数或None
        """
        try:
            async with session.head(video_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
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

    async def check_video_size(self, video_url: str, session: aiohttp.ClientSession) -> bool:
        """
        检查视频大小是否在允许范围内
        Args:
            video_url: 视频URL
            session: aiohttp会话
        Returns:
            bool: 布尔值
        """
        if self.max_video_size_mb <= 0:
            return True
        video_size = await self.get_video_size(video_url, session)
        if video_size is None:
            return True
        return video_size <= self.max_video_size_mb

    async def _download_large_video_to_cache(self, session: aiohttp.ClientSession, video_url: str, video_id: str, index: int = 0, headers: dict = None) -> Optional[str]:
        """
        下载大视频到缓存目录
        Args:
            session: aiohttp会话
            video_url: 视频URL
            video_id: 视频ID
            index: 索引
            headers: 请求头
        Returns:
            Optional[str]: 字符串或None
        """
        if not self.cache_dir:
            return None
        try:
            request_headers = headers or {}
            async with session.get(
                video_url,
                headers=request_headers,
                timeout=aiohttp.ClientTimeout(total=300)
            ) as response:
                response.raise_for_status()
                filename = f"{video_id}_{index}.mp4"
                file_path = os.path.join(self.cache_dir, filename)
                if os.path.exists(file_path):
                    return os.path.normpath(file_path)
                content = await response.read()
                with open(file_path, 'wb') as f:
                    f.write(content)
                return os.path.normpath(file_path)
        except Exception:
            return None

    def build_text_node(self, result: Dict[str, Any], sender_name: str, sender_id: Any, is_auto_pack: bool):
        """
        构建文本节点
        Args:
            result: 解析结果
            sender_name: 发送者名称
            sender_id: 发送者ID
            is_auto_pack: 是否打包为Node
        Returns:
            Any: 返回值
        """
        from astrbot.api.message_components import Plain
        text_parts = []
        if result.get('title'):
            text_parts.append(f"标题：{result['title']}")
        if result.get('author'):
            text_parts.append(f"作者：{result['author']}")
        if result.get('desc'):
            text_parts.append(f"简介：{result['desc']}")
        if result.get('timestamp'):
            text_parts.append(f"发布时间：{result['timestamp']}")
        if result.get('file_size_mb') is not None:
            file_size_mb = result.get('file_size_mb')
            text_parts.append(f"视频大小：{file_size_mb:.2f} MB")
        if result.get('video_url'):
            text_parts.append(f"原始链接：{result['video_url']}")
        if not text_parts:
            return None
        desc_text = "\n".join(text_parts)
        return Plain(desc_text)

    def _build_gallery_nodes_from_files(self, image_files: List[str], sender_name: str, sender_id: Any, is_auto_pack: bool) -> List:
        """
        从文件路径列表构建图集节点
        Args:
            image_files: 图片文件路径列表
            sender_name: 发送者名称
            sender_id: 发送者ID
            is_auto_pack: 是否打包为Node
        Returns:
            List: 列表
        """
        from astrbot.api.message_components import Image
        if not image_files or not isinstance(image_files, list):
            return []
        images = []
        for image_path in image_files:
            if not image_path:
                continue
            image_path = os.path.normpath(image_path)
            if not os.path.exists(image_path):
                continue
            try:
                images.append(Image.fromFileSystem(image_path))
            except Exception:
                if os.path.exists(image_path):
                    try:
                        os.unlink(image_path)
                    except Exception:
                        pass
                continue
        return images

    def _build_gallery_nodes_from_urls(self, images: List[str], sender_name: str, sender_id: Any, is_auto_pack: bool) -> List:
        """
        从URL列表构建图集节点
        Args:
            images: 图片URL列表
            sender_name: 发送者名称
            sender_id: 发送者ID
            is_auto_pack: 是否打包为Node
        Returns:
            List: 列表
        """
        from astrbot.api.message_components import Image
        if not images or not isinstance(images, list):
            return []
        valid_images = [img for img in images if img and isinstance(img, str) and img.startswith(('http://', 'https://'))]
        if not valid_images:
            return []
        images_list = []
        for image_url in valid_images:
            try:
                images_list.append(Image.fromURL(image_url))
            except Exception:
                continue
        return images_list

    def _build_video_node_from_url(self, video_url: str, sender_name: str, sender_id: Any, is_auto_pack: bool, cover: Optional[str] = None) -> Optional[Any]:
        """
        从URL构建视频节点
        Args:
            video_url: 视频URL
            sender_name: 发送者名称
            sender_id: 发送者ID
            is_auto_pack: 是否打包为Node
            cover: 封面图URL
        Returns:
            Optional[Any]: 任意类型或None
        """
        from astrbot.api.message_components import Video
        if not video_url:
            return None
        try:
            if cover:
                return Video.fromURL(video_url, cover=cover)
            else:
                return Video.fromURL(video_url)
        except Exception:
            return None

    def _build_video_node_from_file(self, video_file_path: str, sender_name: str, sender_id: Any, is_auto_pack: bool) -> Optional[Any]:
        """
        从文件路径构建视频节点
        Args:
            video_file_path: 视频文件路径
            sender_name: 发送者名称
            sender_id: 发送者ID
            is_auto_pack: 是否打包为Node
        Returns:
            Optional[Any]: 任意类型或None
        """
        from astrbot.api.message_components import Video
        if not video_file_path:
            return None
        video_file_path = os.path.normpath(video_file_path)
        if not os.path.exists(video_file_path):
            return None
        try:
            return Video.fromFileSystem(video_file_path)
        except Exception:
            return None

    def _build_video_gallery_nodes_from_files(self, video_files: List[Dict[str, Any]], sender_name: str, sender_id: Any, is_auto_pack: bool) -> List:
        """
        从视频文件信息列表构建视频图集节点
        Args:
            video_files: 视频文件列表
            sender_name: 发送者名称
            sender_id: 发送者ID
            is_auto_pack: 是否打包为Node
        Returns:
            List: 列表
        """
        from astrbot.api.message_components import Video
        if not video_files or not isinstance(video_files, list):
            return []
        videos = []
        for video_file_info in video_files:
            file_path = video_file_info.get('file_path') if isinstance(video_file_info, dict) else video_file_info
            if not file_path:
                continue
            file_path = os.path.normpath(file_path)
            if not os.path.exists(file_path):
                continue
            try:
                videos.append(Video.fromFileSystem(file_path))
            except Exception:
                if os.path.exists(file_path):
                    try:
                        os.unlink(file_path)
                    except Exception:
                        pass
                continue
        return videos

    def build_media_nodes(self, result: Dict[str, Any], sender_name: str, sender_id: Any, is_auto_pack: bool) -> List:
        """
        构建媒体节点
        Args:
            result: 解析结果
            sender_name: 发送者名称
            sender_id: 发送者ID
            is_auto_pack: 是否打包为Node
        Returns:
            List: 列表
        """
        nodes = []
        if result.get('is_gallery') and result.get('images'):
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
