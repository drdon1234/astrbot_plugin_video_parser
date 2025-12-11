# -*- coding: utf-8 -*-
"""
下载路由器
根据媒体类型选择相应的下载处理器
"""
from typing import Optional, Dict, Any, Literal

import aiohttp

from .handler.image import download_image_to_file
from .handler.normal_video import download_video_to_cache
from .handler.m3u8 import M3U8Handler


def detect_media_type(url: str) -> Literal['m3u8', 'image', 'video']:
    """检测媒体类型

    Args:
        url: 媒体URL

    Returns:
        媒体类型：'m3u8', 'image', 或 'video'
    """
    url_lower = url.lower()
    
    if '.m3u8' in url_lower:
        return 'm3u8'
    
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg']
    if any(url_lower.endswith(ext) or f'{ext}?' in url_lower for ext in image_extensions):
        return 'image'
    
    video_extensions = ['.mp4', '.mkv', '.mov', '.avi', '.flv', '.f4v', '.webm', '.wmv', '.m4v']
    if any(url_lower.endswith(ext) or f'{ext}?' in url_lower for ext in video_extensions):
        return 'video'
    
    return 'video'


async def download_media(
    session: aiohttp.ClientSession,
    media_url: str,
    media_type: Optional[Literal['m3u8', 'image', 'video']] = None,
    cache_dir: Optional[str] = None,
    media_id: Optional[str] = None,
    index: int = 0,
    headers: dict = None,
    referer: str = None,
    default_referer: str = None,
    proxy: str = None,
    m3u8_handler: Optional[M3U8Handler] = None,
    use_ffmpeg: bool = True
) -> Optional[Dict[str, Any]]:
    """统一的媒体下载接口，根据媒体类型自动选择下载方式

    Args:
        session: aiohttp会话
        media_url: 媒体URL
        media_type: 媒体类型（'m3u8', 'image', 'video'），如果为None则自动检测
        cache_dir: 缓存目录路径（视频和m3u8需要）
        media_id: 媒体ID（视频和m3u8需要）
        index: 索引
        headers: 自定义请求头
        referer: Referer URL
        default_referer: 默认Referer URL
        proxy: 代理地址
        m3u8_handler: M3U8处理器实例（如果为None且需要m3u8下载，则创建新实例）
        use_ffmpeg: 是否使用ffmpeg合并m3u8音视频

    Returns:
        对于图片：返回文件路径字符串，失败返回None
        对于视频和m3u8：返回包含file_path和size_mb的字典，失败返回None
    """
    if media_type is None:
        media_type = detect_media_type(media_url)
    
    if media_type == 'm3u8':
        if not cache_dir:
            return None
        
        if m3u8_handler is None:
            m3u8_handler = M3U8Handler(
                session=session,
                headers=headers,
                referer=referer,
                proxy=proxy
            )
        
        return await m3u8_handler.download_m3u8_to_cache(
            m3u8_url=media_url,
            cache_dir=cache_dir,
            media_id=media_id or 'media',
            index=index,
            use_ffmpeg=use_ffmpeg
        )
    
    elif media_type == 'image':
        file_path = await download_image_to_file(
            session=session,
            image_url=media_url,
            index=index,
            headers=headers,
            referer=referer,
            default_referer=default_referer,
            proxy=proxy,
            cache_dir=cache_dir,
            media_id=media_id
        )
        if file_path:
            return {'file_path': file_path, 'size_mb': None}
        return None
    
    else:  # video
        if not cache_dir:
            return None
        
        return await download_video_to_cache(
            session=session,
            video_url=media_url,
            cache_dir=cache_dir,
            media_id=media_id or 'media',
            index=index,
            headers=headers,
            referer=referer,
            default_referer=default_referer,
            proxy=proxy
        )

