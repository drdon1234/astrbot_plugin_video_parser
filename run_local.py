# -*- coding: utf-8 -*-
"""
本地测试脚本
用于测试视频链接解析功能
"""
import sys
import os
import importlib.util
import types
import re

# 获取项目根目录
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 包名称
_package_name = "astrbot_plugin_video_parser"

# 创建包模块结构
def _setup_package_structure():
    """设置包结构以支持相对导入"""
    # 创建主包
    if _package_name not in sys.modules:
        _main_package = types.ModuleType(_package_name)
        _main_package.__path__ = [_project_root]
        _main_package.__file__ = os.path.join(_project_root, "__init__.py")
        sys.modules[_package_name] = _main_package
    
    # 创建 parsers 子包
    _parsers_pkg_name = f"{_package_name}.parsers"
    _parsers_dir = os.path.join(_project_root, "parsers")
    
    if _parsers_pkg_name not in sys.modules:
        _parsers_package = types.ModuleType(_parsers_pkg_name)
        _parsers_package.__path__ = [_parsers_dir]
        _parsers_package.__file__ = os.path.join(_parsers_dir, "__init__.py")
        _parsers_package.__package__ = _parsers_pkg_name
        sys.modules[_parsers_pkg_name] = _parsers_package
        setattr(sys.modules[_package_name], "parsers", _parsers_package)
    
    # 加载 base_parser 模块
    _base_parser_file = os.path.join(_parsers_dir, "base_parser.py")
    if os.path.exists(_base_parser_file):
        _base_parser_spec = importlib.util.spec_from_file_location(
            f"{_parsers_pkg_name}.base_parser", _base_parser_file
        )
        _base_parser_module = importlib.util.module_from_spec(_base_parser_spec)
        _base_parser_module.__package__ = _parsers_pkg_name
        sys.modules[f"{_parsers_pkg_name}.base_parser"] = _base_parser_module
        _base_parser_spec.loader.exec_module(_base_parser_module)
        setattr(sys.modules[_parsers_pkg_name], "base_parser", _base_parser_module)
    
    # 加载所有解析器模块
    _parser_files = {
        "bilibili": "bilibili.py",
        "douyin": "douyin.py",
        "twitter": "twitter.py",
        "kuaishou": "kuaishou.py",
    }
    
    for _parser_name, _parser_file in _parser_files.items():
        _parser_path = os.path.join(_parsers_dir, _parser_file)
        if os.path.exists(_parser_path):
            _parser_module_name = f"{_parsers_pkg_name}.{_parser_name}"
            _parser_spec = importlib.util.spec_from_file_location(
                _parser_module_name, _parser_path
            )
            _parser_module = importlib.util.module_from_spec(_parser_spec)
            _parser_module.__package__ = _parsers_pkg_name
            sys.modules[_parser_module_name] = _parser_module
            _parser_spec.loader.exec_module(_parser_module)
            setattr(sys.modules[_parsers_pkg_name], _parser_name, _parser_module)
    
    # 加载 parsers/__init__.py（必须在所有解析器模块加载后）
    _parsers_init_file = os.path.join(_parsers_dir, "__init__.py")
    if os.path.exists(_parsers_init_file):
        _parsers_init_spec = importlib.util.spec_from_file_location(
            _parsers_pkg_name, _parsers_init_file
        )
        _parsers_init_module = importlib.util.module_from_spec(_parsers_init_spec)
        _parsers_init_module.__package__ = _parsers_pkg_name
        sys.modules[_parsers_pkg_name] = _parsers_init_module
        _parsers_init_spec.loader.exec_module(_parsers_init_module)
        # 将 parsers 模块添加到主包
        setattr(sys.modules[_package_name], "parsers", _parsers_init_module)
    
    # 加载 parser_manager 模块
    # 使用 importlib 加载，确保相对导入能够工作
    _parser_manager_file = os.path.join(_project_root, "parser_manager.py")
    if os.path.exists(_parser_manager_file):
        _parser_manager_spec = importlib.util.spec_from_file_location(
            "parser_manager", _parser_manager_file
        )
        _parser_manager_module = importlib.util.module_from_spec(_parser_manager_spec)
        _parser_manager_module.__package__ = _package_name
        # 确保模块可以访问包
        _parser_manager_module.__dict__[_package_name] = sys.modules[_package_name]
        sys.modules["parser_manager"] = _parser_manager_module
        _parser_manager_spec.loader.exec_module(_parser_manager_module)

# 设置包结构
_setup_package_structure()

# 现在可以正常导入
import asyncio
import aiohttp
import shutil
import traceback
from urllib.parse import urlparse
from typing import Optional, Dict, Any

# 导入解析器管理器
from parser_manager import ParserManager
from parsers import BilibiliParser, DouyinParser, TwitterParser, KuaishouParser


class LocalTestTwitterParser(TwitterParser):
    """本地测试用的Twitter解析器包装器，解析时不下载文件，只保存URL信息"""

    async def parse(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict[str, Any]]:
        """
        解析Twitter链接，但不下载文件，只保存URL信息
        Args:
            session: aiohttp会话
            url: Twitter链接
        Returns:
            解析结果字典，包含视频/图片URL但不包含文件路径
        """
        try:
            tweet_id_match = re.search(r'/status/(\d+)', url)
            if not tweet_id_match:
                return None
            tweet_id = tweet_id_match.group(1)
            media_info = await self._fetch_media_info(session, tweet_id)
            if not media_info.get('images') and not media_info.get('videos'):
                raise RuntimeError("解析失败：推文不包含图片或视频")
            
            video_files = []
            has_large_video = False
            max_video_size = None
            
            # 处理视频：只保存URL信息，不下载
            if media_info.get('videos'):
                for idx, video_info in enumerate(media_info['videos']):
                    video_url = video_info.get('url')
                    if video_url:
                        video_size = await self.get_video_size(video_url, session, referer=url)
                        if self.max_video_size_mb > 0 and video_size is not None:
                            if video_size > self.max_video_size_mb:
                                continue
                        exceeds_large_threshold = False
                        if self.large_video_threshold_mb > 0 and video_size is not None and video_size > self.large_video_threshold_mb:
                            if self.max_video_size_mb <= 0 or video_size <= self.max_video_size_mb:
                                exceeds_large_threshold = True
                                has_large_video = True
                        # 不下载文件，只保存URL信息
                        video_files.append({
                            'url': video_url,
                            'thumbnail': video_info.get('thumbnail', ''),
                            'duration': video_info.get('duration', 0),
                            'exceeds_large_threshold': exceeds_large_threshold,
                            'file_size_mb': video_size
                        })
                        if video_size is not None:
                            if max_video_size is None or video_size > max_video_size:
                                max_video_size = video_size
            
            # 处理图片：只保存URL信息，不下载
            image_urls = []
            if media_info.get('images'):
                image_urls = media_info['images']
            
            if not video_files and not image_urls:
                raise RuntimeError("解析失败：无有效的媒体内容")
            
            result = {
                "video_url": url,
                "title": media_info.get('text', '')[:100] or "Twitter 推文",
                "author": media_info.get('author', ''),
                "desc": media_info.get('text', ''),
            }
            
            if video_files:
                result['video_files'] = video_files
                result['is_twitter_video'] = True
                result['has_large_video'] = has_large_video
                if has_large_video:
                    result['force_separate_send'] = True
                if max_video_size is not None:
                    result['file_size_mb'] = max_video_size
                # 保存第一个视频的URL作为direct_url，用于下载
                if video_files:
                    result['direct_url'] = video_files[0].get('url')
            
            if image_urls:
                result['images'] = image_urls
                result['is_twitter_images'] = True
                if len(image_urls) > 1:
                    result['is_gallery'] = True
            
            return result
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"解析失败：{str(e)}")


def init_parsers(use_proxy=False, proxy_url=None):
    """
    初始化解析器
    Args:
        use_proxy: 是否使用代理（Twitter/X需要代理才能访问）
        proxy_url: 代理地址（格式：http://host:port 或 socks5://host:port）
    Returns:
        ParserManager: 解析器管理器
    """
    # 本地测试时，所有解析器都不使用缓存目录
    # 解析结果只保存在内存中，包含URL信息
    # 用户选择下载时，再从URL下载到download目录
    
    parsers = [
        BilibiliParser(
            max_video_size_mb=0.0,
            large_video_threshold_mb=50.0,
            cache_dir=None
        ),
        DouyinParser(
            max_video_size_mb=0.0,
            large_video_threshold_mb=50.0,
            cache_dir=None
        ),
        LocalTestTwitterParser(
            max_video_size_mb=0.0,
            large_video_threshold_mb=50.0,
            use_proxy=use_proxy,
            proxy_url=proxy_url,
            cache_dir=None
        ),
        KuaishouParser(
            max_video_size_mb=0.0,
            large_video_threshold_mb=50.0,
            cache_dir=None
        )
    ]
    return ParserManager(parsers)


def print_metadata(result: dict, url: str, parser_name: str):
    """打印解析后的元数据"""
    print("\n" + "=" * 80)
    print(f"解析器: {parser_name}")
    print(f"原始链接: {url}")
    print("-" * 80)
    print(f"标题: {result.get('title', 'N/A')}")
    print(f"作者: {result.get('author', 'N/A')}")
    desc = result.get('desc', '')
    if desc:
        if len(desc) > 100:
            print(f"描述: {desc[:100]}...")
        else:
            print(f"描述: {desc}")
    else:
        print("描述: N/A")

    if result.get('video_files'):
        print("\n视频信息:")
        for idx, video_file in enumerate(result['video_files'], 1):
            video_url = video_file.get('url') or video_file.get('direct_url')
            file_path = video_file.get('file_path')
            if video_url:
                print(f"  [{idx}] 视频URL: {video_url}")
            elif file_path:
                print(f"  [{idx}] 文件路径: {file_path}")
            else:
                print(f"  [{idx}] 视频信息: N/A")
            file_size = video_file.get('file_size_mb')
            if file_size is not None:
                print(f"      大小: {file_size:.2f} MB")
            else:
                print("      大小: N/A")
            thumbnail = video_file.get('thumbnail')
            if thumbnail:
                print(f"      缩略图: {thumbnail}")
            duration = video_file.get('duration')
            if duration:
                print(f"      时长: {duration} 秒")

    if result.get('image_files'):
        print(f"\n图片文件 ({len(result['image_files'])} 张):")
        for idx, image_file in enumerate(result['image_files'], 1):
            print(f"  [{idx}] {image_file}")

    if result.get('direct_url'):
        print(f"\n视频直链: {result.get('direct_url')}")

    if result.get('images') and not result.get('image_files'):
        print(f"\n图片URL ({len(result['images'])} 张):")
        for idx, image_url in enumerate(result['images'], 1):
            print(f"  [{idx}] {image_url}")

    if result.get('file_size_mb'):
        print(f"\n视频大小: {result.get('file_size_mb'):.2f} MB")

    if result.get('is_gallery'):
        print("\n图集: 是")

    if result.get('force_separate_send'):
        print("\n强制单独发送: 是")

    if result.get('timestamp'):
        print(f"\n时间戳: {result.get('timestamp')}")

    print("=" * 80)


async def download_file(session: aiohttp.ClientSession, url: str, filepath: str, referer: str = None, proxy: str = None, headers: dict = None) -> bool:
    """
    下载文件到指定路径
    Args:
        session: aiohttp会话
        url: 文件URL
        filepath: 保存路径
        referer: Referer请求头
        proxy: 代理地址（格式：http://host:port 或 socks5://host:port）
        headers: 自定义请求头（如果提供，会与默认请求头合并）
    Returns:
        bool: 下载是否成功
    """
    try:
        # 默认请求头
        default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'image',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'cross-site',
        }
        
        # 合并自定义请求头
        if headers:
            default_headers.update(headers)
        
        # 设置Referer
        if referer:
            default_headers['Referer'] = referer
        
        # 对于Twitter图片/视频，如果没有提供Referer，使用默认值
        if 'pbs.twimg.com' in url or 'video.twimg.com' in url:
            if 'Referer' not in default_headers:
                default_headers['Referer'] = 'https://x.com/'
        
        async with session.get(
            url, 
            headers=default_headers, 
            timeout=aiohttp.ClientTimeout(total=300, connect=30),
            proxy=proxy
        ) as response:
            response.raise_for_status()
            file_dir = os.path.dirname(filepath)
            if file_dir:
                os.makedirs(file_dir, exist_ok=True)
            with open(filepath, 'wb') as f:
                async for chunk in response.content.iter_chunked(8192):
                    f.write(chunk)
                # 立即刷新缓冲区到磁盘
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
        return True
    except aiohttp.ClientConnectorError as e:
        error_msg = str(e)
        if 'pbs.twimg.com' in url or 'video.twimg.com' in url or 'x.com' in url or 'twitter.com' in url:
            print(f"下载失败: {error_msg}")
            print("提示: Twitter/X 在中国大陆需要代理才能访问。")
            print("      请在脚本中配置代理：修改 init_parsers(use_proxy=True, proxy_url='your_proxy_url')")
        else:
            print(f"下载失败: {error_msg}")
        return False
    except Exception as e:
        print(f"下载失败: {e}")
        return False


async def download_media(result: dict, url: str, download_dir: str, session: aiohttp.ClientSession, parser=None):
    """
    下载媒体文件
    Args:
        result: 解析结果
        url: 原始链接
        download_dir: 下载目录
        session: aiohttp会话
        parser: 解析器实例（用于获取代理设置等）
    """
    download_dir = os.path.abspath(download_dir)
    os.makedirs(download_dir, exist_ok=True)
    
    # 获取代理设置（如果解析器支持）
    proxy = None
    download_headers = None
    if parser and hasattr(parser, 'use_proxy') and hasattr(parser, 'proxy_url'):
        if parser.use_proxy and parser.proxy_url:
            proxy = parser.proxy_url
    if parser and hasattr(parser, 'headers'):
        download_headers = parser.headers.copy()

    # 为每个链接创建子目录（基于域名和路径）
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.replace('.', '_').replace(':', '_')
    path_parts = parsed_url.path.strip('/').split('/')
    path_parts = [p for p in path_parts if p and len(p) > 0]
    if path_parts:
        path = '_'.join(path_parts[:2])
        path = re.sub(r'[^\w\-_]', '_', path)
        if len(path) > 30:
            path = path[:30]
        link_dir_name = f"{domain}_{path}"
    else:
        link_dir_name = f"{domain}_root"

    link_dir = os.path.join(download_dir, link_dir_name)
    link_dir = os.path.normpath(link_dir)
    os.makedirs(link_dir, exist_ok=True)

    downloaded_files = []

    # 下载视频文件
    # 本地测试时，解析结果只包含URL信息，不包含文件路径
    # 所有视频都从URL下载到download目录
    video_urls = []
    
    # 从video_files中提取URL（适用于Twitter等有video_files的情况）
    if result.get('video_files'):
        for idx, video_file in enumerate(result['video_files'], 1):
            video_url = video_file.get('url') or video_file.get('direct_url')
            if video_url:
                video_urls.append((idx, video_url))
            else:
                # 兼容性：如果有file_path且文件存在，复制文件（正常情况下不应该发生）
                file_path = video_file.get('file_path')
                if file_path and os.path.exists(file_path):
                    filename = os.path.basename(file_path) or f"video_{idx}.mp4"
                    dest_path = os.path.join(link_dir, filename)
                    shutil.copy2(file_path, dest_path)
                    downloaded_files.append(dest_path)
                    print(f"✓ 已复制视频文件: {dest_path}")
                else:
                    print(f"⚠ 视频 {idx} 无法下载：无有效的URL")
    
    # 如果没有video_files，但有direct_url，使用direct_url（适用于Bilibili、Douyin、Kuaishou等）
    if not video_urls and result.get('direct_url'):
        video_urls.append((1, result.get('direct_url')))
    
    # 从URL下载所有视频到download目录
    for idx, video_url in video_urls:
        filename = f"video_{idx}.mp4"
        dest_path = os.path.join(link_dir, filename)
        print(f"正在下载视频 {idx}...")
        referer = url
        # 对于Twitter视频，设置正确的Referer
        headers = download_headers
        if 'video.twimg.com' in video_url or 'pbs.twimg.com' in video_url:
            # 从原始URL提取tweet_id
            tweet_id_match = re.search(r'/status/(\d+)', url)
            if tweet_id_match:
                tweet_id = tweet_id_match.group(1)
                referer = f'https://x.com/status/{tweet_id}'
            else:
                referer = 'https://x.com/'
            # 对于Twitter视频，使用解析器的headers（包含Accept等）
            if parser and hasattr(parser, 'headers'):
                headers = parser.headers.copy()
                if referer:
                    headers['Referer'] = referer
        if await download_file(session, video_url, dest_path, referer=referer, proxy=proxy, headers=headers):
            downloaded_files.append(dest_path)
            print(f"✓ 已下载视频: {dest_path}")
        else:
            print(f"⚠ 视频 {idx} 下载失败")

    # 下载图片文件
    # 本地测试时，所有图片都从URL下载
    # 首先处理image_files（可能是文件路径，兼容性处理）
    if result.get('image_files'):
        for idx, image_file in enumerate(result['image_files'], 1):
            if isinstance(image_file, str):
                # 如果是文件路径且文件存在，复制文件（兼容性处理）
                if os.path.exists(image_file):
                    filename = os.path.basename(image_file) or f"image_{idx}.jpg"
                    dest_path = os.path.join(link_dir, filename)
                    shutil.copy2(image_file, dest_path)
                    downloaded_files.append(dest_path)
                    print(f"✓ 已复制图片: {dest_path}")
                # 否则忽略（可能是临时文件路径，但文件不存在）
    
    # 从URL下载图片（适用于所有解析器）
    if result.get('images'):
        for idx, image_url in enumerate(result['images'], 1):
            # 从URL推断文件扩展名
            ext = '.jpg'
            if '.png' in image_url.lower():
                ext = '.png'
            elif '.webp' in image_url.lower():
                ext = '.webp'
            elif '.gif' in image_url.lower():
                ext = '.gif'
            filename = f"image_{idx}{ext}"
            dest_path = os.path.join(link_dir, filename)
            print(f"正在下载图片 {idx}...")
            referer = url
            # 对于Twitter图片，设置正确的Referer
            if 'pbs.twimg.com' in image_url:
                # 从原始URL提取tweet_id
                tweet_id_match = re.search(r'/status/(\d+)', url)
                if tweet_id_match:
                    tweet_id = tweet_id_match.group(1)
                    referer = f'https://x.com/status/{tweet_id}'
                else:
                    referer = 'https://x.com/'
            # 对于Twitter图片，使用解析器的headers（包含Accept等）
            headers = download_headers
            if 'pbs.twimg.com' in image_url and parser and hasattr(parser, 'headers'):
                headers = parser.headers.copy()
                if referer:
                    headers['Referer'] = referer
            if await download_file(session, image_url, dest_path, referer=referer, proxy=proxy, headers=headers):
                downloaded_files.append(dest_path)
                print(f"✓ 已下载图片: {dest_path}")
            else:
                print(f"⚠ 图片 {idx} 下载失败")


    if downloaded_files:
        print(f"\n所有文件已保存到: {link_dir}")
    else:
        print("\n没有可下载的文件")


async def main():
    """主函数"""
    print("=" * 80)
    print("视频链接解析测试工具")
    print("=" * 80)
    print("\n支持的平台: B站、抖音、Twitter/X、快手")
    print("退出方式:")
    print("  - 输入链接时: 输入 'q' / 'quit' / 'exit' 退出程序")
    print("  - 询问下载时: 输入 'q' 也可以退出程序\n")
    
    # 代理配置（Twitter/X 在墙内需要代理才能访问）
    # 如果需要在本地测试时使用代理，请取消注释并修改以下配置：
    # use_proxy = True
    # proxy_url = "http://127.0.0.1:7890"  # HTTP代理，例如 Clash
    # proxy_url = "socks5://127.0.0.1:1080"  # SOCKS5代理，例如 V2Ray
    use_proxy = True
    proxy_url = "http://127.0.0.1:7897" # clash verge 默认端口，请使用正确的代理配置
    
    parser_manager = init_parsers(use_proxy=use_proxy, proxy_url=proxy_url)
    download_dir = os.path.join(os.path.dirname(__file__), "download")
    os.makedirs(download_dir, exist_ok=True)
    
    if use_proxy:
        print(f"✓ 已启用代理: {proxy_url}")
    else:
        print("提示: Twitter/X 链接需要代理才能下载。")
        print("      如需使用代理，请修改脚本中的 use_proxy 和 proxy_url 配置（第538-539行）。")
    print()

    timeout = aiohttp.ClientTimeout(total=60)

    while True:
        try:
            text = input("请输入包含视频链接的文本（输入 q/quit/exit 退出）: ").strip()

            if text.lower() in ('quit', 'exit', 'q', '退出'):
                print("再见！")
                break

            if not text:
                print("输入不能为空，请重新输入。")
                continue

            print(f"\n正在解析: {text}")
            print("-" * 80)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 提取链接
                links_with_parser = parser_manager.extract_all_links(text)
                if not links_with_parser:
                    print("未找到可解析的链接")
                    continue

                print(f"找到 {len(links_with_parser)} 个链接")

                # 解析每个链接
                should_exit_loop = False
                for url, parser in links_with_parser:
                    if should_exit_loop:
                        break
                    print(f"\n解析链接: {url}")
                    try:
                        result = await parser.parse(session, url)
                        if result:
                            parser_name = parser.name if hasattr(parser, 'name') else type(parser).__name__
                            print_metadata(result, url, parser_name)

                            # 询问是否下载
                            while True:
                                choice = input("\n是否下载到本地? (y/n/q退出): ").strip().lower()
                                if choice in ('y', 'yes', '是'):
                                    await download_media(result, url, download_dir, session, parser=parser)
                                    break
                                elif choice in ('n', 'no', '否'):
                                    print("跳过下载")
                                    break
                                elif choice in ('q', 'quit', 'exit', '退出'):
                                    print("再见！")
                                    should_exit_loop = True
                                    break
                                else:
                                    print("请输入 y、n 或 q（退出）")
                            
                            if should_exit_loop:
                                break
                        else:
                            print(f"解析失败: {url}")
                    except Exception as e:
                        error_msg = str(e)
                        if error_msg.startswith("解析失败："):
                            print(f"{error_msg}")
                        else:
                            print(f"解析出错: {error_msg}")
                        traceback.print_exc()
                
                if should_exit_loop:
                    return

                print("\n" + "=" * 80 + "\n")

        except KeyboardInterrupt:
            print("\n\n程序已中断")
            break
        except Exception as e:
            print(f"\n发生错误: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
