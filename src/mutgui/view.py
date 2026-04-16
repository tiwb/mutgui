"""View 基类 — 后端驱动 UI 的核心抽象。"""

from __future__ import annotations

from typing import Any


class View:
    """mutgui 视图基类。

    应用开发者继承此类，实现 render() 返回组件树。
    框架负责 render → serialize → send 循环。
    """

    def render(self) -> list[dict[str, Any]] | dict[str, Any]:
        """声明当前 UI 应该长什么样。

        返回组件列表 (list[dict]) 或单根组件 (dict)。
        框架调用，应用重写。
        """
        return []

    def on_event(self, event: dict[str, Any]) -> None:
        """处理前端事件（fallback）。

        未被 handler/bind 捕获的事件会到达这里。
        """
        pass
