"""View Declaration 实现 — ViewObservers + ViewRenderState Extension + @impl。

渲染职责归 View 所有：render -> serialize -> cache -> push 给 ViewPort。
ViewPort 只负责接收 wire_tree 并发送到 Channel。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Sequence, Mapping, TYPE_CHECKING, cast

import mutobj
from collections.abc import Callable
from mutobj import impl

from ._viewport_context import (
    get_current_viewport,
    reset_current_viewport,
    set_current_viewport,
)
from .events import Event, EventFilter, EventHandler
from .view import View, ViewBlock, PerViewport, RenderValue, WireValue, WireTree, WireNode, RenderNode

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

    handlers: dict[int, EventHandler] = mutobj.field(default_factory=dict)
    children: dict[str | int, View] = mutobj.field(default_factory=dict)
    event_filters: list[EventFilter] = mutobj.field(default_factory=list)
    # per-VP 缓存：key 为 channel_id。多 VP 下可能各自不同（PerViewport 介入）。
    wire_tree_per_vp: dict[int, WireTree] = mutobj.field(default_factory=dict)
    dirty: bool = True
    render_scheduled: bool = False
    render_event: asyncio.Event | None = None
    overlay_children: dict[str | int, View] = mutobj.field(default_factory=dict)  # 框架注入的子 View（如菜单）
    view_block: ViewBlock | None = None


class PerViewportState(mutobj.Extension[PerViewport]):
    """PerViewport 的运行时私有状态。"""

    fn: Callable[..., RenderValue] | None = None
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = mutobj.field(default_factory=dict)



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
    handler = ext.handlers.get(event.handler_id)
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


@impl(View.active_viewport_ids.getter)  # type: ignore[attr-defined]
def getter_active_viewport_ids(self: View) -> Sequence[int]:
    return _active_channel_ids(self)


def _active_channel_ids(view: View) -> list[int]:
    """获取观察 view 的所有活跃 channel_id 列表。

    懒导入 ViewPortRuntime 避免循环 import。顺序与 ViewObservers.viewports 一致。
    """
    from ._viewport_impl import ViewPortRuntime  # 延迟避免循环 import
    obs = ViewObservers.get(view)
    if obs is None:
        return []
    ids: list[int] = []
    for vp in obs.viewports:
        rt = ViewPortRuntime.get(vp)
        if rt is not None and rt.channel is not None:
            ids.append(rt.channel.channel_id)
    return ids


async def handle_raw_event(view: View, raw_msg: Mapping[str, WireValue]) -> None:
    """解析 wire 消息，路由到目标 View 的 on_event。

    这是框架内部管道函数，取代了原本公开的 View.handle_event 声明方法。
    用户不应调用此函数——事件处理通过 View.on_event(event) 进入领域层。
    """
    source = cast("Sequence[str | int]", raw_msg.get("source", []))
    event_name = raw_msg.get("event", "")
    if not isinstance(event_name, str):
        event_name = ""
    data = cast(dict[str, WireValue], raw_msg.get("data", {}))
    handler_id_raw = raw_msg.get("handlerId")
    handler_id = handler_id_raw if isinstance(handler_id_raw, int) else -1
    viewport_id_raw = raw_msg.get("_viewport_id")
    viewport_id = viewport_id_raw if isinstance(viewport_id_raw, int) else None
    await _route_event(view, source, event_name, data,
                       handler_id=handler_id, viewport_id=viewport_id)


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
# @impl — PerViewport 实现
# ---------------------------------------------------------------------------

@impl(PerViewport.__init__)
def per_viewport_init(
    self: PerViewport, fn: Callable[..., RenderValue], /, *args: Any, **kwargs: Any,
) -> None:
    """创建 PerViewport 实例。"""
    ext = PerViewportState.get_or_create(self)
    ext.fn = fn
    ext.args = args
    ext.kwargs = kwargs


@impl(PerViewport.get)
def per_viewport_get(self: PerViewport, viewport_id: int) -> RenderValue:
    """按 viewport_id 取值。"""
    ext = PerViewportState.get_or_create(self)
    assert ext.fn is not None, "PerViewport.get() called without fn"
    return ext.fn(viewport_id, *ext.args, **ext.kwargs)


# ---------------------------------------------------------------------------
# 内部实现 — 事件路由
# ---------------------------------------------------------------------------

async def _route_event(
    view: View,
    source: Sequence[str | int],
    event_name: str,
    data: Mapping[str, WireValue],
    *,
    handler_id: int = -1,
    viewport_id: int | None = None,
) -> None:
    """按 source 数组逐层路由事件，在叶子节点拆解 wire data → Event。"""
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
                                   handler_id=handler_id, viewport_id=viewport_id)
            else:
                token = set_current_viewport(child_vp)  # pyright: ignore[reportArgumentType]
                try:
                    await _route_event(child_view, source[1:], event_name, data,
                                       handler_id=handler_id, viewport_id=viewport_id)
                finally:
                    reset_current_viewport(token)
    elif len(source) == 1:
        component_id = str(source[0])
        args_raw = data.get("$args", ())
        args = list(args_raw) if isinstance(args_raw, list) else []
        kwargs = {k: v for k, v in data.items() if k != "$args"}
        event = Event(component_id, event_name, args, kwargs,
                      handler_id=handler_id, viewport_id=viewport_id)

        # Filter 链
        for f in ext.event_filters:
            if await f.on_event_filter(view, event):
                return

        await view.on_event(event)
    else:
        args_raw = data.get("$args", ())
        args = list(args_raw) if isinstance(args_raw, list) else []
        kwargs = {k: v for k, v in data.items() if k != "$args"}
        event = Event("", event_name, args, kwargs,
                      handler_id=handler_id, viewport_id=viewport_id)

        # Filter 链
        for f in ext.event_filters:
            if await f.on_event_filter(view, event):
                return

        await view.on_event(event)


# ---------------------------------------------------------------------------
# 内部实现 — render / cache / push
# ---------------------------------------------------------------------------

def _render_and_cache(view: View, *, channel_ids: Sequence[int] | None = None) -> None:
    """render -> serialize -> 缓存 per-VP wire_tree + handlers + children。

    对每个活跃 viewport 跑一次 to_wire，PerViewport 在任意位置按 vid 解析。
    children / handlers 取跨 VP 并集（先 clear 再聚合），保障事件路由不丢子。

    channel_ids 参数服务于“初次递归 cascade”：父在 _render_and_cache 阶段递归调子
    _render_and_cache 时，子的 ViewObservers 还未被创建（子 ViewPort 在后续
    _vp_push_render 中才 new），此时传入父的 active_ids 作为 hint——同步上下文下
    子的 channel id 集必与父一致（子 ViewPort 复用父的 channel）。
    """
    ext = render_ext(view)
    block = view.render()

    ext.handlers.clear()
    ext.children = {}
    ext.view_block = block

    if channel_ids is None:
        active_ids: Sequence[int] = _active_channel_ids(view)
    else:
        active_ids = channel_ids
    wire_per_vp: dict[int, WireTree] = {}

    if not active_ids:
        # 无活跃 VP 也跑一次解析（vid=0 占位）以注册 children/handlers，
        # 但不缓存。这让 view.render() 后不含 PerViewport 的测试也能拿到一致状态。
        for node in block.items:
            _process_node(view, ext, node, viewport_id=0)
    else:
        for cid in active_ids:
            wire_tree: WireTree = [
                _process_node(view, ext, node, viewport_id=cid)
                for node in block.items
            ]
            # 注入 overlay children（如活跃菜单）——保持旧行为：所有 VP 末尾 append，
            # 后续 _vp_push_render 按 origin_channel_id 过滤。
            if ext.overlay_children:
                for child_id, child_view in ext.overlay_children.items():
                    ext.children[child_id] = child_view
                    wire_tree.append({"$view": child_id})
            wire_per_vp[cid] = wire_tree

    ext.wire_tree_per_vp = wire_per_vp

    # 递归 render dirty 子 View（跨 VP 并集后的 children）。
    # 子 ViewPort 还未被 _vp_push_render 创建，所以 _active_channel_ids(child) 为空；
    # 这里把父的 active_ids 下发为 hint，让子预警生正确的 wire_tree_per_vp 缓存，
    # 其 channel 与父复用。
    for child_view in ext.children.values():
        child_ext = render_ext(child_view)
        if child_ext.dirty:
            _render_and_cache(child_view, channel_ids=active_ids)
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

def _process_node(
    view: View, state: ViewRenderState, node: RenderNode, *, viewport_id: int,
) -> WireNode:
    if isinstance(node, PerViewport):
        # PerViewport 在 RenderNode 位：get() 返回 RenderValue，但处于此位的
        # PerViewport 约定解析结果为 RenderNode（RenderComponent | View | PerViewport）。
        node = cast(RenderNode, node.get(viewport_id))
    if isinstance(node, Mapping):
        if "$component" not in node:
            raise ValueError(f"Invalid component node: missing $component key")
    return cast(WireNode, _process_value(view, state, node, viewport_id=viewport_id))


def _process_value(
    view: View,
    state: ViewRenderState,
    value: RenderValue,
    *,
    viewport_id: int,
) -> WireValue:
    if value is None or isinstance(value, (str, bytes, int, float, bool)):
        return value
    elif isinstance(value, View):
        state.children[value.id] = value
        return {"$view": value.id}
    elif isinstance(value, EventHandler):
        handler_id = len(state.handlers)
        state.handlers[handler_id] = value
        return value.to_wire(handler_id)
    elif isinstance(value, PerViewport):
        # PerViewport 出现在任意位置（dict 值位 / 嵌套 list 元素位）都递归处理。
        # 注意：list 元素位的语义约束（必须返回单个 node，不 splice）由上层递归自然满足。
        return _process_value(
            view, state, value.get(viewport_id),
            viewport_id=viewport_id,
        )
    elif isinstance(value, Sequence):
        return [
            _process_value(view, state, item,
                           viewport_id=viewport_id)
            for item in value
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

        return {
            k: _process_value(view, state, inner,
                              viewport_id=viewport_id)
            for k, inner in value.items()
        }


# ---------------------------------------------------------------------------
# 测试辅助 — 对外不作为公开 API，仅供 tests 与高阶场景使用。
# ---------------------------------------------------------------------------

def _resolve_for_viewport(  # pyright: ignore[reportUnusedFunction] — 供 tests 与调试场景使用
    view: View, items: Sequence[RenderNode], viewport_id: int,
) -> WireTree:
    """在指定 viewport_id 下将一棵 RenderTree 解析为 WireTree。

    服务于测试与调试场景。产生的 children/handlers 作为副作用写入 view 的
    ViewRenderState，与正常路径一致。调用前需手动 ``ext.handlers.clear()`` /
    ``ext.children = {}`` 避免上一轮残留。
    """
    ext = render_ext(view)
    return [_process_node(view, ext, node, viewport_id=viewport_id) for node in items]
