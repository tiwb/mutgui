"""菜单系统 — MenuView + MenuTrigger。

MenuView 是渲染在 portal 浮层中的 View，按需创建、关闭销毁。
MenuTrigger 是 EventHandler 子类，声明"此事件弹出菜单"。
"""

from __future__ import annotations

import inspect
import uuid
from typing import Any, Callable, TYPE_CHECKING

from .events import EventHandler
from .view import View

if TYPE_CHECKING:
    from .events import Event


class MenuView(View):
    """菜单 View — render() 输出菜单内容。

    按需创建，关闭时销毁。每次触发创建独立实例，
    自然解决 per-viewport 问题。
    """

    _owner: View | None = None

    def __init__(self) -> None:
        self.id = f"$menu:{uuid.uuid4().hex[:8]}"

    async def close(self) -> None:
        """关闭菜单 — 从宿主 View 移除自身。"""
        ...


class MenuTrigger(EventHandler):
    """菜单触发器 — 声明"此事件弹出菜单"。

    复用 $handler + resolvePath 机制，通过 $menu key 标识身份。
    前端看到 $menu → 走菜单逻辑（记住坐标、发 context、等 push、渲染）。

    参数:
        menu_factory: 接收 context kwargs，返回 MenuView 实例
        placement: 定位策略 ('cursor' | 'bottom' | 'right')
        **context_extract: context 提取路径（resolvePath 语法）
    """

    def __init__(
        self,
        menu_factory: Callable[..., MenuView],
        *,
        placement: str = "cursor",
        **context_extract: str,
    ) -> None:
        self.menu_factory = menu_factory
        self.placement = placement
        self.extract = context_extract

    async def handle(self, view: View, event: Event) -> bool:
        """创建 MenuView 并挂载到宿主 View。"""
        ...

    def to_wire(self) -> dict[str, Any]:
        wire: dict[str, Any] = {
            k: v for k, v in self.extract.items()
            if not (isinstance(v, str) and v.startswith("@"))
        }
        wire["$menu"] = True
        if self.placement != "cursor":
            wire["$placement"] = self.placement
        return {"$handler": wire}


from . import _menu_impl as _menu_impl  # noqa: F401, E402
