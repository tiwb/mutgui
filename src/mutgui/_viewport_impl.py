"""ViewPort Declaration 实现 — ViewPortRuntime Extension + @impl。

从原 session.py (ViewSession) 迁移全部逻辑：
render→serialize→send 循环、callback registry、子 View 管理、事件路由。
"""

from __future__ import annotations

import copy
from typing import Any, Callable

import mutobj
from mutobj import impl

from ._view_impl import ViewObservers
from .channel import Channel
from .events import TAG_KEY
from .view import View
from .viewport import ViewPort


# ---------------------------------------------------------------------------
# Extension — ViewPort 的运行时私有状态
# ---------------------------------------------------------------------------

class ViewPortRuntime(mutobj.Extension[ViewPort]):
    """ViewPort 的运行时私有状态。"""

    _view: View | None = None
    _channel: Channel | None = None
    _path: list = mutobj.field(default_factory=list)
    _callbacks: dict = mutobj.field(default_factory=dict)
    _children: dict = mutobj.field(default_factory=dict)
    _dirty: bool = True


def _ext(vp: ViewPort) -> ViewPortRuntime:
    return ViewPortRuntime.get_or_create(vp)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# @impl — ViewPort 生命周期
# ---------------------------------------------------------------------------

@impl(ViewPort.__init__)
def _viewport_init(
    self: ViewPort, view: View, channel: Channel,
    *,
    _path: list[str | int] | None = None,
) -> None:
    ext = _ext(self)
    ext._view = view
    ext._channel = channel
    ext._path = _path if _path is not None else []
    ext._callbacks = {}
    ext._children = {}
    ext._dirty = True
    ViewObservers.get_or_create(view)._viewports.append(self)


@impl(ViewPort.initialize)
async def _viewport_initialize(self: ViewPort) -> None:
    await _flush_tree(self)


@impl(ViewPort.handle_event)
async def _viewport_handle_event(self: ViewPort, event: dict[str, Any]) -> None:
    source = event.get("source", [])
    event_name = event.get("event", "")
    data = event.get("data", {})

    # 防御：字符串 source 转为数组
    if isinstance(source, str):
        source = [source] if source else []

    _route_event(self, source, event_name, data, event)
    await _flush_tree(self)


@impl(ViewPort.flush)
async def _viewport_flush(self: ViewPort) -> None:
    await _flush_tree(self)


@impl(ViewPort.detach)
def _viewport_detach(self: ViewPort) -> None:
    ext = _ext(self)
    if ext._view is not None:
        obs = ViewObservers.get(ext._view)
        if obs is not None:
            try:
                obs._viewports.remove(self)
            except ValueError:
                pass
    # 递归 detach 子 ViewPort
    for child in list(ext._children.values()):
        child.detach()
    ext._children = {}


# ---------------------------------------------------------------------------
# 内部实现 — 事件路由
# ---------------------------------------------------------------------------

def _route_event(
    vp: ViewPort,
    source: list[str | int],
    event_name: str,
    data: dict[str, Any],
    original_event: dict[str, Any],
) -> None:
    """按 source 数组逐层路由事件。"""
    ext = _ext(vp)
    if len(source) > 1:
        child_id = source[0]
        child = ext._children.get(child_id)
        if child is not None:
            _route_event(child, source[1:], event_name, data, original_event)
    elif len(source) == 1:
        component_id = source[0]
        key = (component_id, event_name)
        cb = ext._callbacks.get(key)
        if cb is not None:
            cb(data)
        else:
            ext._view.on_event(original_event)  # type: ignore[union-attr]
        # 通知所有观察者（包括当前 ViewPort 和其他共享同一 View 的 ViewPort）
        ext._view.invalidate()  # type: ignore[union-attr]
    else:
        ext._view.on_event(original_event)  # type: ignore[union-attr]
        ext._view.invalidate()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# 内部实现 — render / flush / dirty
# ---------------------------------------------------------------------------

def _mark_dirty(vp: ViewPort) -> None:
    _ext(vp)._dirty = True


def _schedule_flush(vp: ViewPort) -> None:
    """标记 dirty。异步 flush 在未来版本实现，当前由外部触发。"""
    _mark_dirty(vp)


# 挂到 ViewPort 实例上供 _view_impl 调用
ViewPort._schedule_flush = _schedule_flush  # type: ignore[attr-defined]


async def _flush_tree(vp: ViewPort) -> None:
    """Flush self（if dirty）then children。父先子后。"""
    ext = _ext(vp)
    if ext._dirty:
        await _render_and_send(vp)
        ext._dirty = False
    for child in list(ext._children.values()):
        await _flush_tree(child)


async def _render_and_send(vp: ViewPort) -> None:
    """render → process → send。"""
    ext = _ext(vp)
    view = ext._view
    assert view is not None

    raw_tree = view.render()
    # 归一化：dict → list
    if isinstance(raw_tree, dict):
        items: list[Any] = [raw_tree]
    else:
        items = list(raw_tree)

    ext._callbacks.clear()
    old_children = ext._children
    ext._children = {}

    wire_tree = _process_items(vp, items, old_children)

    # 清理被移除的子 View 的 ViewPort
    for child_vp in old_children.values():
        child_vp.detach()

    assert ext._channel is not None
    await ext._channel.send({
        "type": "render",
        "viewId": ext._path,
        "tree": wire_tree,
    })


# ---------------------------------------------------------------------------
# 内部实现 — 组件树序列化
# ---------------------------------------------------------------------------

def _process_items(
    vp: ViewPort,
    items: list[Any],
    old_children: dict[str | int, ViewPort],
) -> list[dict[str, Any]]:
    """处理列表：组件 dict 或 View 实例。"""
    ext = _ext(vp)
    result: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, View):
            vid = item.id
            # 复用已有子 ViewPort（同一 View 实例）或新建
            if vid in old_children and _ext(old_children[vid])._view is item:
                child = old_children.pop(vid)
            else:
                child_path = ext._path + [vid]
                child = ViewPort(item, ext._channel, _path=child_path)  # type: ignore[arg-type]
            ext._children[vid] = child
            result.append({"$view": vid})
        else:
            result.append(_process_node(vp, item, old_children))
    return result


def _process_node(
    vp: ViewPort,
    node: dict[str, Any],
    old_children: dict[str | int, ViewPort],
) -> dict[str, Any]:
    """处理单个组件节点：提取 callable，处理 $children。"""
    result: dict[str, Any] = {}
    node_id: str | int = node.get("$id", "")

    for key, val in node.items():
        if key == "$children" and isinstance(val, list):
            result[key] = _process_items(vp, val, old_children)
        elif isinstance(val, dict) and TAG_KEY in val:
            result[key] = _process_tagged(vp, val, node_id, key)
        else:
            result[key] = val

    return result


def _process_tagged(
    vp: ViewPort,
    tagged: dict[str, Any],
    node_id: str | int,
    prop_name: str,
) -> dict[str, Any]:
    """处理 $ 标签值：提取 callable，生成 wire 格式。"""
    ext = _ext(vp)
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
