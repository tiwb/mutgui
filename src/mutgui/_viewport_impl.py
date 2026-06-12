"""ViewPort Declaration 实现 — ViewPortRuntime Extension + @impl。

ViewPort 是纯管道：接收 View push 的 wire_tree 并发送到 Channel。
渲染逻辑在 _view_impl.py 中。
"""

from __future__ import annotations

from typing import Any, cast

import mutobj
from mutobj import impl

from ._viewport_context import set_current_viewport, reset_current_viewport
from ._view_impl import ViewObservers, ViewRenderState, handle_raw_event, _render_and_cache  # pyright: ignore[reportPrivateUsage]
from .channel import Channel
from .view import View, ViewId, WireTree
from .viewport import ViewPort


# ---------------------------------------------------------------------------
# Extension — ViewPort 的运行时私有状态
# ---------------------------------------------------------------------------

class ViewPortRuntime(mutobj.Extension[ViewPort]):
    """ViewPort 的运行时私有状态。"""

    view: View | None = None
    channel: Channel | None = None
    path: list[str | int] = mutobj.field(default_factory=list)
    child_viewports: dict[ViewId, ViewPort] = mutobj.field(default_factory=dict)
    # 根 ViewPort 持有的浏览器侧握手信息（子 ViewPort 为空）。
    client: dict[str, Any] | None = None


def _ext(vp: ViewPort) -> ViewPortRuntime:
    return ViewPortRuntime.get_or_create(vp)


# ---------------------------------------------------------------------------
# @impl — ViewPort 生命周期
# ---------------------------------------------------------------------------

@impl(ViewPort.__init__)
def view_port_init(
    self: ViewPort, view: View, channel: Channel,
    *,
    _path: list[str | int] | None = None,
    _client: dict[str, Any] | None = None,
) -> None:
    ext = _ext(self)
    ext.view = view
    ext.channel = channel
    ext.path = _path if _path is not None else []
    ext.child_viewports = {}
    ext.client = _client
    ViewObservers.get_or_create(view).viewports.append(self)


@impl(ViewPort.initialize)
async def view_port_initialize(self: ViewPort) -> None:
    ext = _ext(self)
    view = ext.view
    assert view is not None

    # 初始握手：在首次 render 之前合成一条 $hashchange (cause=initial)
    # 事件，走与 wire 事件相同的 _route_event 路径，让根 View 在首屏
    # render 前已拿到路由状态。只根 ViewPort（client 存在时）发送，避免
    # 子 ViewPort 重复触发。
    if ext.client is not None:
        initial_hash = ext.client.get("hash", "")
        if not isinstance(initial_hash, str):
            initial_hash = ""
        token = set_current_viewport(self)
        try:
            await handle_raw_event(view, {
                "source": [],
                "event": "$hashchange",
                "data": {
                    "hash": initial_hash,
                    "previousHash": None,
                    "cause": "initial",
                },
            })
        finally:
            reset_current_viewport(token)

    render_state = ViewRenderState.get(view)
    if (
        render_state is not None
        and not render_state.dirty
        and ext.channel is not None
        and ext.channel.channel_id in render_state.wire_tree_per_vp
    ):
        # View 已 render 且当前 VP 有缓存 — 直接推送
        await vp_push_render(self)
    else:
        # 需要 render（首次 attach 这个 VP 时其 channel_id 不在缓存里）。
        # 同步跑 _render_and_cache 后推送，避免调用者必须额外 await rendered()。
        try:
            _render_and_cache(view)
        except Exception:
            import logging
            logging.getLogger("mutgui.render").exception(
                "Render failed for %s during ViewPort.initialize",
                type(view).__name__,
            )
            return
        render_state = ViewRenderState.get(view)
        if render_state is not None:
            render_state.dirty = False
            if render_state.render_event is not None:
                render_state.render_event.set()
        await vp_push_render(self)


@impl(ViewPort.handle_event)
async def view_port_handle_event(self: ViewPort, event: dict[str, Any]) -> None:
    ext = _ext(self)
    assert ext.view is not None
    assert ext.channel is not None
    event["_viewport_id"] = ext.channel.channel_id
    token = set_current_viewport(self)
    try:
        await handle_raw_event(ext.view, event)
    finally:
        reset_current_viewport(token)


@impl(ViewPort.send_command)
async def view_port_send_command(self: ViewPort, name: str, /, **args: Any) -> None:
    ext = _ext(self)
    assert ext.channel is not None
    await ext.channel.send({
        "type": "command",
        "viewId": ext.path,
        "name": name,
        "args": args,
    })


@impl(ViewPort.detach)
def view_port_detach(self: ViewPort) -> None:
    ext = _ext(self)
    channel_id = ext.channel.channel_id if ext.channel is not None else None
    if ext.view is not None:
        # 关闭本 viewport 触发的浮层（duck typing：origin_channel_id）。
        # 同步 inline 清理 overlay_children：避免在连接异常关闭路径上
        # 依赖 running event loop；cleanup 本身不需 await IO。
        _cleanup_overlays_for_channel(ext.view, channel_id)
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


def _cleanup_overlays_for_channel(view: View, channel_id: int | None) -> None:
    """关闭挂在 view 上、origin_channel_id == channel_id 的浮层子 View。

    duck typing 判定。detach 是 sync 路径上不假设 running loop，直接同步清理。
    """
    if channel_id is None:
        return
    render_state = ViewRenderState.get(view)
    if render_state is None:
        return
    removed = False
    for child_id, child in list(render_state.overlay_children.items()):
        if getattr(child, "origin_channel_id", None) == channel_id:
            render_state.overlay_children.pop(child_id, None)
            removed = True
    if removed:
        view.invalidate()


# ---------------------------------------------------------------------------
# Push render — 由 _view_impl._deferred_render 调用
# ---------------------------------------------------------------------------

def _extract_view_refs(tree: WireTree) -> set[ViewId]:
    """从 wire tree 中递归提取所有 $view 引用 ID。"""
    refs: set[ViewId] = set()
    for node in tree:
        view_id = node.get("$view")
        if isinstance(view_id, ViewId):
            refs.add(view_id)
        children = node.get("$children")
        if isinstance(children, (list, tuple)):
            refs.update(_extract_view_refs(cast(WireTree, children)))
    return refs


def _filter_overlays_by_channel(
    wire_tree: WireTree,
    children: dict[ViewId, View],
    channel_id: int,
) -> WireTree:
    """过滤 wire_tree 顶层 `$view` 节点：若指向 View 的 `origin_channel_id`
    不为 None 且不等于当前 channel_id，则剔除。

    overlay 子 View（如 MenuView）由 `_render_and_cache` 注入为顶层 `{"$view": id}`
    节点，顶层过滤即可覆盖全部场景。
    """
    result: WireTree = []
    for node in wire_tree:
        view_id = node.get("$view")
        if isinstance(view_id, (str, int)) and view_id in children:
            child_view = children[view_id]
            origin = getattr(child_view, "origin_channel_id", None)
            if origin is not None and origin != channel_id:
                continue
        result.append(node)
    return result


async def vp_push_render(vp: ViewPort) -> None:
    """推送 View 的缓存 wire_tree 到 ViewPort 的 Channel。"""
    ext = _ext(vp)
    view = ext.view
    assert view is not None
    assert ext.channel is not None

    render_state = ViewRenderState.get(view)
    if render_state is None:
        return

    channel_id = ext.channel.channel_id
    wire_tree = render_state.wire_tree_per_vp.get(channel_id)
    if wire_tree is None:
        # 本 VP 未参与上次 _render_and_cache（如仅在递归中临时创建的子 ViewPort）。
        # 同步补一次，不走 invalidate 避免需调用者 await rendered()。
        try:
            _render_and_cache(view)
        except Exception:
            import logging
            logging.getLogger("mutgui.render").exception(
                "Render failed during vp_push_render fallback for %s",
                type(view).__name__,
            )
            return
        render_state.dirty = False
        if render_state.render_event is not None:
            render_state.render_event.set()
        wire_tree = render_state.wire_tree_per_vp.get(channel_id)
        if wire_tree is None:
            return

    # 按 origin 过滤 overlay $view 节点（per-viewport 作用域）。
    # duck typing：避免 _viewport_impl 反向 import menu 模块。
    wire_tree = _filter_overlays_by_channel(wire_tree, render_state.children, channel_id)
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
        await vp_push_render(child_vp)

    # detach 被移除的子 ViewPort
    for old_vp in old_child_vps.values():
        old_vp.detach()


def vp_child_viewport(vp: ViewPort, child_id: ViewId) -> ViewPort | None:
    return _ext(vp).child_viewports.get(child_id)



