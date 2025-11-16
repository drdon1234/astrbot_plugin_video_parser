# -*- coding: utf-8 -*-
"""
下载管理器
负责管理下载流程，检查配置项，确定使用网络直链还是本地文件
"""
from typing import Dict, Any, List, Optional, Tuple
import asyncio
import os

import aiohttp

from astrbot.api import logger

from .downloader import (
    get_video_size,
    download_media_to_cache,
    pre_download_media,
    validate_media_url
)
from .file_manager import (
    check_cache_dir_available,
    cleanup_files
)


class DownloadManager:
    """下载管理器，负责管理视频下载流程"""

    def __init__(
        self,
        max_video_size_mb: float = 0.0,
        large_video_threshold_mb: float = 50.0,
        cache_dir: str = "/app/sharedFolder/video_parser/cache",
        pre_download_all_media: bool = False,
        max_concurrent_downloads: int = 3
    ):
        """初始化下载管理器

        Args:
            max_video_size_mb: 最大允许的视频大小(MB)，0表示不限制
            large_video_threshold_mb: 大视频阈值(MB)，超过此大小将单独发送
            cache_dir: 视频缓存目录
            pre_download_all_media: 是否预先下载所有媒体到本地
            max_concurrent_downloads: 最大并发下载数
        """
        self.max_video_size_mb = max_video_size_mb
        if large_video_threshold_mb > 0:
            self.large_video_threshold_mb = min(large_video_threshold_mb, 100.0)
        else:
            self.large_video_threshold_mb = 0.0
        self.cache_dir = cache_dir
        self.pre_download_all_media = pre_download_all_media
        self.max_concurrent_downloads = max_concurrent_downloads
        self.cache_dir_available = check_cache_dir_available(cache_dir)
        if self.cache_dir_available and cache_dir:
            import os
            os.makedirs(cache_dir, exist_ok=True)

    def _build_media_items(
        self,
        metadata: Dict[str, Any],
        media_id: str,
        headers: dict = None,
        referer: str = None,
        proxy: str = None
    ) -> List[Dict[str, Any]]:
        """构建媒体项列表

        Args:
            metadata: 元数据字典
            media_id: 媒体ID
            headers: 请求头（可选）
            referer: Referer URL（可选）
            proxy: 代理地址（可选）

        Returns:
            媒体项列表，每个项包含url_list（URL列表）、media_id、index、is_video等字段
        """
        media_items = []
        video_urls = metadata.get('video_urls', [])
        image_urls = metadata.get('image_urls', [])
        
        idx = 0
        for url_list in video_urls:
            if url_list and isinstance(url_list, list):
                media_items.append({
                    'url_list': url_list,
                    'media_id': media_id,
                    'index': idx,
                    'is_video': True,
                    'headers': headers,
                    'referer': referer,
                    'default_referer': referer,
                    'proxy': proxy
                })
                idx += 1
        
        for url_list in image_urls:
            if url_list and isinstance(url_list, list):
                media_items.append({
                    'url_list': url_list,
                    'media_id': media_id,
                    'index': idx,
                    'is_video': False,
                    'headers': headers,
                    'referer': referer,
                    'default_referer': referer,
                    'proxy': proxy
                })
                idx += 1
        
        return media_items

    def _process_download_results(
        self,
        download_results: List[Dict[str, Any]],
        video_urls: List[List[str]],
        image_urls: List[List[str]]
    ) -> Tuple[List[Optional[str]], int, int]:
        """处理下载结果，构建文件路径列表并统计失败数量

        Args:
            download_results: 下载结果列表
            video_urls: 视频URL列表（二维列表）
            image_urls: 图片URL列表（二维列表）

        Returns:
            (file_paths, failed_video_count, failed_image_count) 元组
        """
        file_paths = []
        failed_video_count = 0
        failed_image_count = 0
        
        result_idx = 0
        for url_list in video_urls:
            if result_idx < len(download_results):
                result = download_results[result_idx]
                if result.get('success') and result.get('file_path'):
                    file_paths.append(result['file_path'])
                else:
                    file_paths.append(None)
                    failed_video_count += 1
                result_idx += 1
            else:
                file_paths.append(None)
                failed_video_count += 1
        
        for url_list in image_urls:
            if result_idx < len(download_results):
                result = download_results[result_idx]
                if result.get('success') and result.get('file_path'):
                    file_paths.append(result['file_path'])
                else:
                    file_paths.append(None)
                    failed_image_count += 1
                result_idx += 1
            else:
                file_paths.append(None)
                failed_image_count += 1
        
        return file_paths, failed_video_count, failed_image_count

    async def process_metadata(
        self,
        session: aiohttp.ClientSession,
        metadata: Dict[str, Any],
        headers: dict = None,
        referer: str = None,
        proxy: str = None
    ) -> Dict[str, Any]:
        """处理元数据，检查视频大小，确定使用网络直链还是本地文件

        Args:
            session: aiohttp会话
            metadata: 解析后的元数据
            headers: 请求头（可选）
            referer: Referer URL（可选）
            proxy: 代理地址（可选）

        Returns:
            处理后的元数据，包含视频大小信息和文件路径信息
        """
        if not metadata:
            return metadata

        url = metadata.get('url', '')
        video_urls = metadata.get('video_urls', [])
        image_urls = metadata.get('image_urls', [])

        if not video_urls and not image_urls:
            metadata['has_valid_media'] = False
            metadata['video_count'] = 0
            metadata['image_count'] = 0
            metadata['failed_video_count'] = 0
            metadata['failed_image_count'] = 0
            metadata['file_paths'] = []
            return metadata

        # 统计视频和图片数量
        video_count = len(video_urls)
        image_count = len(image_urls)
        
        # 预检查视频大小（如果需要）
        pre_check_video_sizes = None
        if video_urls and self.max_video_size_mb > 0:
            async def get_video_size_task(url_list: List[str]) -> Optional[float]:
                """获取视频大小，尝试第一个URL"""
                if not url_list:
                    return None
                try:
                    size = await get_video_size(session, url_list[0], headers, proxy)
                    return size
                except Exception:
                    return None
            
            tasks = [
                get_video_size_task(url_list)
                for url_list in video_urls
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            video_sizes = []
            for result in results:
                if isinstance(result, Exception):
                    video_sizes.append(None)
                elif isinstance(result, (int, float)) or result is None:
                    video_sizes.append(result)
                else:
                    video_sizes.append(None)
            
            valid_sizes = [s for s in video_sizes if s is not None]
            if valid_sizes:
                max_video_size = max(valid_sizes)
                if max_video_size > self.max_video_size_mb:
                    logger.warning(
                        f"视频大小超过限制: {max_video_size:.2f}MB > {self.max_video_size_mb}MB, "
                        f"URL: {url}，跳过下载"
                    )
                    metadata['exceeds_max_size'] = True
                    metadata['has_valid_media'] = False
                    metadata['video_sizes'] = video_sizes
                    metadata['max_video_size_mb'] = max_video_size
                    metadata['total_video_size_mb'] = sum(valid_sizes) if valid_sizes else 0.0
                    metadata['video_count'] = video_count
                    metadata['image_count'] = image_count
                    metadata['failed_video_count'] = video_count
                    metadata['failed_image_count'] = image_count
                    metadata['file_paths'] = []
                    metadata['use_local_files'] = False
                    metadata['is_large_media'] = False
                    return metadata
                pre_check_video_sizes = video_sizes
        
        # 如果需要预下载所有媒体
        if self.pre_download_all_media and self.cache_dir_available:
            media_id = self._generate_media_id(url)
            media_items = self._build_media_items(
                metadata,
                media_id,
                headers,
                referer,
                proxy
            )

            download_results = await pre_download_media(
                session,
                media_items,
                self.cache_dir,
                self.max_concurrent_downloads
            )
            
            # 处理下载结果，构建文件路径列表
            file_paths, failed_video_count, failed_image_count = self._process_download_results(
                download_results, video_urls, image_urls
            )
            
            metadata['file_paths'] = file_paths
            metadata['failed_video_count'] = failed_video_count
            metadata['failed_image_count'] = failed_image_count
            
            # 处理视频大小信息
            if video_urls:
                video_sizes = []
                for idx, result in enumerate(download_results[:len(video_urls)]):
                    if result.get('success') and result.get('size_mb') is not None:
                        video_sizes.append(result.get('size_mb'))
                    elif pre_check_video_sizes and idx < len(pre_check_video_sizes):
                        video_sizes.append(pre_check_video_sizes[idx])
                    else:
                        video_sizes.append(None)
                
                valid_sizes = [s for s in video_sizes if s is not None]
                max_video_size = max(valid_sizes) if valid_sizes else None
                total_video_size = sum(valid_sizes) if valid_sizes else 0.0
                
                metadata['video_sizes'] = video_sizes
                metadata['max_video_size_mb'] = max_video_size
                metadata['total_video_size_mb'] = total_video_size
                
                # 再次检查大小限制
                if self.max_video_size_mb > 0 and max_video_size is not None:
                    if max_video_size > self.max_video_size_mb:
                        logger.warning(
                            f"视频大小超过限制: {max_video_size:.2f}MB > {self.max_video_size_mb}MB, "
                            f"URL: {url}"
                        )
                        cleanup_files(file_paths)
                        metadata['exceeds_max_size'] = True
                        metadata['has_valid_media'] = False
                        metadata['use_local_files'] = False
                        metadata['file_paths'] = []
                        return metadata
            else:
                metadata['video_sizes'] = []
                metadata['max_video_size_mb'] = None
                metadata['total_video_size_mb'] = 0.0
            
            # 检查是否有有效媒体
            has_valid_media = any(
                result.get('success') and result.get('file_path')
                for result in download_results
            )
            
            metadata['has_valid_media'] = has_valid_media
            metadata['use_local_files'] = has_valid_media
            metadata['video_count'] = video_count
            metadata['image_count'] = image_count
            metadata['exceeds_max_size'] = False
            metadata['is_large_media'] = False
            
            return metadata

        # 非预下载模式：验证媒体URL并检查大小
        async def get_video_size_task(url_list: List[str]) -> Optional[float]:
            """获取单个视频的大小，尝试第一个URL"""
            if not url_list:
                return None
            try:
                size = await get_video_size(session, url_list[0], headers, proxy)
                return size
            except Exception:
                return None
        
        # 获取视频大小
        video_sizes = []
        if video_urls:
            tasks = [
                get_video_size_task(url_list)
                for url_list in video_urls
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    video_sizes.append(None)
                elif isinstance(result, (int, float)) or result is None:
                    video_sizes.append(result)
                else:
                    video_sizes.append(None)
        else:
            video_sizes = []

        valid_sizes = [s for s in video_sizes if s is not None]
        max_video_size = max(valid_sizes) if valid_sizes else None
        total_video_size = sum(valid_sizes) if valid_sizes else 0.0

        metadata['video_sizes'] = video_sizes
        metadata['max_video_size_mb'] = max_video_size
        metadata['total_video_size_mb'] = total_video_size
        metadata['video_count'] = video_count
        metadata['image_count'] = image_count

        has_valid_videos = len(valid_sizes) > 0
        
        # 验证图片URL
        has_valid_images = False
        if image_urls:
            async def validate_image_task(url_list: List[str]) -> bool:
                """验证图片URL列表，尝试第一个URL"""
                if not url_list:
                    return False
                try:
                    return await validate_media_url(session, url_list[0], headers, proxy, is_video=False)
                except Exception:
                    return False
            
            tasks = [validate_image_task(url_list) for url_list in image_urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            has_valid_images = any(
                r for r in results 
                if isinstance(r, bool) and r
            )
        
        has_valid_media = has_valid_videos or has_valid_images
        metadata['has_valid_media'] = has_valid_media
        
        if not has_valid_media:
            metadata['exceeds_max_size'] = False
            metadata['file_paths'] = []
            metadata['use_local_files'] = False
            metadata['is_large_media'] = False
            metadata['failed_video_count'] = video_count
            metadata['failed_image_count'] = image_count
            return metadata

        # 检查视频大小限制
        if self.max_video_size_mb > 0 and max_video_size is not None:
            if max_video_size > self.max_video_size_mb:
                logger.warning(
                    f"视频大小超过限制: {max_video_size:.2f}MB > {self.max_video_size_mb}MB, "
                    f"URL: {url}"
                )
                metadata['exceeds_max_size'] = True
                metadata['has_valid_media'] = False
                metadata['max_video_size_mb'] = max_video_size
                metadata['failed_video_count'] = video_count
                metadata['failed_image_count'] = image_count
                return metadata

        metadata['exceeds_max_size'] = False

        # 判断是否需要下载
        needs_download = False
        if self.large_video_threshold_mb > 0 and max_video_size is not None:
            if max_video_size > self.large_video_threshold_mb:
                needs_download = True

        if metadata.get('is_twitter_video'):
            needs_download = True

        # 下载大视频
        if needs_download and self.cache_dir_available:
            media_id = self._generate_media_id(url)
            media_items = self._build_media_items(
                metadata,
                media_id,
                headers,
                referer,
                proxy
            )
            
            download_results = await pre_download_media(
                session,
                media_items,
                self.cache_dir,
                self.max_concurrent_downloads
            )
            
            # 处理下载结果
            file_paths, failed_video_count, failed_image_count = self._process_download_results(
                download_results, video_urls, image_urls
            )
            
            # 检查下载后的视频大小
            if video_urls and self.max_video_size_mb > 0:
                download_video_sizes = []
                for idx, result in enumerate(download_results[:len(video_urls)]):
                    if result.get('success') and result.get('size_mb') is not None:
                        download_video_sizes.append(result.get('size_mb'))
                    elif idx < len(video_sizes):
                        download_video_sizes.append(video_sizes[idx])
                    else:
                        download_video_sizes.append(None)
                
                valid_download_sizes = [s for s in download_video_sizes if s is not None]
                if valid_download_sizes:
                    actual_max_video_size = max(valid_download_sizes)
                    if actual_max_video_size > self.max_video_size_mb:
                        logger.warning(
                            f"视频大小超过限制: {actual_max_video_size:.2f}MB > {self.max_video_size_mb}MB, "
                            f"URL: {url}，清理已下载的文件"
                        )
                        cleanup_files(file_paths)
                        metadata['exceeds_max_size'] = True
                        metadata['has_valid_media'] = False
                        metadata['use_local_files'] = False
                        metadata['file_paths'] = []
                        metadata['is_large_media'] = False
                        metadata['video_sizes'] = download_video_sizes
                        metadata['max_video_size_mb'] = actual_max_video_size
                        metadata['failed_video_count'] = video_count
                        metadata['failed_image_count'] = image_count
                        return metadata
                    metadata['video_sizes'] = download_video_sizes
                    metadata['max_video_size_mb'] = actual_max_video_size
                    metadata['total_video_size_mb'] = sum(valid_download_sizes)
            
            has_valid_media = any(
                result.get('success') and result.get('file_path')
                for result in download_results
            )
            
            metadata['file_paths'] = file_paths
            metadata['use_local_files'] = True
            metadata['is_large_media'] = True
            metadata['failed_video_count'] = failed_video_count
            metadata['failed_image_count'] = failed_image_count
        else:
            metadata['file_paths'] = []
            metadata['use_local_files'] = False
            metadata['is_large_media'] = False
            metadata['failed_video_count'] = 0
            metadata['failed_image_count'] = 0
        
        metadata['has_valid_media'] = has_valid_media

        return metadata

    def _generate_media_id(self, url: str) -> str:
        """根据URL生成媒体ID

        Args:
            url: 原始URL

        Returns:
            媒体ID
        """
        import hashlib
        import re
        from urllib.parse import urlparse

        parsed = urlparse(url)
        path = parsed.path.strip('/')
        
        id_match = re.search(r'/(\d+)', path)
        if id_match:
            return id_match.group(1)
        
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        return url_hash

    async def process_metadata_list(
        self,
        session: aiohttp.ClientSession,
        metadata_list: List[Dict[str, Any]],
        headers: dict = None,
        referer: str = None,
        proxy: str = None
    ) -> List[Dict[str, Any]]:
        """处理元数据列表

        Args:
            session: aiohttp会话
            metadata_list: 解析后的元数据列表
            headers: 请求头（可选）
            referer: Referer URL（可选）
            proxy: 代理地址（可选）

        Returns:
            处理后的元数据列表
        """
        processed_metadata = []
        for metadata in metadata_list:
            try:
                processed = await self.process_metadata(
                    session,
                    metadata,
                    headers,
                    referer,
                    proxy
                )
                processed_metadata.append(processed)
            except Exception as e:
                logger.exception(f"处理元数据失败: {metadata.get('url', '')}, 错误: {e}")
                metadata['error'] = str(e)
                processed_metadata.append(metadata)
        return processed_metadata

