# -*- coding: utf-8 -*-
"""
消息适配器模块
统一管理消息构建和发送逻辑，集中所有 astrbot 消息组件的导入
"""
from .manager import MessageManager

__all__ = ['MessageManager']

