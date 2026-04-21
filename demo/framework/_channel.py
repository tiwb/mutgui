"""WebSocketChannel — 基于 mutio.net WebSocketConnection 的 Channel 实现。"""

from __future__ import annotations

from typing import Any

from mutgui import Channel
from mutio.net.server import WebSocketConnection


class WebSocketChannel(Channel):
    """基于 mutio.net WebSocketConnection 的 Channel 实现。"""

    def __init__(self, ws: WebSocketConnection) -> None:
        super().__init__()
        self._ws = ws

    async def send(self, message: dict[str, Any]) -> None:
        await self._ws.send_json(message)
