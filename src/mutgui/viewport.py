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

    def __init__(
        self,
        view: View,
        channel: Channel,
        *,
        _path: list[str | int] | None = None,
    ) -> None:
        """创建 ViewPort，绑定 View 和 Channel。"""
        raise NotImplementedError

    async def initialize(self) -> None:
        """首次 render，推送完整树。先推父，再推子。"""
        raise NotImplementedError

    async def handle_event(self, event: dict[str, Any]) -> None:
        """处理前端事件 → 转交 View.handle_event()。"""
        raise NotImplementedError

    async def send_command(self, name: str, /, **args: Any) -> None:
        """触发前端命令。fire-and-forget，无返回值。"""
        raise NotImplementedError

    def detach(self) -> None:
        """从 View 解除绑定，移除观察者注册。"""
        raise NotImplementedError


from . import _viewport_impl as _viewport_impl  # noqa: F401, E402
