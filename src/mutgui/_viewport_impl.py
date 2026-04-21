"""ViewPort Declaration 实现 — ViewPortRuntime Extension + @impl。

ViewPort 是纯管道：接收 View push 的 wire_tree 并发送到 Channel。
渲染逻辑在 _view_impl.py 中。
"""

from __future__ import annotations

from typing import Any

import mutobj
from mutobj import impl

from ._view_impl import ViewObservers, ViewRenderState, _render_ext
from .channel import Channel
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
    _child_viewports: dict = mutobj.field(default_factory=dict)


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
    ext._child_viewports = {}
    ViewObservers.get_or_create(view)._viewports.append(self)


@impl(ViewPort.initialize)
async def _viewport_initialize(self: ViewPort) -> None:
    ext = _ext(self)
    view = ext._view
    assert view is not None
    render_state = ViewRenderState.get(view)
    if render_state is not None and not render_state._dirty and render_state._wire_tree:
        # View 已 render 且 clean — 直接推送缓存
        await _vp_push_render(self)
    else:
        # 需要 render — invalidate 触发延迟调度
        view.invalidate()


@impl(ViewPort.handle_event)
async def _viewport_handle_event(self: ViewPort, event: dict[str, Any]) -> None:
    ext = _ext(self)
    assert ext._view is not None
    event["_viewport_id"] = ext._channel.channel_id  # type: ignore[union-attr]
    await ext._view.handle_event(event)


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
    for child_vp in list(ext._child_viewports.values()):
        child_vp.detach()
    ext._child_viewports = {}


# ---------------------------------------------------------------------------
# Push render — 由 _view_impl._deferred_render 调用
# ---------------------------------------------------------------------------

def _filter_children_in_tree(
    tree: list[dict[str, Any]], allowed: set[str],
) -> list[dict[str, Any]]:
    """浅拷贝 tree，只保留 $children 中 ID 在 allowed 集合内的 $view 节点。"""
    result: list[dict[str, Any]] = []
    for node in tree:
        if "$children" in node:
            filtered = [
                c for c in node["$children"]
                if not isinstance(c, dict) or c.get("$view") in allowed
            ]
            node = {**node, "$children": filtered}
        result.append(node)
    return result


def _extract_view_refs(tree: list[dict[str, Any]]) -> set[str]:
    """从 wire tree 中递归提取所有 $view 引用 ID。"""
    refs: set[str] = set()
    for node in tree:
        if not isinstance(node, dict):
            continue
        view_id = node.get("$view")
        if view_id is not None:
            refs.add(view_id)
        children = node.get("$children")
        if isinstance(children, list):
            refs.update(_extract_view_refs(children))
    return refs


async def _vp_push_render(vp: ViewPort) -> None:
    """推送 View 的缓存 wire_tree 到 ViewPort 的 Channel。"""
    ext = _ext(vp)
    view = ext._view
    assert view is not None
    assert ext._channel is not None

    render_state = ViewRenderState.get(view)
    if render_state is None:
        return

    wire_tree = render_state._wire_tree
    channel_id = ext._channel.channel_id

    wire_tree = view.render_viewport(wire_tree, channel_id)
    allowed = _extract_view_refs(wire_tree)

    await ext._channel.send({
        "type": "render",
        "viewId": ext._path,
        "tree": wire_tree,
    })

    # 子 ViewPort reconciliation（只包含 wire tree 中引用的 View）
    children = {k: v for k, v in render_state._children.items() if k in allowed}

    old_child_vps = ext._child_viewports
    ext._child_viewports = {}

    for child_id, child_view in children.items():
        # 复用已有子 ViewPort（同一 View 实例）或新建
        if child_id in old_child_vps and _ext(old_child_vps[child_id])._view is child_view:
            child_vp = old_child_vps.pop(child_id)
        else:
            child_path = ext._path + [child_id]
            child_vp = ViewPort(child_view, ext._channel, _path=child_path)  # type: ignore[arg-type]
        ext._child_viewports[child_id] = child_vp

        # 递归推送子 View 的 wire_tree
        await _vp_push_render(child_vp)

    # detach 被移除的子 ViewPort
    for old_vp in old_child_vps.values():
        old_vp.detach()


# 挂到 ViewPort 实例上供 _view_impl._deferred_render 调用
ViewPort._push_render = _vp_push_render  # type: ignore[attr-defined]
