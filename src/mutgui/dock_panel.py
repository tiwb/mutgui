"""DockPanel — 响应式多面板布局组件。

支持二分分割（水平/垂直）、响应式坍缩、Tab 拖拽重排/移动、
Splitter 拖拽、merge_bars 融合 tab 栏。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .action import ActionRef
from .view import View, ViewBlock, WireTree


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class PanelDef:
    id: str
    title: str
    icon: str | None = None
    min_width: int = 0
    min_height: int = 0


@dataclass
class SplitNode:
    direction: Literal["horizontal", "vertical"]
    children: tuple[SplitNode | TabSetNode, SplitNode | TabSetNode]
    id: str | None = None
    ratio: float = 0.5
    merge_bars: bool = False
    collapse_below: int | None = None


@dataclass
class TabSetNode:
    panel_ids: list[str]
    id: str | None = None
    active_id: str | None = None
    bar_position: Literal["top", "bottom", "left", "right"] = "top"
    display_mode: Literal["icon-text", "icon", "icon-active-text"] = "icon-text"
    actions: list[ActionRef] | None = None


LayoutNode = SplitNode | TabSetNode


# ---------------------------------------------------------------------------
# DockPanel View
# ---------------------------------------------------------------------------

class DockPanel(View):
    panels: dict[str, PanelDef]
    panel_views: dict[str, View]
    layout: LayoutNode
    default_collapse_below: int

    def __init__(
        self,
        id: str,
        panels: list[PanelDef],
        layout: LayoutNode,
        default_collapse_below: int = 0,
    ) -> None: ...

    def set_panel_view(self, panel_id: str, view: View) -> None:
        """为 panel_id 设置内容 View。"""
        ...

    def render(self) -> ViewBlock:
        """产出 DockPanel 完整 wire tree。"""
        ...

    def render_viewport(
        self, wire_tree: WireTree, channel_id: int,
    ) -> WireTree:
        """为指定 viewport 计算响应式坍缩后的 layout。"""
        ...


from . import _dock_panel_impl as _dock_panel_impl  # noqa: F401, E402
