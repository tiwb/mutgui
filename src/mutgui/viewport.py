"""ViewPort — 渲染管道声明。"""

from __future__ import annotations

from typing import Any

import mutobj

from .channel import Channel
from .view import View


class ViewPort(mutobj.Declaration):
    """将一个 View 渲染并推送到一个 Channel。

    每个 ViewPort 代表"一个客户端正在观察一个 View"。
    同一个 View 可以被多个 ViewPort 观察，invalidate() 通知所有。
    """

    def __init__(self, view: View, channel: Channel) -> None:
        """创建 ViewPort，绑定 View 和 Channel。"""
        ...

    async def initialize(self) -> None:
        """首次 render，推送完整树。先推父，再推子。"""
        ...

    async def handle_event(self, event: dict[str, Any]) -> None:
        """处理前端事件 → 路由 → flush dirty views。"""
        ...

    async def flush(self) -> None:
        """Flush 所有 dirty views。

        配合 invalidate() 使用：invalidate 标脏，flush 推送。
        """
        ...

    def detach(self) -> None:
        """从 View 解除绑定，移除观察者注册。"""
        ...
