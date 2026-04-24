"""Channel Declaration 实现 — channel_id 自增分配。"""

from __future__ import annotations

from mutobj import impl

from .channel import Channel

_next_channel_id = 1


@impl(Channel.__init__)
def channel_init(self: Channel) -> None:
    global _next_channel_id
    self.channel_id = _next_channel_id
    _next_channel_id += 1
