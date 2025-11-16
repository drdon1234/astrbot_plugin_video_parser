# -*- coding: utf-8 -*-
"""
文件管理模块
负责缓存目录检查等文件处理相关的方法
"""
import os
from typing import List, Optional

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


def check_cache_dir_available(cache_dir: str) -> bool:
    """检查缓存目录是否可用（可写）

    Args:
        cache_dir: 缓存目录路径

    Returns:
        如果目录可用返回True，否则返回False
    """
    if not cache_dir:
        return False
    try:
        os.makedirs(cache_dir, exist_ok=True)
        test_file = os.path.join(cache_dir, ".test_write")
        try:
            with open(test_file, 'w') as f:
                f.write("test")
            os.unlink(test_file)
            return True
        except Exception as e:
            logger.warning(f"检查缓存目录写入权限失败: {e}")
            return False
    except Exception as e:
        logger.warning(f"检查缓存目录可用性失败: {e}")
        return False


def get_image_suffix(content_type: str = None, url: str = None) -> str:
    """根据Content-Type或URL确定图片文件扩展名

    Args:
        content_type: HTTP Content-Type头
        url: 图片URL

    Returns:
        文件扩展名（.jpg, .png, .webp, .gif），默认返回.jpg
    """
    if content_type:
        if 'jpeg' in content_type or 'jpg' in content_type:
            return '.jpg'
        elif 'png' in content_type:
            return '.png'
        elif 'webp' in content_type:
            return '.webp'
        elif 'gif' in content_type:
            return '.gif'

    if url:
        url_lower = url.lower()
        if '.jpg' in url_lower or '.jpeg' in url_lower:
            return '.jpg'
        elif '.png' in url_lower:
            return '.png'
        elif '.webp' in url_lower:
            return '.webp'
        elif '.gif' in url_lower:
            return '.gif'

    return '.jpg'


def cleanup_files(file_paths: List[str]) -> None:
    """清理文件列表

    Args:
        file_paths: 文件路径列表
    """
    for file_path in file_paths:
        if file_path and os.path.exists(file_path):
            try:
                os.unlink(file_path)
            except Exception as e:
                logger.warning(f"清理文件失败: {file_path}, 错误: {e}")

