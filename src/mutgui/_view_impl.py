"""View Declaration 实现 — ViewObservers + ViewRenderState Extension + @impl。

渲染职责归 View 所有：render -> serialize -> cache -> push 给 ViewPort。
ViewPort 只负责接收 wire_tree 并发送到 Channel。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Sequence, Mapping, TYPE_CHECKING, cast

import mutobj
from mutobj import impl

from ._viewport_context import (
    get_current_viewport,
    reset_current_viewport,
    set_current_viewport,
)
from .events import Event, EventFilter, EventHandler
from .view import View, ViewBlock, RenderValue, WireValue, WireTree, WireNode, RenderNode

if TYPE_CHECKING:
    from .viewport import ViewPort


_logger = logging.getLogger("mutgui.view")


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
    wire_tree: WireTree = mutobj.field(default_factory=list)
    dirty: bool = True
    render_scheduled: bool = False
    render_event: asyncio.Event | None = None
    overlay_children: dict[str | int, View] = mutobj.field(default_factory=dict)  # 框架注入的子 View（如菜单）
    view_block: ViewBlock | None = None



def render_ext(view: View) -> ViewRenderState:
    return ViewRenderState.get_or_create(view)


# ---------------------------------------------------------------------------
# @impl — View 默认实现
# ---------------------------------------------------------------------------

@impl(View.render)
def view_render(self: View) -> ViewBlock:
    return ViewBlock([])


@impl(View.on_event)
async def view_on_event(self: View, event: Event) -> bool:
    ext = render_ext(self)
    handler = ext.handlers.get((event.component_id, event.name))
    if handler is not None:
        return await handler.handle(self, event)
    return False


@impl(View.viewport.getter)  # type: ignore[attr-defined]
def getter_viewport(self: View) -> ViewPort:
    viewport = get_current_viewport()
    if viewport is None:
        raise RuntimeError("View.viewport 只能在 ViewPort 事件上下文中访问")
    return viewport


@impl(View.send_command)
async def view_send_command(self: View, name: str, /, **args: Any) -> None:
    await self.viewport.send_command(name, **args)


@impl(View.broadcast_command)
async def view_broadcast_command(self: View, name: str, /, **args: Any) -> None:
    obs = ViewObservers.get(self)
    if obs is None:
        return
    # 顺序串行：channel.send 通常只是 enqueue，无需并发；
    # 单点失败不影响其余 ViewPort。
    for vp in list(obs.viewports):
        try:
            await vp.send_command(name, **args)
        except Exception:
            _logger.exception(
                "broadcast_command(%s) to viewport failed", name,
            )


@impl(View.invalidate)
def view_invalidate(self: View) -> None:
    ext = render_ext(self)
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
def view_install_event_filter(self: View, filter: EventFilter) -> None:
    ext = render_ext(self)
    ext.event_filters.append(filter)


@impl(View.handle_event)
async def view_handle_event(self: View, event: Mapping[str, WireValue]) -> None:
    source = cast("Sequence[str | int]", event.get("source", []))
    event_name = event.get("event", "")
    if not isinstance(event_name, str):
        event_name = ""
    data = cast(dict[str, WireValue], event.get("data", {}))
    viewport_id_raw = event.get("_viewport_id")
    viewport_id: int | None = viewport_id_raw if isinstance(viewport_id_raw, int) else None
    await _route_event(self, source, event_name, data, viewport_id=viewport_id)


@impl(View.render_viewport)
def view_render_viewport(self: View, wire_tree: WireTree, channel_id: int) -> WireTree:
    return wire_tree


@impl(View.render_to_wire)
def view_render_to_wire(self: View, value: RenderValue) -> WireValue:
    return _process_value(self, render_ext(self), value)

@impl(View.rendered)
async def view_rendered(self: View) -> None:
    ext = render_ext(self)
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
    data: Mapping[str, WireValue],
    *,
    viewport_id: int | None = None,
) -> None:
    """按 source 数组逐层路由事件。"""
    ext = render_ext(view)
    if len(source) > 1:
        child_id = source[0]
        child_view = ext.children.get(child_id)
        if child_view is not None:
            current_vp = get_current_viewport()
            child_vp = current_vp
            if current_vp is not None:
                resolver = getattr(current_vp, "_child_viewport", None)
                if callable(resolver):
                    resolved = resolver(child_id)
                    if resolved is not None:
                        child_vp = resolved

            if child_vp is current_vp or child_vp is None:
                await _route_event(child_view, source[1:], event_name, data,
                                   viewport_id=viewport_id)
            else:
                token = set_current_viewport(child_vp)  # pyright: ignore[reportArgumentType]
                try:
                    await _route_event(child_view, source[1:], event_name, data,
                                       viewport_id=viewport_id)
                finally:
                    reset_current_viewport(token)
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

        # Filter 链
        for f in ext.event_filters:
            if await f.on_event_filter(view, event):
                return

        await view.on_event(event)


# ---------------------------------------------------------------------------
# 内部实现 — render / cache / push
# ---------------------------------------------------------------------------

def _render_and_cache(view: View) -> None:
    """render -> serialize -> 缓存 wire_tree + handlers + children。"""
    ext = render_ext(view)
    block = view.render()

    ext.handlers.clear()
    ext.children = {}
    ext.view_block = block

    wire_tree: list[WireNode] = [_process_node(view, ext, node) for node in block.items]

    # 注入 overlay children（如活跃菜单）
    if ext.overlay_children:
        for child_id, child_view in ext.overlay_children.items():
            ext.children[child_id] = child_view
            wire_tree.append({"$view": child_id})

    ext.wire_tree = wire_tree

    # 递归 render dirty 子 View
    for child_view in ext.children.values():
        child_ext = render_ext(child_view)
        if child_ext.dirty:
            _render_and_cache(child_view)
            child_ext.dirty = False


async def _deferred_render(view: View) -> None:
    """deferred render callback — render -> push -> signal。"""
    import logging
    _logger = logging.getLogger("mutgui.render")

    ext = render_ext(view)
    ext.render_scheduled = False

    if not ext.dirty:
        # 防御性：dirty 已被外部清除，仍需 signal 等待者
        if ext.render_event is not None:
            ext.render_event.set()
        return

    try:
        _render_and_cache(view)
    except Exception:
        _logger.exception("Render failed for %s", type(view).__name__)
        # 即使 render 失败也要 signal，否则 rendered() 永久挂起
        if ext.render_event is not None:
            ext.render_event.set()
        return

    ext.dirty = False

    # push to all ViewPorts
    try:
        obs = ViewObservers.get(view)
        if obs is not None:
            for vp in obs.viewports:
                await vp._push_render()  # type: ignore[attr-defined]
    except Exception:
        _logger.exception("Push render failed for %s", type(view).__name__)
    finally:
        # signal rendered — 即使 push 失败也保证 signal，防止 rendered() 永久挂起
        if ext.render_event is not None:
            ext.render_event.set()


# ---------------------------------------------------------------------------
# 内部实现 — 组件树序列化
# ---------------------------------------------------------------------------

_MISSING: RenderValue = {}

def _process_node(view: View, state: ViewRenderState, node: RenderNode) -> WireNode:
    if isinstance(node, Mapping):
        if "$component" not in node:
            raise ValueError(f"Invalid component node: missing $component key")
    return cast(WireNode, _process_value(view, state, node))


def _process_value(
    view: View,
    state: ViewRenderState,
    value: RenderValue,
    *,
    component_id: str | int = "",
    event_name: str = "",
) -> WireValue:
    if value is None or isinstance(value, (str, bytes, int, float, bool)):
        return value
    elif isinstance(value, View):
        state.children[value.id] = value
        return {"$view": value.id}
    elif isinstance(value, EventHandler):
        if component_id == "":
            raise ValueError(
                f"Component has handler '{event_name}' but missing $id. "
                f"Every component with an event handler must have a $id."
            )
        state.handlers[(component_id, event_name)] = value
        return value.to_wire()
    elif isinstance(value, Sequence):
        return [
            _process_value(view, state, item,
                component_id=component_id,
                event_name=f"{event_name}.{index}" if event_name else event_name,
            )
            for index, item in enumerate(value)
        ]
    else:
        assert isinstance(value, Mapping)
        component = value.get("$component", _MISSING)
        if component is not _MISSING:
            if not isinstance(component, str) or component == "":
                raise ValueError(
                    f"Invalid component type: {type(component).__name__}. "
                    f"$component must be a non-empty string.",
                )
            tmp_id = value.get("$id", _MISSING)
            if tmp_id is not _MISSING:
                if not isinstance(tmp_id, (str, int)):
                    raise ValueError("$id must be string or int.")
                component_id = tmp_id

        result: dict[str, WireValue] = {}
        for key, inner in value.items():
            if key == "$children":
                child_event = ""  # scope 边界，事件名重置
            elif event_name:
                child_event = f"{event_name}.{key}"
            else:
                child_event = key
            result[key] = _process_value(view, state, inner,
                component_id=component_id,
                event_name=child_event,
            )
        return result
