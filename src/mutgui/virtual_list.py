"""VirtualList — 虚拟滚动列表组件。

View 不碰数据，只管 count + ID + item View 生命周期。
数据通过 Adapter 桥接。

每个 item 是独立的 View，支持独立更新和状态保持。
支持多 ViewPort 独立滚动（per-VP viewport + union 渲染）。
"""

from __future__ import annotations

import mutobj

from .view import View, ViewBlock


class VirtualListItemAdapter(mutobj.Declaration):
    """VirtualList 的 item 数据适配器。

    应用继承此类，提供业务数据到 View 的映射。
    """

    virtual_lists: list[VirtualList] = mutobj.field(default_factory=list)

    @property
    def item_count(self) -> int:
        """当前可用的 item 总数。"""
        ...

    def item_id(self, index: int) -> str:
        """返回 index 位置的 stable ID。

        驱动 View 复用——同一 id 的 View 实例保持不变。
        """
        ...

    def create_item_view(self, index: int) -> View:
        """创建新的 item View（不需要设 id，VirtualList 自动赋值）。

        仅在 VirtualList 找不到匹配 id 的已有 View 时调用。
        """
        ...

    def invalidate(self) -> None:
        """通知 VirtualList 数据已变化（count 或 id 映射变了）。

        VirtualList 会重新查询 adapter，对比 id，复用/创建/销毁 View。
        """
        ...


class VirtualList(View):
    """虚拟滚动列表。管理 item View 的生命周期。

    item View 作为 $children 出现在 render 输出中，
    框架标准子 View 机制（_process_items）自动管理
    ViewPort 创建/复用/销毁。

    支持多 ViewPort 独立滚动：每个 VP 独立跟踪 viewport，
    render 取并集，push 时按 VP 裁剪 $children。
    """
    adapter: VirtualListItemAdapter
    sync_scroll: bool
    stick_to_bottom: bool
    estimated_item_height: int

    def __init__(
        self,
        id: str,
        adapter: VirtualListItemAdapter,
        *,
        sync_scroll: bool = False,
        stick_to_bottom: bool = False,
        estimated_item_height: int = 32,
    ) -> None: ...

    def render(self) -> ViewBlock:
        """返回 VirtualList 容器 + 当前 viewport 并集内的 item View（按 PerViewport 拆分表达）。"""
        ...


from . import _virtual_list_impl as _virtual_list_impl  # noqa: F401, E402
