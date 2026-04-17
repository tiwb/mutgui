"""View Declaration 实现 — ViewObservers + ViewRenderState Extension + @impl。

渲染职责归 View 所有：render → serialize → cache → push 给 ViewPort。
ViewPort 只负责接收 wire_tree 并发送到 Channel。
"""

from __future__ import annotations

import asyncio
import copy
import inspect
from typing import Any, Callable, TYPE_CHECKING

import mutobj
from mutobj import impl

from .events import TAG_KEY
from .view import View

if TYPE_CHECKING:
    from .viewport import ViewPort


# ---------------------------------------------------------------------------
# Extensions
# ---------------------------------------------------------------------------

class ViewObservers(mutobj.Extension[View]):
    """追踪一个 View 实例的所有 ViewPort 观察者。"""

    _viewports: list = mutobj.field(default_factory=list)  # list[ViewPort]


class ViewRenderState(mutobj.Extension[View]):
    """View 的渲染状态 — callbacks、children、wire_tree 缓存、dirty 标记。"""

    _callbacks: dict = mutobj.field(default_factory=dict)
    _children: dict = mutobj.field(default_factory=dict)  # dict[str|int, View]
    _wire_tree: list = mutobj.field(default_factory=list)
    _dirty: bool = True
    _render_scheduled: bool = False
    _render_event: asyncio.Event | None = None


def _render_ext(view: View) -> ViewRenderState:
    return ViewRenderState.get_or_create(view)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# @impl — View 默认实现
# ---------------------------------------------------------------------------

@impl(View.render)
def _default_render(self: View) -> list[Any]:
    return []


@impl(View.on_event)
def _default_on_event(self: View, event: dict[str, Any]) -> None:
    pass


@impl(View.invalidate)
def _view_invalidate(self: View) -> None:
    ext = _render_ext(self)
    ext._dirty = True
    if ext._render_scheduled:
        return
    ext._render_scheduled = True
    try:
        loop = asyncio.get_running_loop()
        loop.call_soon(lambda: asyncio.ensure_future(_deferred_render(self)))
    except RuntimeError:
        pass  # 无事件循环时只标脏


@impl(View.handle_event)
async def _view_handle_event(self: View, event: dict[str, Any]) -> None:
    source = event.get("source", [])
    event_name = event.get("event", "")
    data = event.get("data", {})
    if isinstance(source, str):
        source = [source] if source else []
    await _route_event(self, source, event_name, data, event)


@impl(View.rendered)
async def _view_rendered(self: View) -> None:
    ext = _render_ext(self)
    if not ext._dirty and not ext._render_scheduled:
        return
    if ext._render_event is None:
        ext._render_event = asyncio.Event()
    ext._render_event.clear()
    await ext._render_event.wait()


# ---------------------------------------------------------------------------
# 内部实现 — 事件路由
# ---------------------------------------------------------------------------

async def _route_event(
    view: View,
    source: list[str | int],
    event_name: str,
    data: dict[str, Any],
    original_event: dict[str, Any],
) -> None:
    """按 source 数组逐层路由事件。"""
    ext = _render_ext(view)
    if len(source) > 1:
        child_id = source[0]
        child_view = ext._children.get(child_id)
        if child_view is not None:
            await _route_event(
                child_view, source[1:], event_name, data, original_event,
            )
    elif len(source) == 1:
        component_id = source[0]
        key = (component_id, event_name)
        cb = ext._callbacks.get(key)
        if cb is not None:
            result = cb(data)
            if inspect.isawaitable(result):
                await result
        else:
            view.on_event(original_event)
        view.invalidate()
    else:
        view.on_event(original_event)
        view.invalidate()


# ---------------------------------------------------------------------------
# 内部实现 — render / cache / push
# ---------------------------------------------------------------------------

def _render_and_cache(view: View) -> None:
    """render → serialize → 缓存 wire_tree + callbacks + children。"""
    ext = _render_ext(view)
    raw_tree = view.render()
    if isinstance(raw_tree, dict):
        items: list[Any] = [raw_tree]
    else:
        items = list(raw_tree)

    ext._callbacks.clear()
    ext._children = {}
    ext._wire_tree = _process_items(view, items)

    # 递归 render dirty 子 View
    for child_view in ext._children.values():
        child_ext = _render_ext(child_view)
        if child_ext._dirty:
            _render_and_cache(child_view)
            child_ext._dirty = False


async def _deferred_render(view: View) -> None:
    """deferred render callback — render → push → signal。"""
    ext = _render_ext(view)
    ext._render_scheduled = False

    if not ext._dirty:
        # 防御性：dirty 已被外部清除，仍需 signal 等待者
        if ext._render_event is not None:
            ext._render_event.set()
        return

    _render_and_cache(view)
    ext._dirty = False

    # push to all ViewPorts
    obs = ViewObservers.get(view)
    if obs is not None:
        for vp in obs._viewports:
            await vp._push_render()  # type: ignore[attr-defined]

    # signal rendered
    if ext._render_event is not None:
        ext._render_event.set()


# ---------------------------------------------------------------------------
# 内部实现 — 组件树序列化
# ---------------------------------------------------------------------------

def _process_items(view: View, items: list[Any]) -> list[dict[str, Any]]:
    """处理列表：组件 dict 或 View 实例。"""
    ext = _render_ext(view)
    result: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, View):
            ext._children[item.id] = item
            result.append({"$view": item.id})
        else:
            result.append(_process_node(view, item))
    return result


def _process_node(view: View, node: dict[str, Any]) -> dict[str, Any]:
    """处理单个组件节点：提取 callable，处理 $children。"""
    result: dict[str, Any] = {}
    node_id: str | int = node.get("$id", "")
    for key, val in node.items():
        if key == "$children" and isinstance(val, list):
            result[key] = _process_items(view, val)
        elif isinstance(val, dict) and TAG_KEY in val:
            result[key] = _process_tagged(view, val, node_id, key)
        else:
            result[key] = val
    return result


def _process_tagged(
    view: View,
    tagged: dict[str, Any],
    node_id: str | int,
    prop_name: str,
) -> dict[str, Any]:
    """处理 $ 标签值：提取 callable，生成 wire 格式。"""
    ext = _render_ext(view)
    tag_type = tagged[TAG_KEY]

    if tag_type == "handler":
        fn = tagged.get("fn")
        extract = tagged.get("extract", {})
        if fn is not None:
            ext._callbacks[(node_id, prop_name)] = fn
        return {TAG_KEY: "handler", "extract": extract}

    elif tag_type == "bind":
        obj = tagged["obj"]
        attr = tagged["attr"]
        path = tagged.get("path", "$0")
        ext._callbacks[(node_id, prop_name)] = _make_bind_callback(obj, attr)
        return {TAG_KEY: "handler", "extract": {"__bind_value__": path}}

    else:
        return copy.deepcopy(tagged)


def _make_bind_callback(obj: Any, attr: str) -> Callable[..., Any]:
    """创建 bind 的写回 callback。"""
    def callback(data: dict[str, Any]) -> None:
        value = data.get("__bind_value__")
        setattr(obj, attr, value)
    return callback
