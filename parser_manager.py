# -*- coding: utf-8 -*-
"""
解析器管理器
统一管理和调度所有视频解析器
"""
from typing import List, Dict, Any, Optional, Tuple
import asyncio
import aiohttp
from .parsers.base_parser import BaseVideoParser


class ParserManager:
    """解析器管理器"""
    
    def __init__(self, parsers: List[BaseVideoParser]):
        """
        初始化解析器管理器
        
        Args:
            parsers: 解析器列表（必需）
        """
        if not parsers:
            raise ValueError("parsers 参数不能为空")
        self.parsers = parsers
    
    def register_parser(self, parser: BaseVideoParser):
        """
        注册新的解析器
        
        Args:
            parser: 继承自BaseVideoParser的解析器实例
        """
        if parser not in self.parsers:
            self.parsers.append(parser)
    
    def find_parser(self, url: str) -> Optional[BaseVideoParser]:
        """
        根据URL查找合适的解析器
        
        Args:
            url: 视频链接
            
        Returns:
            能解析该URL的解析器，如果找不到则返回None
        """
        for parser in self.parsers:
            if parser.can_parse(url):
                return parser
        return None
    
    def extract_all_links(self, text: str) -> List[Tuple[str, BaseVideoParser]]:
        """
        从文本中提取所有可解析的链接，并返回链接和对应的解析器
        按照链接在文本中出现的顺序返回
        
        Args:
            text: 输入文本
            
        Returns:
            List[Tuple[str, BaseVideoParser]]: (链接, 解析器) 的列表，按文本中出现顺序
        """
        # 收集所有链接及其在文本中的位置
        links_with_position = []
        for parser in self.parsers:
            links = parser.extract_links(text)
            for link in links:
                # 查找链接在文本中的位置
                position = text.find(link)
                if position != -1:
                    links_with_position.append((position, link, parser))
        
        # 按位置排序，保持文本中的原始顺序
        links_with_position.sort(key=lambda x: x[0])
        
        # 去重：保留第一个出现的链接
        seen_links = set()
        links_with_parser = []
        for position, link, parser in links_with_position:
            if link not in seen_links:
                seen_links.add(link)
                links_with_parser.append((link, parser))
        
        return links_with_parser
    
    def _deduplicate_links(self, links_with_parser: List[Tuple[str, BaseVideoParser]]) -> Dict[str, BaseVideoParser]:
        """
        对链接进行去重，保留第一个出现的链接
        
        Args:
            links_with_parser: (链接, 解析器) 的列表
            
        Returns:
            Dict[str, BaseVideoParser]: 去重后的链接字典
        """
        unique_links = {}
        for link, parser in links_with_parser:
            if link not in unique_links:
                unique_links[link] = parser
        return unique_links
    
    async def parse_url(self, url: str, session: aiohttp.ClientSession) -> Optional[Dict[str, Any]]:
        """
        解析单个URL
        
        Args:
            url: 视频链接
            session: aiohttp会话
            
        Returns:
            解析结果，如果无法解析则返回None
        """
        parser = self.find_parser(url)
        if parser is None:
            return None
        return await parser.parse(session, url)
    
    async def parse_text(self, text: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        """
        解析文本中的所有链接
        
        Args:
            text: 输入文本
            session: aiohttp会话
            
        Returns:
            解析结果列表
        """
        links_with_parser = self.extract_all_links(text)
        if not links_with_parser:
            return []
        
        unique_links = self._deduplicate_links(links_with_parser)
        tasks = [parser.parse(session, url) for url, parser in unique_links.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [result for result in results if result and not isinstance(result, Exception)]
    
    async def build_nodes(self, event, is_auto_pack: bool) -> Optional[tuple]:
        """
        构建消息节点
        
        Args:
            event: AstrMessageEvent事件对象
            is_auto_pack: 是否打包为Node
            
        Returns:
            (普通链接节点列表, 大视频链接节点列表, 临时文件路径列表, 视频文件路径列表, 链接数量) 元组，如果没有可解析的链接则返回None
            普通链接节点列表：每个元素是一个链接的节点列表（没有大视频的链接），可以打包发送
            大视频链接节点列表：每个元素是一个链接的节点列表（有大视频的链接），需要单独发送
        """
        try:
            input_text = event.message_str
            links_with_parser = self.extract_all_links(input_text)
            if not links_with_parser:
                return None
            
            unique_links = self._deduplicate_links(links_with_parser)
            
            normal_link_nodes = []  # 普通链接节点列表，每个元素是一个链接的节点列表
            large_video_link_nodes = []  # 大视频链接节点列表，每个元素是一个链接的节点列表
            normal_link_count = 0  # 普通链接数量（用于决定节点组装方式）
            temp_files = []
            video_files = []
            sender_name = "视频解析bot"
            platform = event.get_platform_name()
            sender_id = event.get_self_id()
            if platform not in ("wechatpadpro", "webchat", "gewechat"):
                try:
                    sender_id = int(sender_id)
                except (ValueError, TypeError):
                    sender_id = 10000
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url_parser_pairs = list(unique_links.items())
                tasks = [parser.parse(session, url) for url, parser in url_parser_pairs]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for (url, parser_instance), result in zip(url_parser_pairs, results):
                    # 处理异常结果或None结果（解析失败）
                    if isinstance(result, Exception) or not result:
                        # 解析失败，创建一个链接的节点列表（扁平化结构）
                        from astrbot.api.message_components import Plain
                        failure_text = f"解析失败\n原始链接：{url}"
                        link_nodes = [Plain(failure_text)]
                        normal_link_nodes.append(link_nodes)
                        normal_link_count += 1  # 统计普通链接数量（包括解析失败的）
                        continue
                    
                    # 检查该链接是否有大视频（需要单独发送）
                    # 优先检查 force_separate_send，如果没有则检查 has_large_video
                    link_has_large_video = result.get('force_separate_send', False) or result.get('has_large_video', False)
                    
                    # 处理图片文件
                    if result.get('image_files'):
                        temp_files.extend(result['image_files'])
                    
                    # 处理视频文件
                    if result.get('video_files'):
                        for video_file_info in result['video_files']:
                            file_path = video_file_info.get('file_path')
                            if file_path:
                                video_files.append(file_path)
                    
                    # 为当前链接构建节点列表（扁平化结构）
                    link_nodes = []
                    
                    # 构建文本节点（统一返回 Plain 对象）
                    text_node = parser_instance.build_text_node(result, sender_name, sender_id, False)
                    if text_node:
                        link_nodes.append(text_node)
                    
                    # 构建媒体节点（统一返回 Image/Video 对象列表）
                    media_nodes = parser_instance.build_media_nodes(result, sender_name, sender_id, False)
                    link_nodes.extend(media_nodes)
                    
                    if link_has_large_video:
                        large_video_link_nodes.append(link_nodes)
                    else:
                        normal_link_nodes.append(link_nodes)
                        normal_link_count += 1  # 统计普通链接数量
            
            # 如果没有任何节点，返回None
            if not normal_link_nodes and not large_video_link_nodes:
                return None
            return (normal_link_nodes, large_video_link_nodes, temp_files, video_files, normal_link_count)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError) as e:
            # 捕获预期的异常类型，避免插件崩溃
            # 网络错误、超时、数据格式错误等应该被静默处理
            return None
        except Exception:
            # 捕获其他未预期的异常，避免插件崩溃
            # 在生产环境中，建议记录日志以便调试
            return None

