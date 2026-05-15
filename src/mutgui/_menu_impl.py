"""MenuView + MenuTrigger 实现。"""

from __future__ import annotations

from typing import Any

import mutobj
from mutobj import impl

from ._view_impl import render_ext
from .events import Event, EventFilter
from .menu import MenuView, MenuTrigger
from .view import View


# ---------------------------------------------------------------------------
# Extension — MenuView 运行时状态
# ---------------------------------------------------------------------------

class MenuRuntime(mutobj.Extension[MenuView]):
    """MenuView 框架运行时状态 — 仅 _menu_impl 内部维护。

    `host` 是菜单的挂载点（overlay_children 容器 + invalidate 目标）。
    业务代码不应访问，生命周期随 MenuView 实例自动回收。
    """

    host: View | None = None


# ---------------------------------------------------------------------------
# EventFilter — 拦截菜单关闭事件
# ---------------------------------------------------------------------------

class _MenuCloseFilter(EventFilter):
    """拦截 $close 事件，关闭菜单。"""

    async def on_event_filter(self, watched: View, event: Event) -> bool:
        if event.name == "$close" and isinstance(watched, MenuView):
            await watched.close()
            return True
        return False


_close_filter = _MenuCloseFilter()


# ---------------------------------------------------------------------------
# @impl — MenuView
# ---------------------------------------------------------------------------

@impl(MenuView.close)
async def menu_close(self: MenuView) -> None:
    rt = MenuRuntime.get(self)
    if rt is None or rt.host is None:
        return
    host = rt.host
    rt.host = None
    ext = render_ext(host)
    ext.overlay_children.pop(self.id, None)
    host.invalidate()


# ---------------------------------------------------------------------------
# @impl — MenuTrigger
# ---------------------------------------------------------------------------

@impl(MenuTrigger.handle)
async def menu_trigger_handle(self: MenuTrigger, view: View, event: Event) -> bool:
    positional, kwargs = self._resolve_call(view, event)

    # 关闭已有菜单
    ext = render_ext(view)
    for child in list(ext.overlay_children.values()):
        if isinstance(child, MenuView):
            await child.close()

    # 创建新菜单
    menu_view = self.menu_factory(*positional, **kwargs)
    if not isinstance(menu_view, MenuView):  # pyright: ignore[reportUnnecessaryIsInstance]
        return False

    MenuRuntime.get_or_create(menu_view).host = view
    menu_view.install_event_filter(_close_filter)
    ext.overlay_children[menu_view.id] = menu_view
    view.invalidate()
    return True
