"""MenuView + MenuTrigger 实现。"""

from __future__ import annotations

from typing import Any

from mutobj import impl

from ._view_impl import _render_ext
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
async def _menu_close(self: MenuView) -> None:
    if self._owner is None:
        return
    ext = _render_ext(self._owner)
    ext._overlay_children.pop(self.id, None)
    self._owner.invalidate()
    self._owner = None


# ---------------------------------------------------------------------------
# @impl — MenuTrigger
# ---------------------------------------------------------------------------

@impl(MenuTrigger.handle)
async def _menu_trigger_handle(self: MenuTrigger, view: View, event: Event) -> bool:
    context: dict[str, Any] = {}
    for k, v in event.data.items():
        if k == "$args" or k.startswith("$"):
            continue
        context[k] = v

    # @-prefix: 后端注入
    inject_sources = {"event": event, "view": view}
    for k, v in self.extract.items():
        if isinstance(v, str) and v.startswith("@"):
            parts = v[1:].split(".")
            obj: Any = inject_sources.get(parts[0])
            for attr in parts[1:]:
                obj = getattr(obj, attr, None)
            context[k] = obj

    # 关闭已有菜单
    ext = _render_ext(view)
    for child in list(ext._overlay_children.values()):
        if isinstance(child, MenuView):
            await child.close()

    # 创建新菜单
    menu_view = self.menu_factory(**context)
    if not isinstance(menu_view, MenuView):
        return False

    menu_view._owner = view
    menu_view.install_event_filter(_close_filter)
    ext._overlay_children[menu_view.id] = menu_view
    view.invalidate()
    return True
