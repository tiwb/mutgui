"""VirtualList / VirtualListItemAdapter Declaration 实现。

所有 VirtualListItemAdapter 和 VirtualList 方法的实际实现，
通过 @impl 注册到声明侧。
"""

from __future__ import annotations

from typing import Any

import mutobj
from mutobj import impl

from .virtual_list import VirtualList, VirtualListItemAdapter
from .view import ViewBlock
from .events import Callback
from .expr import Expr
from ._viewport_impl import filter_children_in_tree


# ---------------------------------------------------------------------------
# Extension — VirtualList 运行时私有状态
# ---------------------------------------------------------------------------

class VirtualListRuntime(mutobj.Extension[VirtualList]):
    """VirtualList 的运行时私有状态 — viewport 渲染内部簿记。"""
    item_views: dict[str, Any] = mutobj.field(default_factory=dict)
    viewport_ranges: dict[int, tuple[int, int]] = mutobj.field(default_factory=dict)
    viewport_item_ids: dict[int, set[str]] = mutobj.field(default_factory=dict)
    rendered_viewport_ranges: dict[int, tuple[int, int]] = mutobj.field(default_factory=dict)
    rendered_viewport_ids: dict[int, list[str]] = mutobj.field(default_factory=dict)
    visible_ids: list[str] = mutobj.field(default_factory=list)
    scroll_top: float = 0.0


def _vl_ext(self: VirtualList) -> VirtualListRuntime:
    return VirtualListRuntime.get_or_create(self)


# ---------------------------------------------------------------------------
# VirtualListItemAdapter 默认实现
# ---------------------------------------------------------------------------

@impl(VirtualListItemAdapter.item_count.getter)  # type: ignore[attr-defined]
def getter_item_count(self: VirtualListItemAdapter) -> int:
    return 0


@impl(VirtualListItemAdapter.item_id)
def virtual_list_item_adapter_item_id(self: VirtualListItemAdapter, index: int) -> str:
    return str(index)


@impl(VirtualListItemAdapter.create_item_view)
def virtual_list_item_adapter_create_item_view(self: VirtualListItemAdapter, index: int):
    raise NotImplementedError


@impl(VirtualListItemAdapter.invalidate)
def virtual_list_item_adapter_invalidate(self: VirtualListItemAdapter) -> None:
    for vl in self.virtual_lists:
        vl.invalidate()


# ---------------------------------------------------------------------------
# VirtualList 实现
# ---------------------------------------------------------------------------

@impl(VirtualList.__init__)
def virtual_list_init(
    self: VirtualList,
    id: str,
    adapter: VirtualListItemAdapter,
    *,
    sync_scroll: bool = False,
    stick_to_bottom: bool = False,
    estimated_item_height: int = 32,
) -> None:
    if sync_scroll and stick_to_bottom:
        raise ValueError(
            "VirtualList sync_scroll 和 stick_to_bottom 不能同时为 True",
        )
    self.id = id
    self.adapter = adapter
    self.sync_scroll = sync_scroll
    self.stick_to_bottom = stick_to_bottom
    self.estimated_item_height = estimated_item_height
    adapter.virtual_lists.append(self)
    ext = _vl_ext(self)
    ext.item_views = {}
    ext.viewport_ranges = {}
    ext.viewport_item_ids = {}
    ext.rendered_viewport_ranges = {}
    ext.rendered_viewport_ids = {}
    ext.visible_ids = []
    ext.scroll_top = 0.0


@impl(VirtualList.render)
def virtual_list_render(self: VirtualList) -> ViewBlock:
    """返回 VirtualList 容器 + 当前 viewport 并集内的 item View。"""
    ext = _vl_ext(self)
    _refresh_visible(self)
    visible_items = [ext.item_views[vid] for vid in ext.visible_ids]
    props: dict[str, Any] = {
        "$component": "mutgui.VirtualList",
        "$id": "list",
        "itemCount": self.adapter.item_count,
        "itemIds": ext.visible_ids,
        "viewportStart": 0,
        "stickToBottom": self.stick_to_bottom,
        "estimatedItemHeight": self.estimated_item_height,
        "onViewport": Callback(
            _virtual_list_on_viewport,
            self,
            start=Expr.wire("$0.start"),
            end=Expr.wire("$0.end"),
            viewport_id=Expr.host("event.viewport_id"),
        ),
        "$children": visible_items,
    }
    if self.sync_scroll:
        props["scrollTop"] = ext.scroll_top
        props["onScroll"] = Callback(
            _virtual_list_on_scroll,
            self,
            scrollTop=Expr.wire("$0.scrollTop"),
        )
    return ViewBlock([props])


def _virtual_list_on_viewport(
    self: VirtualList, *, start: int, end: int, viewport_id: int,
) -> None:
    """Callback 回调：前端 viewport 变化时更新 per-VP viewport range。"""
    _vl_ext(self).viewport_ranges[viewport_id] = (start, end)
    self.invalidate()


def _virtual_list_on_scroll(self: VirtualList, *, scrollTop: float) -> None:
    """Callback 回调：sync scroll 模式下前端报告滚动位置。"""
    _vl_ext(self).scroll_top = scrollTop
    self.invalidate()


@impl(VirtualList.render_viewport)
def virtual_list_render_viewport(
    self: VirtualList, wire_tree: list[dict[str, Any]], channel_id: int,
) -> list[dict[str, Any]]:
    """为指定 viewport 裁剪 $children，只保留该 VP 可见的 item。"""
    ext = _vl_ext(self)
    allowed = ext.viewport_item_ids.get(channel_id, set())
    filtered = filter_children_in_tree(wire_tree, allowed)
    if filtered:
        start, _ = ext.rendered_viewport_ranges.get(channel_id, (0, 0))
        filtered[0]["viewportStart"] = start
        filtered[0]["itemIds"] = ext.rendered_viewport_ids.get(channel_id, [])
    return filtered


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _refresh_visible(self: VirtualList) -> None:
    """根据所有 VP viewport 的并集重新查询 adapter，更新 visible items。"""
    from ._view_impl import ViewObservers
    from ._viewport_impl import ViewPortRuntime

    ext = _vl_ext(self)

    # 清理已断开 VP 的 viewport 条目
    obs = ViewObservers.get(self)
    if obs is not None:
        active_ids: set[int] = set()
        for vp in obs.viewports:
            rt = ViewPortRuntime.get(vp)
            if rt is not None and rt.channel is not None:
                active_ids.add(rt.channel.channel_id)
        ext.viewport_ranges = {
            k: v for k, v in ext.viewport_ranges.items()
            if k in active_ids
        }

    if not ext.viewport_ranges:
        ext.visible_ids = []
        ext.item_views.clear()
        ext.viewport_item_ids = {}
        ext.rendered_viewport_ranges = {}
        ext.rendered_viewport_ids = {}
        return

    # 计算并集
    union_start = min(s for s, _ in ext.viewport_ranges.values())
    union_end = max(e for _, e in ext.viewport_ranges.values())

    count = self.adapter.item_count
    union_start = min(union_start, count)
    union_end = min(union_end, count)

    # 查询并集范围的 id 列表
    new_ids = [self.adapter.item_id(i) for i in range(union_start, union_end)]
    # 创建新 item View（VirtualList 负责赋 id）
    for i, item_id in enumerate(new_ids):
        if item_id not in ext.item_views:
            view = self.adapter.create_item_view(union_start + i)
            view.id = item_id
            ext.item_views[item_id] = view
    # 清理不在并集范围内的旧 View
    visible_set = set(new_ids)
    for old_id in list(ext.item_views):
        if old_id not in visible_set:
            del ext.item_views[old_id]
    ext.visible_ids = new_ids

    # 预计算 per-VP 的 item ID 集合
    viewport_item_ids: dict[int, set[str]] = {}
    rendered_viewport_ranges: dict[int, tuple[int, int]] = {}
    rendered_viewport_ids: dict[int, list[str]] = {}
    for vp_id, (s, e) in ext.viewport_ranges.items():
        s, e = min(s, count), min(e, count)
        rendered_viewport_ranges[vp_id] = (s, e)
        rendered_viewport_ids[vp_id] = [
            self.adapter.item_id(i) for i in range(s, e)
        ]
        viewport_item_ids[vp_id] = {
            self.adapter.item_id(i) for i in range(s, e)
        }
    ext.viewport_item_ids = viewport_item_ids
    ext.rendered_viewport_ranges = rendered_viewport_ranges
    ext.rendered_viewport_ids = rendered_viewport_ids
