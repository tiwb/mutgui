"""mutgui — 后端驱动 UI 框架。"""

__version__ = "0.1.999"

from .events import Event, EventHandler, Callback, Bind, EventFilter
from .view import View, ViewBlock
from .channel import Channel
from .viewport import ViewPort
from .virtual_list import VirtualList, VirtualListItemAdapter
from .dock_panel import (
    DockPanel, PanelDef, SplitNode, TabSetNode, ActionDef,
)
from .menu import MenuView, MenuTrigger
from .modules import ModuleRegistry

__all__ = [
    "View",
    "ViewBlock",
    "Channel",
    "ViewPort",
    "VirtualList",
    "VirtualListItemAdapter",
    "Event",
    "EventHandler",
    "Callback",
    "Bind",
    "EventFilter",
    "DockPanel",
    "PanelDef",
    "SplitNode",
    "TabSetNode",
    "ActionDef",
    "MenuView",
    "MenuTrigger",
    "ModuleRegistry",
]
