"""View Declaration 实现 — ViewObservers + ViewRenderState Extension + @impl。

渲染职责归 View 所有：render -> serialize -> cache -> push 给 ViewPort。
ViewPort 只负责接收 wire_tree 并发送到 Channel。
"""

from __future__ import annotations

import asyncio
from typing import Any, Sequence, TYPE_CHECKING

import mutobj
from mutobj import impl

from .events import Event, EventFilter, EventHandler
from .view import View, ViewBlock

if TYPE_CHECKING:
    from .viewport import ViewPort


# ---------------------------------------------------------------------------
# Extensions
# ---------------------------------------------------------------------------

class ViewObservers(mutobj.Extension[View]):
    """追踪一个 View 实例的所有 ViewPort 观察者。"""

    viewports: list[ViewPort] = mutobj.field(default_factory=list)


class ViewRenderState(mutobj.Extension[View]):
    """View 的渲染状态 — handlers、children、wire_tree 缓存、dirty 标记。"""

    handlers: dict[tuple[str | int, str], EventHandler] = mutobj.field(default_factory=dict)
    children: dict[str | int, View] = mutobj.field(default_factory=dict)
    event_filters: list[EventFilter] = mutobj.field(default_factory=list)
    wire_tree: list[dict[str, Any]] = mutobj.field(default_factory=list)
    dirty: bool = True
    render_scheduled: bool = False
    render_event: asyncio.Event | None = None
    overlay_children: dict[str | int, View] = mutobj.field(default_factory=dict)  # 框架注入的子 View（如菜单）
    view_block: ViewBlock | None = None



def _render_ext(view: View) -> ViewRenderState:
    return ViewRenderState.get_or_create(view)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# @impl — View 默认实现
# ---------------------------------------------------------------------------

@impl(View.render)
def _default_render(self: View) -> ViewBlock:
    return ViewBlock([])


@impl(View.on_event)
async def _default_on_event(self: View, event: Event) -> bool:
    ext = _render_ext(self)
    handler = ext.handlers.get((event.component_id, event.name))
    if handler is not None:
        return await handler.handle(self, event)
    return False


@impl(View.invalidate)
def _view_invalidate(self: View) -> None:
    ext = _render_ext(self)
    ext.dirty = True
    if ext.render_scheduled:
        return
    ext.render_scheduled = True
    try:
        loop = asyncio.get_running_loop()
        loop.call_soon(lambda: asyncio.ensure_future(_deferred_render(self)))
    except RuntimeError:
        pass  # 无事件循环时只标脏


@impl(View.install_event_filter)
def _view_install_event_filter(self: View, filter: EventFilter) -> None:
    ext = _render_ext(self)
    ext.event_filters.append(filter)


@impl(View.handle_event)
async def _view_handle_event(self: View, event: dict[str, Any]) -> None:
    source = event.get("source", [])
    event_name = event.get("event", "")
    data = event.get("data", {})
    viewport_id = event.get("_viewport_id")
    if isinstance(source, str):
        source = [source] if source else []
    await _route_event(self, source, event_name, data, viewport_id=viewport_id)


@impl(View.render_viewport)
def _default_render_viewport(
    self: View, wire_tree: list[dict[str, Any]], channel_id: int,
) -> list[dict[str, Any]]:
    return wire_tree


@impl(View.rendered)
async def _view_rendered(self: View) -> None:
    ext = _render_ext(self)
    if not ext.dirty and not ext.render_scheduled:
        return
    if ext.render_event is None:
        ext.render_event = asyncio.Event()
    ext.render_event.clear()
    await ext.render_event.wait()


# ---------------------------------------------------------------------------
# 内部实现 — 事件路由
# ---------------------------------------------------------------------------

async def _route_event(
    view: View,
    source: Sequence[str | int],
    event_name: str,
    data: dict[str, Any],
    *,
    viewport_id: int | None = None,
) -> None:
    """按 source 数组逐层路由事件。"""
    ext = _render_ext(view)
    if len(source) > 1:
        child_id = source[0]
        child_view = ext.children.get(child_id)
        if child_view is not None:
            await _route_event(child_view, source[1:], event_name, data,
                               viewport_id=viewport_id)
    elif len(source) == 1:
        component_id = str(source[0])
        event = Event(component_id, event_name, data, viewport_id=viewport_id)

        # Filter 链
        for f in ext.event_filters:
            if await f.on_event_filter(view, event):
                return

        await view.on_event(event)
    else:
        event = Event("", event_name, data, viewport_id=viewport_id)
        await view.on_event(event)


# ---------------------------------------------------------------------------
# 内部实现 — render / cache / push
# ---------------------------------------------------------------------------

def _render_and_cache(view: View) -> None:
    """render -> serialize -> 缓存 wire_tree + handlers + children。"""
    ext = _render_ext(view)
    block = view.render()

    ext.handlers.clear()
    ext.children = {}
    ext.view_block = block
    ext.wire_tree = _process_items(view, block.items)

    # 注入 overlay children（如活跃菜单）
    for child_id, child_view in ext.overlay_children.items():
        ext.children[child_id] = child_view
        ext.wire_tree.append({"$view": child_id})

    # 递归 render dirty 子 View
    for child_view in ext.children.values():
        child_ext = _render_ext(child_view)
        if child_ext.dirty:
            _render_and_cache(child_view)
            child_ext.dirty = False


async def _deferred_render(view: View) -> None:
    """deferred render callback — render -> push -> signal。"""
    ext = _render_ext(view)
    ext.render_scheduled = False

    if not ext.dirty:
        # 防御性：dirty 已被外部清除，仍需 signal 等待者
        if ext.render_event is not None:
            ext.render_event.set()
        return

    _render_and_cache(view)
    ext.dirty = False

    # push to all ViewPorts
    obs = ViewObservers.get(view)
    if obs is not None:
        for vp in obs.viewports:
            await vp._push_render()  # type: ignore[attr-defined]

    # signal rendered
    if ext.render_event is not None:
        ext.render_event.set()


# ---------------------------------------------------------------------------
# 内部实现 — 组件树序列化
# ---------------------------------------------------------------------------

def _process_items(view: View, items: list[Any]) -> list[dict[str, Any]]:
    """处理列表：组件 dict 或 View 实例。"""
    ext = _render_ext(view)
    result: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, View):
            ext.children[item.id] = item
            result.append({"$view": item.id})
        else:
            result.append(_process_node(view, item))
    return result


def _process_node(view: View, node: dict[str, Any]) -> dict[str, Any]:
    """处理单个组件节点：检测 EventHandler，处理 $children。"""
    ext = _render_ext(view)
    result: dict[str, Any] = {}
    node_id: str | int = node.get("$id", "")
    for key, val in node.items():
        if key == "$children" and isinstance(val, list):
            result[key] = _process_items(view, val)
        elif isinstance(val, EventHandler):
            ext.handlers[(node_id, key)] = val
            result[key] = val.to_wire()
        else:
            result[key] = val
    return result
