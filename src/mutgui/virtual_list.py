"""VirtualList — 虚拟滚动列表组件。

View 不碰数据，只管 count + ID + item View 生命周期。
数据通过 Adapter 桥接。

每个 item 是独立的 View，支持独立更新和状态保持。
支持多 ViewPort 独立滚动（per-VP viewport + union 渲染）。
"""

from __future__ import annotations

from typing import Any

from .events import Callback
from .view import View, ViewBlock
from ._viewport_impl import _filter_children_in_tree


class VirtualListItemAdapter:
    """VirtualList 的 item 数据适配器。

    应用继承此类，提供业务数据到 View 的映射。
    """

    _virtual_lists: list[VirtualList]

    def __init__(self) -> None:
        self._virtual_lists = []

    @property
    def item_count(self) -> int:
        """当前可用的 item 总数。"""
        return 0

    def item_id(self, index: int) -> str:
        """返回 index 位置的 stable ID。

        驱动 View 复用——同一 id 的 View 实例保持不变。
        """
        return str(index)

    def create_item_view(self, index: int) -> View:
        """创建新的 item View（不需要设 id，VirtualList 自动赋值）。

        仅在 VirtualList 找不到匹配 id 的已有 View 时调用。
        """
        raise NotImplementedError

    def invalidate(self) -> None:
        """通知 VirtualList 数据已变化（count 或 id 映射变了）。

        VirtualList 会重新查询 adapter，对比 id，复用/创建/销毁 View。
        """
        if self._virtual_lists is not None:
            for vl in self._virtual_lists:
                vl.invalidate()


class VirtualList(View):
    """虚拟滚动列表。管理 item View 的生命周期。

    item View 作为 $children 出现在 render 输出中，
    框架标准子 View 机制（_process_items）自动管理
    ViewPort 创建/复用/销毁。

    支持多 ViewPort 独立滚动：每个 VP 独立跟踪 viewport，
    render 取并集，push 时按 VP 裁剪 $children。
    """

    def __init__(
        self,
        id: str,
        adapter: VirtualListItemAdapter,
        *,
        sync_scroll: bool = False,
    ) -> None:
        self.id = id
        self.adapter = adapter
        adapter._virtual_lists.append(self)
        self._item_views: dict[str, View] = {}
        self._viewports: dict[int, tuple[int, int]] = {}  # channel_id → (start, end)
        self._viewport_item_ids: dict[int, set[str]] = {}  # channel_id → visible item IDs
        self._visible_ids: list[str] = []
        self.sync_scroll = sync_scroll
        self._scroll_top: float = 0

    def render(self) -> ViewBlock:
        """返回 VirtualList 容器 + 当前 viewport 并集内的 item View。"""
        self._refresh_visible()
        visible_items = [self._item_views[vid] for vid in self._visible_ids]
        props: dict[str, Any] = {
            "$component": "VirtualList",
            "$id": "list",
            "itemCount": self.adapter.item_count,
            "onViewport": Callback(
                self._on_viewport, start="$0.start", end="$0.end",
                viewport_id="@event.viewport_id",
            ),
            "$children": visible_items,
        }
        if self.sync_scroll:
            props["scrollTop"] = self._scroll_top
            props["onScroll"] = Callback(
                self._on_scroll, scrollTop="$0.scrollTop",
            )
        return ViewBlock([props])

    def render_viewport(
        self, wire_tree: list[dict[str, Any]], channel_id: int,
    ) -> list[dict[str, Any]]:
        allowed = self._viewport_item_ids.get(channel_id, set())
        return _filter_children_in_tree(wire_tree, allowed)

    def _on_viewport(self, *, start: int, end: int, viewport_id: int) -> None:
        """Callback 回调：前端 viewport 变化时更新 per-VP viewport range。"""
        self._viewports[viewport_id] = (start, end)
        self.invalidate()

    def _on_scroll(self, *, scrollTop: float) -> None:
        """Callback 回调：sync scroll 模式下前端报告滚动位置。"""
        self._scroll_top = scrollTop
        self.invalidate()

    def _refresh_visible(self) -> None:
        """根据所有 VP viewport 的并集重新查询 adapter，更新 visible items。"""
        from ._view_impl import ViewObservers
        from ._viewport_impl import ViewPortRuntime

        # 清理已断开 VP 的 viewport 条目
        obs = ViewObservers.get(self)
        if obs is not None:
            active_ids: set[int] = set()
            for vp in obs._viewports:
                rt = ViewPortRuntime.get(vp)
                if rt is not None and rt._channel is not None:
                    active_ids.add(rt._channel.channel_id)
            self._viewports = {k: v for k, v in self._viewports.items()
                               if k in active_ids}

        if not self._viewports:
            self._visible_ids = []
            self._item_views.clear()
            self._viewport_item_ids = {}
            return

        # 计算并集
        union_start = min(s for s, e in self._viewports.values())
        union_end = max(e for s, e in self._viewports.values())

        count = self.adapter.item_count
        union_start = min(union_start, count)
        union_end = min(union_end, count)

        # 查询并集范围的 id 列表
        new_ids = [self.adapter.item_id(i) for i in range(union_start, union_end)]
        # 创建新 item View（VirtualList 负责赋 id）
        for i, item_id in enumerate(new_ids):
            if item_id not in self._item_views:
                view = self.adapter.create_item_view(union_start + i)
                view.id = item_id
                self._item_views[item_id] = view
        # 清理不在并集范围内的旧 View
        visible_set = set(new_ids)
        for old_id in list(self._item_views):
            if old_id not in visible_set:
                del self._item_views[old_id]
        self._visible_ids = new_ids

        # 预计算 per-VP 的 item ID 集合
        viewport_item_ids: dict[int, set[str]] = {}
        for vp_id, (s, e) in self._viewports.items():
            s, e = min(s, count), min(e, count)
            viewport_item_ids[vp_id] = {
                self.adapter.item_id(i) for i in range(s, e)
            }
        self._viewport_item_ids = viewport_item_ids
