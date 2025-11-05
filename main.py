# -*- coding: utf-8 -*-
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Nodes
from astrbot.core.star.filter.event_message_type import EventMessageType
from .parser_manager import ParserManager
from .parsers import BilibiliParser, DouyinParser, TwitterParser
import re
import os


@register("astrbot_plugin_video_parser", "drdon1234", "统一视频链接解析插件，支持B站、抖音等平台", "1.0.0")
class VideoParserPlugin(Star):
    """统一视频解析插件"""
    
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.is_auto_parse = config.get("is_auto_parse", True)
        self.is_auto_pack = config.get("is_auto_pack", True)
        max_video_size_mb = config.get("max_video_size_mb", 0.0)
        
        parsers = []
        if config.get("enable_bilibili", True):
            parsers.append(BilibiliParser(max_video_size_mb=max_video_size_mb))
        if config.get("enable_douyin", True):
            parsers.append(DouyinParser(max_video_size_mb=max_video_size_mb))
        if config.get("enable_twitter", True):
            use_proxy = config.get("twitter_use_proxy", False)
            proxy_url = config.get("twitter_proxy_url", "")
            cache_dir = config.get("twitter_cache_dir", "/app/sharedFolder/video_parser/cache/twitter")
            parsers.append(TwitterParser(
                max_video_size_mb=max_video_size_mb,
                use_proxy=use_proxy,
                proxy_url=proxy_url,
                cache_dir=cache_dir
            ))
        
        self.parser_manager = ParserManager(parsers)
        self.trigger_keywords = config.get("trigger_keywords", ["视频解析", "解析视频"])

    async def terminate(self):
        """插件终止时的清理工作"""
        pass

    def _should_parse(self, message_str: str) -> bool:
        """
        判断是否应该解析消息
        
        Args:
            message_str: 消息文本
            
        Returns:
            bool: 是否应该解析
        """
        if self.is_auto_parse:
            return True
        
        for keyword in self.trigger_keywords:
            if keyword in message_str:
                return True
        
        if bool(re.search(r'.?B站解析|b站解析|bilibili解析', message_str)):
            return True
        if bool(re.search(r'.?抖音解析', message_str)):
            return True
        
        return False

    def _cleanup_temp_files(self, temp_files: list):
        """清理临时文件"""
        for file_path in temp_files:
            if file_path and os.path.exists(file_path):
                try:
                    os.unlink(file_path)
                except Exception:
                    pass
    
    def _cleanup_video_files(self, video_files: list):
        """清理视频文件"""
        for file_path in video_files:
            if file_path and os.path.exists(file_path):
                try:
                    os.unlink(file_path)
                except Exception:
                    pass
    
    def _cleanup_all_files(self, temp_files: list, video_files: list):
        """清理所有文件"""
        if temp_files:
            self._cleanup_temp_files(temp_files)
        if video_files:
            self._cleanup_video_files(video_files)
    
    @filter.event_message_type(EventMessageType.ALL)
    async def auto_parse(self, event: AstrMessageEvent):
        """自动解析消息中的视频链接"""
        if not self._should_parse(event.message_str):
            return
        
        result = await self.parser_manager.build_nodes(event, self.is_auto_pack)
        if result is None:
            return
        
        nodes, temp_files, video_files = result
        
        try:
            await event.send(event.plain_result("视频解析bot为您服务 ٩( 'ω' )و"))
            if self.is_auto_pack:
                await event.send(event.chain_result([Nodes(nodes)]))
            else:
                for node in nodes:
                    await event.send(event.chain_result([node]))
            
            self._cleanup_all_files(temp_files, video_files)
        except Exception:
            self._cleanup_all_files(temp_files, video_files)
            raise

