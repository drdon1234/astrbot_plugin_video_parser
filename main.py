# -*- coding: utf-8 -*-
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Nodes, Plain, Image, Video
from astrbot.core.star.filter.event_message_type import EventMessageType
from .parser_manager import ParserManager
from .parsers import BilibiliParser, DouyinParser, TwitterParser, KuaishouParser
import re
import os


@register("astrbot_plugin_video_parser", "drdon1234", "统一视频链接解析插件，支持B站、抖音等平台", "1.0.0")
class VideoParserPlugin(Star):

    def __init__(self, context: Context, config: dict):
        """
        初始化插件
        Args:
            context: 上下文对象
            config: 配置字典
        """
        super().__init__(context)
        self.is_auto_pack = config.get("is_auto_pack", True)
        trigger_settings = config.get("trigger_settings", {})
        self.is_auto_parse = trigger_settings.get("is_auto_parse", True)
        self.trigger_keywords = trigger_settings.get("trigger_keywords", ["视频解析", "解析视频"])
        video_size_settings = config.get("video_size_settings", {})
        max_video_size_mb = video_size_settings.get("max_video_size_mb", 0.0)
        large_video_threshold_mb = video_size_settings.get("large_video_threshold_mb", 100.0)
        if large_video_threshold_mb > 0:
            large_video_threshold_mb = min(large_video_threshold_mb, 100.0)
        self.large_video_threshold_mb = large_video_threshold_mb
        cache_dir = video_size_settings.get("cache_dir", "/app/sharedFolder/video_parser/cache")
        os.makedirs(cache_dir, exist_ok=True)
        parser_enable_settings = config.get("parser_enable_settings", {})
        enable_bilibili = parser_enable_settings.get("enable_bilibili", True)
        enable_douyin = parser_enable_settings.get("enable_douyin", True)
        enable_twitter = parser_enable_settings.get("enable_twitter", True)
        enable_kuaishou = parser_enable_settings.get("enable_kuaishou", True)
        twitter_proxy_settings = config.get("twitter_proxy_settings", {})
        use_proxy = twitter_proxy_settings.get("twitter_use_proxy", False)
        proxy_url = twitter_proxy_settings.get("twitter_proxy_url", "")
        parsers = []
        if enable_bilibili:
            parsers.append(BilibiliParser(max_video_size_mb=max_video_size_mb, large_video_threshold_mb=large_video_threshold_mb, cache_dir=cache_dir))
        if enable_douyin:
            parsers.append(DouyinParser(max_video_size_mb=max_video_size_mb, large_video_threshold_mb=large_video_threshold_mb, cache_dir=cache_dir))
        if enable_twitter:
            parsers.append(TwitterParser(
                max_video_size_mb=max_video_size_mb,
                large_video_threshold_mb=large_video_threshold_mb,
                use_proxy=use_proxy,
                proxy_url=proxy_url,
                cache_dir=cache_dir
            ))
        if enable_kuaishou:
            parsers.append(KuaishouParser(max_video_size_mb=max_video_size_mb, large_video_threshold_mb=large_video_threshold_mb, cache_dir=cache_dir))
        if not parsers:
            raise ValueError("至少需要启用一个视频解析器。请检查配置中的 parser_enable_settings 设置。")
        self.parser_manager = ParserManager(parsers)

    async def terminate(self):
        """
        插件终止时的清理工作
        """
        pass

    def _should_parse(self, message_str: str) -> bool:
        """
        判断是否应该解析消息
        Args:
            message_str: 消息文本
        Returns:
            bool: 布尔值
        """
        if self.is_auto_parse:
            return True
        for keyword in self.trigger_keywords:
            if keyword in message_str:
                return True
        platform_triggers = [
            r'.?B站解析|b站解析|bilibili解析',
            r'.?抖音解析',
            r'.?快手解析'
        ]
        for pattern in platform_triggers:
            if re.search(pattern, message_str):
                return True
        return False

    def _cleanup_files(self, file_paths: list):
        """
        清理文件列表
        Args:
            file_paths: 文件路径列表
        Returns:
            Any: 返回值
        """
        for file_path in file_paths:
            if file_path and os.path.exists(file_path):
                try:
                    os.unlink(file_path)
                except Exception:
                    pass

    def _cleanup_all_files(self, temp_files: list, video_files: list):
        """
        清理所有临时文件和视频文件
        Args:
            temp_files: 临时文件列表
            video_files: 视频文件列表
        Returns:
            Any: 返回值
        """
        if temp_files:
            self._cleanup_files(temp_files)

    def _is_pure_image_gallery(self, nodes: list) -> bool:
        """
        判断节点列表是否是纯图片图集
        Args:
            nodes: 节点列表
        Returns:
            bool: 布尔值
        """
        has_video = False
        has_image = False
        for node in nodes:
            if isinstance(node, Video):
                has_video = True
                break
            elif isinstance(node, Image):
                has_image = True
        return has_image and not has_video

    @filter.event_message_type(EventMessageType.ALL)
    async def auto_parse(self, event: AstrMessageEvent):
        """
        自动解析消息中的视频链接
        Args:
            event: 消息事件对象
        Returns:
            Any: 返回值
        """
        if not self._should_parse(event.message_str):
            return
        links_with_parser = self.parser_manager.extract_all_links(event.message_str)
        if not links_with_parser:
            return
        await event.send(event.plain_result("视频解析bot为您服务 ٩( 'ω' )و"))
        result = await self.parser_manager.build_nodes(event, self.is_auto_pack)
        if result is None:
            return
        all_link_nodes, link_metadata, temp_files, video_files, normal_link_count = result
        try:
            from astrbot.api.message_components import Node
            sender_name = "视频解析bot"
            platform = event.get_platform_name()
            sender_id = event.get_self_id()
            if platform not in ("wechatpadpro", "webchat", "gewechat"):
                try:
                    sender_id = int(sender_id)
                except (ValueError, TypeError):
                    sender_id = 10000
            separator = "-------------------------------------"
            if self.is_auto_pack:
                normal_metadata = [meta for meta in link_metadata if meta['is_normal']]
                large_video_metadata = [meta for meta in link_metadata if meta['is_large_video']]
                normal_link_nodes = [meta['link_nodes'] for meta in normal_metadata]
                large_video_link_nodes = [meta['link_nodes'] for meta in large_video_metadata]
                if normal_link_nodes:
                    flat_nodes = []
                    for link_idx, link_nodes in enumerate(normal_link_nodes):
                        if self._is_pure_image_gallery(link_nodes):
                            texts = [node for node in link_nodes if isinstance(node, Plain)]
                            images = [node for node in link_nodes if isinstance(node, Image)]
                            for text in texts:
                                flat_nodes.append(Node(name=sender_name, uin=sender_id, content=[text]))
                            if images:
                                flat_nodes.append(Node(name=sender_name, uin=sender_id, content=images))
                        else:
                            for node in link_nodes:
                                if node is not None:
                                    flat_nodes.append(Node(name=sender_name, uin=sender_id, content=[node]))
                        if link_idx < len(normal_link_nodes) - 1:
                            flat_nodes.append(Node(name=sender_name, uin=sender_id, content=[Plain(separator)]))
                    if flat_nodes:
                        await event.send(event.chain_result([Nodes(flat_nodes)]))
                if large_video_link_nodes:
                    threshold_mb = int(self.large_video_threshold_mb) if self.large_video_threshold_mb > 0 else 50
                    notice_text = f"⚠️ 链接中包含超过{threshold_mb}MB的视频时将单独发送所有媒体"
                    await event.send(event.plain_result(notice_text))
                    for link_idx, link_nodes in enumerate(large_video_link_nodes):
                        for node in link_nodes:
                            if node is not None:
                                await event.send(event.chain_result([node]))
                        if link_idx < len(large_video_metadata):
                            link_video_files = large_video_metadata[link_idx].get('video_files', [])
                            if link_video_files:
                                self._cleanup_files(link_video_files)
                        if link_idx < len(large_video_link_nodes) - 1:
                            await event.send(event.plain_result(separator))
                for metadata in normal_metadata:
                    link_video_files = metadata.get('video_files', [])
                    if link_video_files:
                        self._cleanup_files(link_video_files)
            else:
                for link_idx, (link_nodes, metadata) in enumerate(zip(all_link_nodes, link_metadata)):
                    if self._is_pure_image_gallery(link_nodes):
                        texts = [node for node in link_nodes if isinstance(node, Plain)]
                        images = [node for node in link_nodes if isinstance(node, Image)]
                        for text in texts:
                            await event.send(event.chain_result([text]))
                        if images:
                            await event.send(event.chain_result(images))
                    else:
                        for node in link_nodes:
                            if node is not None:
                                await event.send(event.chain_result([node]))
                    link_video_files = metadata.get('video_files', [])
                    if link_video_files:
                        self._cleanup_files(link_video_files)
                    if link_idx < len(all_link_nodes) - 1:
                        await event.send(event.plain_result(separator))
            self._cleanup_all_files(temp_files, video_files)
        except Exception:
            self._cleanup_all_files(temp_files, video_files)
            raise
