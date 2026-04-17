"""View 基类 — 后端驱动 UI 的核心抽象。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .session import ViewSession


class View:
    """mutgui 视图基类。

    应用开发者继承此类，实现 render() 返回组件树。
    框架负责 render → serialize → send 循环。
    """

    id: str | int = ""

    _session: ViewSession | None = None  # 框架管理，勿手动修改

    def render(self) -> list[Any] | dict[str, Any]:
        """声明当前 UI 应该长什么样。

        返回组件列表 (list[dict | View]) 或单根组件 (dict)。
        列表中可包含子 View 实例，框架自动转换为 $view 协议节点。
        """
        return []

    def on_event(self, event: dict[str, Any]) -> None:
        """处理前端事件（fallback）。

        未被 handler/bind 捕获的事件会到达这里。
        """
        pass

    def invalidate(self) -> None:
        """标记需要重新 render，合并到下一次推送。"""
        if self._session is not None:
            self._session._mark_dirty()
