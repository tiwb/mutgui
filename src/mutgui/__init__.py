"""mutgui — 后端驱动 UI 框架。"""

__version__ = "0.9.999"

from .events import Event, EventHandler, Callback, Bind, EventFilter
from .expr import Expr
from .view import View, ViewBlock
from .channel import Channel
from .viewport import ViewPort
from .virtual_list import VirtualList, VirtualListItemAdapter
from .dock_panel import (
    DockPanel, PanelDef, SplitNode, TabSetNode,
)
from .menu import MenuView, MenuTrigger
from .action import (
    Action,
    ActionRef,
    ActionContext,
    ActionCategoryProvider,
    ActionMenu,
    ActionToolbar,
)
from .modules import ModuleRegistry

__all__ = [
    "View",
    "ViewBlock",
    "Channel",
    "ViewPort",
    "VirtualList",
    "VirtualListItemAdapter",
    "Event",
    "Expr",
    "EventHandler",
    "Callback",
    "Bind",
    "EventFilter",
    "DockPanel",
    "PanelDef",
    "SplitNode",
    "TabSetNode",
    "Action",
    "ActionRef",
    "ActionContext",
    "ActionCategoryProvider",
    "ActionMenu",
    "ActionToolbar",
    "MenuView",
    "MenuTrigger",
    "ModuleRegistry",
]
