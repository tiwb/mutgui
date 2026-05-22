"""DockPanel — 响应式多面板布局组件。

支持二分分割（水平/垂直）、响应式坍缩、Tab 拖拽重排/移动、
Splitter 拖拽、merge_bars 融合 tab 栏。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .action import ActionContext, ActionRef
from .view import View, ViewBlock


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class PanelDef:
    title: str
    icon: str | None = None
    min_width: int = 0
    min_height: int = 0
    view: View | None = None


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
    layout: LayoutNode
    default_collapse_below: int = 0
    action_context: ActionContext | None = None

    def __init__(
        self,
        id: str,
        panels: dict[str, PanelDef],
        layout: LayoutNode,
        default_collapse_below: int = 0,
    ) -> None: ...

    def render(self) -> ViewBlock:
        """产出 DockPanel 完整 wire tree。"""
        ...


from . import _dock_panel_impl as _dock_panel_impl  # noqa: F401, E402
