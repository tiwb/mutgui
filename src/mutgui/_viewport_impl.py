"""ViewPort Declaration 实现 — ViewPortRuntime Extension + @impl。

ViewPort 是纯管道：接收 View push 的 wire_tree 并发送到 Channel。
渲染逻辑在 _view_impl.py 中。
"""

from __future__ import annotations

from typing import Any, cast

import mutobj
from mutobj import impl

from ._viewport_context import set_current_viewport, reset_current_viewport
from ._view_impl import ViewObservers, ViewRenderState
from .channel import Channel
from .view import View
from .viewport import ViewPort


# ---------------------------------------------------------------------------
# Extension — ViewPort 的运行时私有状态
# ---------------------------------------------------------------------------

class ViewPortRuntime(mutobj.Extension[ViewPort]):
    """ViewPort 的运行时私有状态。"""

    view: View | None = None
    channel: Channel | None = None
    path: list[str | int] = mutobj.field(default_factory=list)
    child_viewports: dict[str | int, ViewPort] = mutobj.field(default_factory=dict)


def _ext(vp: ViewPort) -> ViewPortRuntime:
    return ViewPortRuntime.get_or_create(vp)


# ---------------------------------------------------------------------------
# @impl — ViewPort 生命周期
# ---------------------------------------------------------------------------

@impl(ViewPort.__init__)
def viewport_init(
    self: ViewPort, view: View, channel: Channel,
    *,
    _path: list[str | int] | None = None,
) -> None:
    ext = _ext(self)
    ext.view = view
    ext.channel = channel
    ext.path = _path if _path is not None else []
    ext.child_viewports = {}
    ViewObservers.get_or_create(view).viewports.append(self)


@impl(ViewPort.initialize)
async def viewport_initialize(self: ViewPort) -> None:
    ext = _ext(self)
    view = ext.view
    assert view is not None
    render_state = ViewRenderState.get(view)
    if render_state is not None and not render_state.dirty and render_state.wire_tree:
        # View 已 render 且 clean — 直接推送缓存
        await _vp_push_render(self)
    else:
        # 需要 render — invalidate 触发延迟调度
        view.invalidate()


@impl(ViewPort.handle_event)
async def viewport_handle_event(self: ViewPort, event: dict[str, Any]) -> None:
    ext = _ext(self)
    assert ext.view is not None
    assert ext.channel is not None
    event["_viewport_id"] = ext.channel.channel_id
    token = set_current_viewport(self)
    try:
        await ext.view.handle_event(event)
    finally:
        reset_current_viewport(token)


@impl(ViewPort.send_command)
async def viewport_send_command(self: ViewPort, name: str, /, **args: Any) -> None:
    ext = _ext(self)
    assert ext.channel is not None
    await ext.channel.send({
        "type": "command",
        "viewId": ext.path,
        "name": name,
        "args": args,
    })


@impl(ViewPort.detach)
def viewport_detach(self: ViewPort) -> None:
    ext = _ext(self)
    if ext.view is not None:
        obs = ViewObservers.get(ext.view)
        if obs is not None:
            try:
                obs.viewports.remove(self)
            except ValueError:
                pass
    # 递归 detach 子 ViewPort
    for child_vp in list(ext.child_viewports.values()):
        child_vp.detach()
    ext.child_viewports = {}


# ---------------------------------------------------------------------------
# Push render — 由 _view_impl._deferred_render 调用
# ---------------------------------------------------------------------------

def filter_children_in_tree(
    tree: list[dict[str, Any]], allowed: set[str],
) -> list[dict[str, Any]]:
    """浅拷贝 tree，只保留 $children 中 ID 在 allowed 集合内的 $view 节点。"""
    result: list[dict[str, Any]] = []
    for node in tree:
        if "$children" in node:
            raw_children: list[Any] = node["$children"]
            filtered: list[Any] = [
                c for c in raw_children
                if not isinstance(c, dict) or c.get("$view") in allowed  # pyright: ignore[reportUnknownMemberType]
            ]
            node = {**node, "$children": filtered}
        result.append(node)
    return result


def _extract_view_refs(tree: list[dict[str, Any]]) -> set[str]:
    """从 wire tree 中递归提取所有 $view 引用 ID。"""
    refs: set[str] = set()
    for node in tree:
        view_id = node.get("$view")
        if view_id is not None:
            refs.add(view_id)
        children = node.get("$children")
        if isinstance(children, list):
            child_list = cast(list[dict[str, Any]], children)
            refs.update(_extract_view_refs(child_list))
    return refs


async def _vp_push_render(vp: ViewPort) -> None:
    """推送 View 的缓存 wire_tree 到 ViewPort 的 Channel。"""
    ext = _ext(vp)
    view = ext.view
    assert view is not None
    assert ext.channel is not None

    render_state = ViewRenderState.get(view)
    if render_state is None:
        return

    wire_tree = render_state.wire_tree
    channel_id = ext.channel.channel_id

    wire_tree = view.render_viewport(wire_tree, channel_id)
    allowed = _extract_view_refs(wire_tree)

    await ext.channel.send({
        "type": "render",
        "viewId": ext.path,
        "tree": wire_tree,
    })

    # 子 ViewPort reconciliation（只包含 wire tree 中引用的 View）
    children = {k: v for k, v in render_state.children.items() if k in allowed}

    old_child_vps = ext.child_viewports
    ext.child_viewports = {}

    for child_id, child_view in children.items():
        # 复用已有子 ViewPort（同一 View 实例）或新建
        if child_id in old_child_vps and _ext(old_child_vps[child_id]).view is child_view:
            child_vp = old_child_vps.pop(child_id)
        else:
            child_path = ext.path + [child_id]
            child_vp = ViewPort(child_view, ext.channel, _path=child_path)
        ext.child_viewports[child_id] = child_vp

        # 递归推送子 View 的 wire_tree
        await _vp_push_render(child_vp)

    # detach 被移除的子 ViewPort
    for old_vp in old_child_vps.values():
        old_vp.detach()


def _vp_child_viewport(vp: ViewPort, child_id: str | int) -> ViewPort | None:
    return _ext(vp).child_viewports.get(child_id)


# 挂到 ViewPort 实例上供 _view_impl._deferred_render 调用
setattr(ViewPort, "_push_render", _vp_push_render)
setattr(ViewPort, "_child_viewport", _vp_child_viewport)
