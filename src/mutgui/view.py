"""View — 后端驱动 UI 的核心抽象。"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

import mutobj

if TYPE_CHECKING:
    from .events import Event, EventFilter


class View(mutobj.Declaration):
    """mutgui 视图基类。

    应用开发者继承此类，覆盖 render() 描述 UI 应该长什么样。
    框架负责 render -> serialize -> send 循环。
    """

    id: str | int = ""

    def render(self) -> list[Any] | dict[str, Any]:
        """声明当前 UI 应该长什么样。

        返回组件列表 (list[dict | View]) 或单根组件 (dict)。
        列表中可包含子 View 实例，框架自动转换为 $view 协议节点。
        """
        ...

    async def on_event(self, event: Event) -> bool:
        """统一事件入口。

        默认实现：查找 render 中注册的 EventHandler，调用 handle()。
        子类重写可拦截、预处理、后处理，再 super() 走默认分派。
        返回 True 表示事件已消费。
        """
        ...

    def invalidate(self) -> None:
        """标记需要重新 render，合并到下一次推送。"""
        ...

    def install_event_filter(self, filter: EventFilter) -> None:
        """注册 event filter。filter 在 on_event 之前看到事件。"""
        ...

    async def handle_event(self, event: dict[str, Any]) -> None:
        """处理前端事件 — 解析 WebSocket 消息，路由到目标 View。"""
        ...

    async def rendered(self) -> None:
        """等待 deferred render 完成。如果不 dirty，立即返回。"""
        ...
