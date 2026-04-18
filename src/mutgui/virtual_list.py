"""VirtualList — 虚拟滚动列表组件。

View 不碰数据，只管 count + ID + item View 生命周期。
数据通过 Adapter 桥接。

每个 item 是独立的 View，支持独立更新和状态保持。
"""

from __future__ import annotations

from typing import Any

from .events import Callback
from .view import View


class VirtualListItemAdapter:
    """VirtualList 的 item 数据适配器。

    应用继承此类，提供业务数据到 View 的映射。
    """

    _virtual_list: VirtualList | None = None

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
        if self._virtual_list is not None:
            self._virtual_list.invalidate()


class VirtualList(View):
    """虚拟滚动列表。管理 item View 的生命周期。

    item View 作为 $children 出现在 render 输出中，
    框架标准子 View 机制（_process_items）自动管理
    ViewPort 创建/复用/销毁。
    """

    def __init__(self, id: str, adapter: VirtualListItemAdapter) -> None:
        self.id = id
        self.adapter = adapter
        adapter._virtual_list = self
        self._item_views: dict[str, View] = {}
        self._viewport: tuple[int, int] = (0, 0)
        self._visible_ids: list[str] = []

    def render(self) -> dict[str, Any]:
        """返回 VirtualList 容器 + 当前 viewport 内的 item View。"""
        self._refresh_visible()
        visible_items = [self._item_views[vid] for vid in self._visible_ids]
        return {
            "$component": "VirtualList",
            "$id": "list",
            "itemCount": self.adapter.item_count,
            "onViewport": Callback(
                self._on_viewport, start="$0.start", end="$0.end",
            ),
            "$children": visible_items,
        }

    def _on_viewport(self, *, start: int, end: int) -> None:
        """Callback 回调：前端 viewport 变化时更新 viewport range。"""
        self._viewport = (start, end)
        self.invalidate()

    def _refresh_visible(self) -> None:
        """根据当前 viewport range 重新查询 adapter，更新 visible items。"""
        start, end = self._viewport
        count = self.adapter.item_count
        # clamp viewport to current item count（删除后 viewport 可能越界）
        start = min(start, count)
        end = min(end, count)
        # 查询当前 viewport 的 id 列表
        new_ids = [self.adapter.item_id(i) for i in range(start, end)]
        # 创建新 item View（VirtualList 负责赋 id）
        for i, item_id in enumerate(new_ids):
            if item_id not in self._item_views:
                view = self.adapter.create_item_view(start + i)
                view.id = item_id
                self._item_views[item_id] = view
        # 清理不在 viewport 内的旧 View（v1 简单策略）
        visible_set = set(new_ids)
        for old_id in list(self._item_views):
            if old_id not in visible_set:
                del self._item_views[old_id]
        self._visible_ids = new_ids
