"""mutgui demo framework — 基于 mutio.net 的 demo 管理框架。

用法::

    python -m demo

启动 Gallery 服务器，自动扫描 demo/examples/ 下的 demo 文件。
"""

from ._routes import (
    MutguiRoute,
    DemoApp,
    MODULE_REGISTRY,
    mutgui_boot_script,
    mutgui_mount_div,
    mutgui_page,
    mutgui_runtime_assets,
)
from ._channel import WebSocketChannel

__all__ = [
    "MutguiRoute",
    "DemoApp",
    "MODULE_REGISTRY",
    "WebSocketChannel",
    "mutgui_boot_script",
    "mutgui_mount_div",
    "mutgui_page",
    "mutgui_runtime_assets",
]
