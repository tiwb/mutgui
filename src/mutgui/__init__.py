"""mutgui — 后端驱动 UI 框架。"""

__version__ = "0.1.999"

from .events import bind, handler, notify
from .view import View
from .channel import Channel
from .viewport import ViewPort
from .virtual_list import VirtualList, VirtualListItemAdapter

# 加载 impl 模块（注册 @impl 实现）
import mutgui._view_impl as _view_impl  # noqa: F401, E402
import mutgui._viewport_impl as _viewport_impl  # noqa: F401, E402

__all__ = [
    "View",
    "Channel",
    "ViewPort",
    "VirtualList",
    "VirtualListItemAdapter",
    "notify",
    "handler",
    "bind",
]
