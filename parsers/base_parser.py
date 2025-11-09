# -*- coding: utf-8 -*-
"""
基础解析器抽象类
所有视频解析器都应继承此类并实现必要的方法
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import aiohttp
import os
import re


class BaseVideoParser(ABC):
    """视频解析器基类"""
    
    def __init__(self, name: str, max_video_size_mb: float = 0.0, large_video_threshold_mb: float = 50.0, cache_dir: str = "/app/sharedFolder/video_parser/cache"):
        """
        初始化解析器
        
        Args:
            name: 解析器名称（用于显示）
            max_video_size_mb: 最大允许的视频大小(MB)，0表示不限制
            large_video_threshold_mb: 大视频阈值(MB)，超过此大小的视频将单独发送，0表示不启用，最大不超过100MB
            cache_dir: 视频缓存目录，用于大视频的缓存
        """
        self.name = name
        self.max_video_size_mb = max_video_size_mb
        self.cache_dir = cache_dir
        self.semaphore = None  # 子类可以设置信号量来控制并发
        # 大视频阈值（从配置读取，最大不超过100MB）
        if large_video_threshold_mb > 0:
            # 限制最大值为100MB（消息适配器硬性阈值）
            self.large_video_threshold_mb = min(large_video_threshold_mb, 100.0)
        else:
            self.large_video_threshold_mb = 0.0
        # 确保缓存目录存在
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
    
    @abstractmethod
    def can_parse(self, url: str) -> bool:
        """
        判断是否可以解析此URL
        
        Args:
            url: 待检测的URL
            
        Returns:
            bool: 是否可以解析
        """
        pass
    
    @abstractmethod
    def extract_links(self, text: str) -> List[str]:
        """
        从文本中提取该解析器可以处理的链接
        
        Args:
            text: 输入文本
            
        Returns:
            List[str]: 提取到的链接列表
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
            Optional[Dict[str, Any]]: 解析结果，包含：
                - video_url: 原始视频页面URL
                - direct_url: 视频直链（如果有）
                - title: 视频标题
                - author: 作者信息
                - desc: 视频描述（可选）
                - thumb_url: 封面图URL（可选）
                - images: 图片列表（如果是图片集，可选）
                - is_gallery: 是否为图片集（可选）
            如果解析失败，返回None
        """
        pass
    
    async def get_video_size(self, video_url: str, session: aiohttp.ClientSession) -> Optional[float]:
        """
        获取视频文件大小(MB)
        
        Args:
            video_url: 视频URL
            session: aiohttp会话
            
        Returns:
            Optional[float]: 视频大小(MB)，如果无法获取则返回None
        """
        try:
            async with session.head(video_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                # 优先检查Content-Range（无论状态码，因为它包含完整文件大小）
                content_range = resp.headers.get("Content-Range")
                if content_range:
                    # Content-Range格式: bytes 286523392-286526818/286526819
                    # 提取最后一个数字（完整文件大小）
                    match = re.search(r'/\s*(\d+)', content_range)
                    if match:
                        size_bytes = int(match.group(1))
                        size_mb = size_bytes / (1024 * 1024)
                        return size_mb
                
                # 如果没有Content-Range，检查Content-Length
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
            bool: 如果视频大小在允许范围内或无法获取大小，返回True；否则返回False
        """
        if self.max_video_size_mb <= 0:
            return True
        video_size = await self.get_video_size(video_url, session)
        if video_size is None:
            return True  # 无法获取大小时，允许通过
        return video_size <= self.max_video_size_mb
    
    async def _download_large_video_to_cache(self, session: aiohttp.ClientSession, video_url: str, video_id: str, index: int = 0, headers: dict = None) -> Optional[str]:
        """
        下载大视频到缓存目录（用于超过大视频阈值的视频）
        
        Args:
            session: aiohttp会话
            video_url: 视频URL
            video_id: 视频ID（用于生成文件名）
            index: 视频索引（同一内容可能有多个视频）
            headers: 请求头（可选）
            
        Returns:
            文件路径，失败返回 None
        """
        if not self.cache_dir:
            return None
        
        try:
            request_headers = headers or {}
            async with session.get(
                video_url,
                headers=request_headers,
                timeout=aiohttp.ClientTimeout(total=300)  # 大视频下载可能需要更长时间
            ) as response:
                response.raise_for_status()
                
                # 生成文件名（使用视频ID和索引）
                filename = f"{video_id}_{index}.mp4"
                file_path = os.path.join(self.cache_dir, filename)
                
                # 如果文件已存在，直接返回
                if os.path.exists(file_path):
                    return os.path.normpath(file_path)
                
                # 下载视频内容
                content = await response.read()
                
                # 写入缓存目录
                with open(file_path, 'wb') as f:
                    f.write(content)
                
                return os.path.normpath(file_path)
        except Exception:
            return None
    
    def build_text_node(self, result: Dict[str, Any], sender_name: str, sender_id: Any, is_auto_pack: bool):
        """
        构建文本节点（标题、作者等信息）
        
        Args:
            result: 解析结果
            sender_name: 发送者名称
            sender_id: 发送者ID
            is_auto_pack: 是否打包为Node
            
        Returns:
            Node或Plain: 文本节点
        """
        from astrbot.api.message_components import Plain
        
        # 构建文本内容
        text_parts = []
        if result.get('title'):
            text_parts.append(f"标题：{result['title']}")
        if result.get('author'):
            text_parts.append(f"作者：{result['author']}")
        if result.get('desc'):
            text_parts.append(f"简介：{result['desc']}")
        if result.get('timestamp'):
            text_parts.append(f"发布时间：{result['timestamp']}")
        
        # 添加视频大小调试信息
        if result.get('file_size_mb') is not None:
            file_size_mb = result.get('file_size_mb')
            text_parts.append(f"视频大小：{file_size_mb:.2f} MB")
        
        if result.get('video_url'):
            text_parts.append(f"原始链接：{result['video_url']}")
        
        if not text_parts:
            return None
        
        desc_text = "\n".join(text_parts)
        
        # 重构后：统一返回 Plain 对象，扁平化处理
        return Plain(desc_text)
    
    def _build_gallery_nodes_from_files(self, image_files: List[str], sender_name: str, sender_id: Any, is_auto_pack: bool) -> List:
        """
        从文件路径列表构建图集节点
        重构后：纯图片图集返回 Image 对象列表，扁平化处理
        
        Args:
            image_files: 图片文件路径列表
            sender_name: 发送者名称
            sender_id: 发送者ID
            is_auto_pack: 是否打包为Node（已废弃，统一返回 Image 列表）
            
        Returns:
            List: Image 对象列表
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
                # 如果加载失败，清理临时文件
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
        重构后：纯图片图集返回 Image 对象列表，扁平化处理
        
        Args:
            images: 图片URL列表
            sender_name: 发送者名称（已废弃）
            sender_id: 发送者ID（已废弃）
            is_auto_pack: 是否打包为Node（已废弃）
            
        Returns:
            List: Image 对象列表
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
        重构后：统一返回 Video 对象，不再包装为 Node
        
        Args:
            video_url: 视频URL
            sender_name: 发送者名称（已废弃）
            sender_id: 发送者ID（已废弃）
            is_auto_pack: 是否打包为Node（已废弃）
            cover: 封面图URL（可选）
            
        Returns:
            Video 对象，如果失败返回None
        """
        from astrbot.api.message_components import Video
        
        if not video_url:
            return None
        
        try:
            # 重构后：直接返回 Video 对象，扁平化处理
            if cover:
                return Video.fromURL(video_url, cover=cover)
            else:
                return Video.fromURL(video_url)
        except Exception:
            return None
    
    def _build_video_node_from_file(self, video_file_path: str, sender_name: str, sender_id: Any, is_auto_pack: bool) -> Optional[Any]:
        """
        从文件路径构建视频节点
        重构后：统一返回 Video 对象，不再包装为 Node
        
        Args:
            video_file_path: 视频文件路径
            sender_name: 发送者名称（已废弃）
            sender_id: 发送者ID（已废弃）
            is_auto_pack: 是否打包为Node（已废弃）
            
        Returns:
            Video 对象，如果失败返回None
        """
        from astrbot.api.message_components import Video
        
        if not video_file_path:
            return None
        
        video_file_path = os.path.normpath(video_file_path)
        if not os.path.exists(video_file_path):
            return None
        
        try:
            # 重构后：直接返回 Video 对象，扁平化处理
            return Video.fromFileSystem(video_file_path)
        except Exception:
            return None
    
    def _build_video_gallery_nodes_from_files(self, video_files: List[Dict[str, Any]], sender_name: str, sender_id: Any, is_auto_pack: bool) -> List:
        """
        从视频文件信息列表构建视频图集节点
        重构后：视频图集混合结果全部单独发送，返回 Video 对象列表，扁平化处理
        
        Args:
            video_files: 视频文件信息列表，每个元素包含 'file_path' 等字段
            sender_name: 发送者名称（已废弃）
            sender_id: 发送者ID（已废弃）
            is_auto_pack: 是否打包为Node（已废弃，统一返回 Video 列表）
            
        Returns:
            List: Video 对象列表
        """
        from astrbot.api.message_components import Video
        
        if not video_files or not isinstance(video_files, list):
            return []
        
        # 重构后：视频图集混合结果全部单独发送，返回 Video 对象列表，扁平化处理
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
                # 如果加载失败，清理临时文件
                if os.path.exists(file_path):
                    try:
                        os.unlink(file_path)
                    except Exception:
                        pass
                continue
        
        return videos
    
    def build_media_nodes(self, result: Dict[str, Any], sender_name: str, sender_id: Any, is_auto_pack: bool) -> List:
        """
        构建媒体节点（视频或图片）
        默认实现：处理URL方式的图片集和视频
        子类可以重写此方法以支持文件方式或其他特殊需求
        重构后：所有节点都扁平化返回（Image/Video 对象）
        
        Args:
            result: 解析结果
            sender_name: 发送者名称（已废弃）
            sender_id: 发送者ID（已废弃）
            is_auto_pack: 是否打包为Node（已废弃，统一扁平化返回）
            
        Returns:
            List: 媒体节点列表（Image/Video 对象）
        """
        nodes = []
        
        # 处理图片集（从URL）
        if result.get('is_gallery') and result.get('images'):
            gallery_nodes = self._build_gallery_nodes_from_urls(
                result['images'], 
                sender_name, 
                sender_id, 
                is_auto_pack
            )
            nodes.extend(gallery_nodes)
        
        # 处理视频（从URL）
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

