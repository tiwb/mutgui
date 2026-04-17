"""Channel — 通信管道声明。"""

from __future__ import annotations

from typing import Any

import mutobj


class Channel(mutobj.Declaration):
    """通信管道接口。

    mutgui 核心不包含任何网络代码。具体传输方式（WebSocket、IPC 等）
    由使用方子类实现。
    """

    async def send(self, message: dict[str, Any]) -> None:
        """发送一条 JSON 消息到前端。"""
        ...
