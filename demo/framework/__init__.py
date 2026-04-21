"""mutgui demo framework — 基于 mutio.net 的 demo 管理框架。

用法::

    python -m demo

启动 Gallery 服务器，自动扫描 demo/examples/ 下的 demo 文件。
"""

from ._routes import MutguiRoute, DemoApp, mutgui_page
from ._channel import WebSocketChannel

__all__ = ["MutguiRoute", "DemoApp", "WebSocketChannel", "mutgui_page"]
