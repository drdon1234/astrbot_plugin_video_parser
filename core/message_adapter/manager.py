# -*- coding: utf-8 -*-
"""
消息管理器
统一管理消息构建和发送的完整流程
"""
from typing import Any, Dict, List, Tuple

from .node_builder import build_all_nodes
from .sender import MessageSender


class MessageManager:
    """消息管理器，整合节点构建和消息发送的协调逻辑"""

    def __init__(self, logger=None):
        """初始化消息管理器

        Args:
            logger: 日志记录器（可选）
        """
        self.logger = logger
        self.sender = MessageSender(logger=logger)

    def get_sender_info(self, event) -> tuple:
        """获取发送者信息

        Args:
            event: 消息事件对象

        Returns:
            包含发送者名称和ID的元组 (sender_name, sender_id)
        """
        return self.sender.get_sender_info(event)

    def build_nodes(
        self,
        metadata_list: List[Dict[str, Any]],
        is_auto_pack: bool,
        sender_name: str,
        sender_id: Any,
        large_video_threshold_mb: float = 0.0,
        max_video_size_mb: float = 0.0
    ) -> Tuple[List[List], List[Dict], List[str], List[str]]:
        """构建所有链接的节点

        Args:
            metadata_list: 元数据列表
            is_auto_pack: 是否打包为Node
            sender_name: 发送者名称
            sender_id: 发送者ID
            large_video_threshold_mb: 大视频阈值(MB)
            max_video_size_mb: 最大允许的视频大小(MB)，用于显示错误信息

        Returns:
            包含(all_link_nodes, link_metadata, temp_files, video_files)的元组
        """
        return build_all_nodes(
            metadata_list,
            is_auto_pack,
            sender_name,
            sender_id,
            large_video_threshold_mb,
            max_video_size_mb
        )

    async def send_results(
        self,
        event,
        all_link_nodes: list,
        link_metadata: list,
        sender_name: str,
        sender_id: Any,
        is_auto_pack: bool,
        large_video_threshold_mb: float = 0.0
    ):
        """发送结果（根据 is_auto_pack 自动选择打包或非打包方式）

        Args:
            event: 消息事件对象
            all_link_nodes: 所有链接节点列表
            link_metadata: 链接元数据列表
            sender_name: 发送者名称
            sender_id: 发送者ID
            is_auto_pack: 是否打包发送
            large_video_threshold_mb: 大视频阈值(MB)
        """
        if is_auto_pack:
            await self.sender.send_packed_results(
                event,
                link_metadata,
                sender_name,
                sender_id,
                large_video_threshold_mb
            )
        else:
            await self.sender.send_unpacked_results(
                event,
                all_link_nodes,
                link_metadata
            )

    async def build_and_send(
        self,
        event,
        metadata_list: List[Dict[str, Any]],
        is_auto_pack: bool,
        large_video_threshold_mb: float = 0.0,
        max_video_size_mb: float = 0.0
    ) -> Tuple[bool, List[str], List[str]]:
        """构建节点并发送消息的完整流程

        Args:
            event: 消息事件对象
            metadata_list: 元数据列表
            is_auto_pack: 是否打包发送
            large_video_threshold_mb: 大视频阈值(MB)
            max_video_size_mb: 最大允许的视频大小(MB)，用于显示错误信息

        Returns:
            包含(是否成功, temp_files, video_files)的元组
        """
        sender_name, sender_id = self.get_sender_info(event)
        
        all_link_nodes, link_metadata, temp_files, video_files = self.build_nodes(
            metadata_list,
            is_auto_pack,
            sender_name,
            sender_id,
            large_video_threshold_mb,
            max_video_size_mb
        )
        
        if not all_link_nodes:
            return False, temp_files, video_files
        
        await self.send_results(
            event,
            all_link_nodes,
            link_metadata,
            sender_name,
            sender_id,
            is_auto_pack,
            large_video_threshold_mb
        )
        
        return True, temp_files, video_files

