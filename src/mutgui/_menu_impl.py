"""MenuView + MenuTrigger 实现。"""

from __future__ import annotations

from typing import Any

from mutobj import impl

from ._view_impl import render_ext
from .events import Event, EventFilter
from .menu import MenuView, MenuTrigger
from .view import View


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
    if self.owner is None:
        return
    ext = render_ext(self.owner)
    ext.overlay_children.pop(self.id, None)
    self.owner.invalidate()
    self.owner = None


# ---------------------------------------------------------------------------
# @impl — MenuTrigger
# ---------------------------------------------------------------------------

@impl(MenuTrigger.handle)
async def menu_trigger_handle(self: MenuTrigger, view: View, event: Event) -> bool:
    from .events import _build_dispatch_context, _eval_kwargs

    # 从 event.data 提取前端 resolve 后的原始 wire 值（跳过 $* 元数据）
    # 仅用于向后兼容 — 新 API 所有 wire 参数都在 self.extract 中明确声明
    dispatch_context = _build_dispatch_context(view, event)
    context = _eval_kwargs(self.extract, event.data, dispatch_context)

    # 关闭已有菜单
    ext = render_ext(view)
    for child in list(ext.overlay_children.values()):
        if isinstance(child, MenuView):
            await child.close()

    # 创建新菜单
    menu_view = self.menu_factory(**context)
    if not isinstance(menu_view, MenuView):  # pyright: ignore[reportUnnecessaryIsInstance]
        return False

    menu_view.owner = view
    menu_view.install_event_filter(_close_filter)
    ext.overlay_children[menu_view.id] = menu_view
    view.invalidate()
    return True
