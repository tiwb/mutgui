"""传输抽象 — 只负责把消息送出去。"""

from __future__ import annotations

from typing import Any


class Transport:
    """传输接口。

    mutgui 核心不包含任何网络代码。具体传输方式（WebSocket、IPC 等）
    由使用方实现此接口。
    """

    async def send(self, message: dict[str, Any]) -> None:
        """发送一条 JSON 消息到前端。"""
        raise NotImplementedError
