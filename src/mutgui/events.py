"""事件系统 — Event + EventHandler。

Event 纯数据，描述"发生了什么"。
EventHandler 策略对象，定义"怎么处理"。
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .view import View


class Event:
    """运行时事件 — 纯数据，不含处理逻辑。"""

    __slots__ = ("component_id", "name", "data")

    def __init__(self, component_id: str, name: str, data: dict[str, Any]) -> None:
        self.component_id = component_id
        self.name = name
        self.data = data


class EventHandler:
    """事件处理策略 — 声明在 render 中，定义提取和处理方式。

    直接使用时：只提取数据，不消费（等同旧 Notify）。
    子类 Callback/Bind 覆盖 handle() 添加消费行为。
    """

    def __init__(self, **extract: str) -> None:
        self.extract = extract

    async def handle(self, view: View, event: Event) -> bool:
        """处理事件。返回 True 表示已消费。基类不消费。"""
        return False

    def to_wire(self) -> dict[str, Any]:
        return {"$handler": dict(self.extract)}


class Callback(EventHandler):
    """提取数据 -> callback(*args, **kwargs)。不自动 invalidate。"""

    def __init__(self, callback: Callable[..., Any], /, *args: str, **extract: str) -> None:
        self.callback = callback
        self.args = args
        self.extract = extract

    async def handle(self, view: View, event: Event) -> bool:
        args = event.data.get("$args", [])
        kwargs = {k: v for k, v in event.data.items() if k != "$args"}
        result = self.callback(*args, **kwargs)
        if inspect.isawaitable(result):
            await result
        return True

    def to_wire(self) -> dict[str, Any]:
        wire: dict[str, str | list[str]] = dict(self.extract)
        if self.args:
            wire["$args"] = list(self.args)
        return {"$handler": wire}


class Bind(EventHandler):
    """提取数据 -> setattr(obj, attr, value)。自动 invalidate。"""

    def __init__(self, obj: Any, attr: str, path: str = "$0") -> None:
        self.obj = obj
        self.attr = attr
        self.path = path
        self.extract: dict[str, str] = {}

    async def handle(self, view: View, event: Event) -> bool:
        args = event.data.get("$args", [])
        setattr(self.obj, self.attr, args[0] if args else None)
        view.invalidate()
        return True

    def to_wire(self) -> dict[str, Any]:
        return {"$handler": {"$args": [self.path]}}


class EventFilter:
    """事件观察/拦截器。"""

    async def on_event_filter(self, watched: View, event: Event) -> bool:
        """返回 True 吞掉事件，target 的 on_event 不会被调用。"""
        return False
