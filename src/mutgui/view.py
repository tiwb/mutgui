"""View — 后端驱动 UI 的核心抽象。"""

from __future__ import annotations

from typing import Any

import mutobj


class View(mutobj.Declaration):
    """mutgui 视图基类。

    应用开发者继承此类，覆盖 render() 描述 UI 应该长什么样。
    框架负责 render → serialize → send 循环。
    """

    id: str | int = ""

    def render(self) -> list[Any] | dict[str, Any]:
        """声明当前 UI 应该长什么样。

        返回组件列表 (list[dict | View]) 或单根组件 (dict)。
        列表中可包含子 View 实例，框架自动转换为 $view 协议节点。
        """
        ...

    def on_event(self, event: dict[str, Any]) -> None:
        """处理前端事件（fallback）。

        未被 handler/bind 捕获的事件会到达这里。
        """
        ...

    def invalidate(self) -> None:
        """标记需要重新 render，合并到下一次推送。"""
        ...

    async def handle_event(self, event: dict[str, Any]) -> None:
        """处理前端事件 — 路由到 callback 或 fallback 到 on_event()。

        callback 返回 coroutine 时自动 await，支持异步回调。
        """
        ...

    async def rendered(self) -> None:
        """等待 deferred render 完成。如果不 dirty，立即返回。"""
        ...
